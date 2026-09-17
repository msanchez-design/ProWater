import os
from datetime import date, datetime

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session, contains_eager, joinedload
from dotenv import load_dotenv

from . import models, crud, auth
from .database import engine, get_db, Base

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Reparto de Agua - Gestión")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret-cambiame"))

BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def fmt_money(v):
    try:
        return f"${v:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return v

templates.env.filters["money"] = fmt_money


@app.on_event("startup")
def crear_admin_inicial():
    db = next(get_db())
    existe = db.query(models.Usuario).first()
    if not existe:
        email = os.getenv("ADMIN_EMAIL", "admin@tuempresa.com")
        password = os.getenv("ADMIN_PASSWORD", "cambiame123")
        admin = models.Usuario(
            nombre="Administrador",
            email=email,
            password_hash=auth.hash_password(password),
            rol="admin",
        )
        db.add(admin)
        db.commit()
    db.close()


def usuario_o_redirect(request: Request, db: Session):
    """Devuelve el usuario logueado, o None. Las rutas deciden qué hacer con None."""
    return auth.usuario_actual(request, db)


def es_admin(user) -> bool:
    return bool(user and user.rol == "admin")


# ---------------- LOGIN ----------------

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...),
                  db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if not user or not auth.verificar_password(password, user.password_hash):
        return RedirectResponse(url="/login?error=Email o contraseña incorrectos", status_code=303)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ---------------- DASHBOARD ----------------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    resumen = crud.resumen_deuda_clientes(db)
    deuda_total = sum(saldo for _, saldo in resumen if saldo > 0)
    clientes_con_deuda = [x for x in resumen if x[1] > 0]
    ultimos_remitos = db.query(models.Remito).options(
        joinedload(models.Remito.cliente)
    ).order_by(models.Remito.fecha.desc(), models.Remito.id.desc()).limit(10).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user,
        "deuda_total": deuda_total,
        "clientes_con_deuda": clientes_con_deuda[:15],
        "cantidad_clientes_deuda": len(clientes_con_deuda),
        "ultimos_remitos": ultimos_remitos,
    })


# ---------------- CLIENTES ----------------

@app.get("/clientes", response_class=HTMLResponse)
def clientes_list(request: Request, q: str = None, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    clientes = crud.listar_clientes(db, buscar=q)
    saldos = crud.saldos_todos(db, [c.id for c in clientes])
    return templates.TemplateResponse("clientes_list.html", {
        "request": request, "user": user, "clientes": clientes, "saldos": saldos, "q": q or ""
    })


@app.get("/clientes/nuevo", response_class=HTMLResponse)
def cliente_nuevo_form(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    listas = crud.listar_listas_precios(db, solo_activas=False)
    return templates.TemplateResponse("cliente_form.html", {
        "request": request, "user": user, "cliente": None, "listas": listas
    })


@app.post("/clientes/nuevo")
def cliente_nuevo_submit(
    request: Request,
    nombre: str = Form(...),
    cuit: str = Form(""),
    condicion_fiscal: str = Form(""),
    tipo_factura: str = Form(""),
    telefono: str = Form(""),
    direccion: str = Form(""),
    barrio: str = Form(""),
    cantidad_dispensers: int = Form(0),
    cantidad_abonos: int = Form(0),
    bidones_incluidos_abono: int = Form(4),
    abono_mensual: float = Form(0),
    precio_bidon20: float = Form(0),
    precio_bidon10: float = Form(0),
    precio_sifon: float = Form(0),
    lista_precios_id: str = Form(""),
    saldo_inicial: float = Form(0),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    cliente = models.Cliente(
        nombre=nombre, cuit=cuit, condicion_fiscal=condicion_fiscal, tipo_factura=tipo_factura,
        telefono=telefono, direccion=direccion, barrio=barrio,
        cantidad_dispensers=cantidad_dispensers, cantidad_abonos=cantidad_abonos,
        bidones_incluidos_abono=bidones_incluidos_abono, abono_mensual=abono_mensual,
        precio_bidon20=precio_bidon20, precio_bidon10=precio_bidon10, precio_sifon=precio_sifon,
        lista_precios_id=int(lista_precios_id) if lista_precios_id else None,
        saldo_inicial=saldo_inicial,
        observacion=observacion,
    )
    db.add(cliente)
    db.commit()
    return RedirectResponse(url="/clientes", status_code=303)


@app.get("/clientes/{cliente_id}", response_class=HTMLResponse)
def cliente_detalle(request: Request, cliente_id: int, error: str = None, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    cliente = crud.obtener_cliente(db, cliente_id)
    movimientos = crud.movimientos_cliente(db, cliente_id)
    saldo = crud.saldo_cliente(db, cliente_id)
    remitos = db.query(models.Remito).filter(models.Remito.cliente_id == cliente_id) \
        .order_by(models.Remito.fecha.desc()).limit(20).all()
    pendientes = crud.facturaciones_pendientes_cliente(db, cliente_id)
    productos = crud.listar_productos(db)
    return templates.TemplateResponse("cliente_detail.html", {
        "request": request, "user": user, "cliente": cliente,
        "movimientos": movimientos, "saldo": saldo, "remitos": remitos,
        "pendientes": pendientes, "productos": productos, "error": error,
    })


@app.get("/clientes/{cliente_id}/editar", response_class=HTMLResponse)
def cliente_editar_form(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    cliente = crud.obtener_cliente(db, cliente_id)
    listas = crud.listar_listas_precios(db, solo_activas=False)
    return templates.TemplateResponse("cliente_form.html", {
        "request": request, "user": user, "cliente": cliente, "listas": listas
    })


@app.post("/clientes/{cliente_id}/editar")
def cliente_editar_submit(
    request: Request,
    cliente_id: int,
    nombre: str = Form(...),
    cuit: str = Form(""),
    condicion_fiscal: str = Form(""),
    tipo_factura: str = Form(""),
    telefono: str = Form(""),
    direccion: str = Form(""),
    barrio: str = Form(""),
    cantidad_dispensers: int = Form(0),
    cantidad_abonos: int = Form(0),
    bidones_incluidos_abono: int = Form(4),
    abono_mensual: float = Form(0),
    precio_bidon20: float = Form(0),
    precio_bidon10: float = Form(0),
    precio_sifon: float = Form(0),
    lista_precios_id: str = Form(""),
    saldo_inicial: float = Form(0),
    observacion: str = Form(""),
    activo: str = Form(None),
    db: Session = Depends(get_db),
):
    cliente = crud.obtener_cliente(db, cliente_id)
    cliente.nombre = nombre
    cliente.cuit = cuit
    cliente.condicion_fiscal = condicion_fiscal
    cliente.tipo_factura = tipo_factura
    cliente.telefono = telefono
    cliente.direccion = direccion
    cliente.barrio = barrio
    cliente.cantidad_dispensers = cantidad_dispensers
    cliente.cantidad_abonos = cantidad_abonos
    cliente.bidones_incluidos_abono = bidones_incluidos_abono
    cliente.abono_mensual = abono_mensual
    cliente.precio_bidon20 = precio_bidon20
    cliente.precio_bidon10 = precio_bidon10
    cliente.precio_sifon = precio_sifon
    cliente.lista_precios_id = int(lista_precios_id) if lista_precios_id else None
    cliente.saldo_inicial = saldo_inicial
    cliente.observacion = observacion
    cliente.activo = bool(activo)
    db.commit()
    return RedirectResponse(url=f"/clientes/{cliente_id}", status_code=303)


@app.post("/clientes/{cliente_id}/eliminar")
def cliente_eliminar(cliente_id: int, db: Session = Depends(get_db)):
    ok, motivo = crud.eliminar_cliente(db, cliente_id)
    if ok:
        return RedirectResponse(url="/clientes?eliminado=1", status_code=303)
    return RedirectResponse(url=f"/clientes/{cliente_id}?error={motivo}", status_code=303)


# ---------------- REMITOS ----------------

@app.get("/remitos", response_class=HTMLResponse)
def remitos_list(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    remitos = db.query(models.Remito).options(
        joinedload(models.Remito.cliente), joinedload(models.Remito.usuario)
    ).order_by(models.Remito.fecha.desc(), models.Remito.id.desc()).limit(100).all()
    return templates.TemplateResponse("remitos_list.html", {"request": request, "user": user, "remitos": remitos})


@app.get("/remitos/nuevo", response_class=HTMLResponse)
def remito_nuevo_form(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    clientes = crud.listar_clientes(db)
    return templates.TemplateResponse("remito_form.html", {
        "request": request, "user": user, "clientes": clientes, "hoy": date.today().isoformat()
    })


@app.post("/remitos/nuevo")
def remito_nuevo_submit(
    request: Request,
    cliente_id: int = Form(...),
    fecha: str = Form(...),
    numero: str = Form(""),
    bidones_20: int = Form(0),
    bidones_10: int = Form(0),
    sifones: int = Form(0),
    dispensers_entregados: int = Form(0),
    dispensers_retirados: int = Form(0),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    user = usuario_o_redirect(request, db)
    remito = models.Remito(
        cliente_id=cliente_id,
        fecha=datetime.strptime(fecha, "%Y-%m-%d").date(),
        numero=numero,
        bidones_20=bidones_20, bidones_10=bidones_10, sifones=sifones,
        dispensers_entregados=dispensers_entregados, dispensers_retirados=dispensers_retirados,
        observacion=observacion,
        usuario_id=user.id if user else None,
    )
    db.add(remito)
    db.commit()
    return RedirectResponse(url="/remitos?ok=1", status_code=303)


# ---------------- FACTURACIÓN MENSUAL ----------------

@app.get("/facturacion", response_class=HTMLResponse)
def facturacion_view(request: Request, periodo: str = None, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not periodo:
        periodo = date.today().strftime("%Y-%m")
    filas = db.query(models.Facturacion).join(models.Cliente).filter(models.Facturacion.periodo == periodo) \
        .options(contains_eager(models.Facturacion.cliente)).order_by(models.Cliente.nombre).all()
    pagado = crud.pagado_por_facturacion(db, [f.id for f in filas])
    total_periodo = sum(f.total for f in filas)
    return templates.TemplateResponse("facturacion.html", {
        "request": request, "user": user, "filas": filas, "periodo": periodo,
        "total_periodo": total_periodo, "pagado": pagado,
    })


@app.post("/facturacion/generar")
def facturacion_generar(request: Request, periodo: str = Form(...), db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    resultado = crud.generar_facturacion_periodo(db, periodo, quien_factura=user.nombre if user else "")
    return RedirectResponse(
        url=f"/facturacion?periodo={periodo}&creadas={resultado['creadas']}&actualizadas={resultado['actualizadas']}",
        status_code=303,
    )


@app.post("/facturacion/{fact_id}/marcar")
def facturacion_marcar(fact_id: int, periodo: str = Form(...), db: Session = Depends(get_db)):
    fila = db.query(models.Facturacion).get(fact_id)
    fila.facturado = not fila.facturado
    db.commit()
    return RedirectResponse(url=f"/facturacion?periodo={periodo}", status_code=303)


# ---------------- PAGOS ----------------

@app.post("/clientes/{cliente_id}/pagos/nuevo")
def pago_nuevo(
    request: Request,
    cliente_id: int,
    fecha: str = Form(...),
    monto: float = Form(...),
    medio_pago: str = Form(""),
    facturacion_id: str = Form(""),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    user = usuario_o_redirect(request, db)
    pago = models.Pago(
        cliente_id=cliente_id,
        facturacion_id=int(facturacion_id) if facturacion_id else None,
        fecha=datetime.strptime(fecha, "%Y-%m-%d").date(),
        monto=monto, medio_pago=medio_pago, observacion=observacion,
        usuario_id=user.id if user else None,
    )
    db.add(pago)
    db.commit()
    return RedirectResponse(url=f"/clientes/{cliente_id}", status_code=303)


# ---------------- PRODUCTOS (catálogo de venta) ----------------

@app.get("/productos", response_class=HTMLResponse)
def productos_list(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    productos = crud.listar_productos(db, solo_activos=False)
    return templates.TemplateResponse("productos_list.html", {"request": request, "user": user, "productos": productos})


@app.get("/productos/nuevo", response_class=HTMLResponse)
def producto_nuevo_form(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("producto_form.html", {"request": request, "user": user})


@app.post("/productos/nuevo")
def producto_nuevo_submit(nombre: str = Form(...), precio: float = Form(0),
                           observacion: str = Form(""), db: Session = Depends(get_db)):
    db.add(models.Producto(nombre=nombre, precio=precio, observacion=observacion))
    db.commit()
    return RedirectResponse(url="/productos", status_code=303)


@app.post("/productos/{producto_id}/toggle")
def producto_toggle(producto_id: int, db: Session = Depends(get_db)):
    producto = db.query(models.Producto).get(producto_id)
    producto.activo = not producto.activo
    db.commit()
    return RedirectResponse(url="/productos", status_code=303)


# ---------------- VENTAS PUNTUALES (a un cliente) ----------------

@app.post("/clientes/{cliente_id}/ventas/nuevo")
def venta_nueva(
    request: Request,
    cliente_id: int,
    fecha: str = Form(...),
    producto_id: str = Form(""),
    nombre_producto: str = Form(""),
    cantidad: int = Form(1),
    precio_unitario: float = Form(0),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    user = usuario_o_redirect(request, db)
    nombre_final = nombre_producto
    if producto_id:
        producto = db.query(models.Producto).get(int(producto_id))
        if producto and not nombre_final:
            nombre_final = producto.nombre
    crud.registrar_venta(
        db, cliente_id=cliente_id,
        producto_id=int(producto_id) if producto_id else None,
        nombre_producto=nombre_final or "Producto",
        fecha=datetime.strptime(fecha, "%Y-%m-%d").date(),
        cantidad=cantidad, precio_unitario=precio_unitario, observacion=observacion,
        usuario_id=user.id if user else None,
    )
    return RedirectResponse(url=f"/clientes/{cliente_id}", status_code=303)


# ---------------- LISTAS DE PRECIOS ----------------

@app.get("/listas-precios", response_class=HTMLResponse)
def listas_precios_view(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    listas = crud.listar_listas_precios(db, solo_activas=False)
    return templates.TemplateResponse("listas_precios_list.html", {"request": request, "user": user, "listas": listas})


@app.get("/listas-precios/nuevo", response_class=HTMLResponse)
def lista_precios_nueva_form(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("lista_precios_form.html", {"request": request, "user": user, "lista": None})


@app.post("/listas-precios/nuevo")
def lista_precios_nueva_submit(
    nombre: str = Form(...),
    precio_abono: float = Form(0),
    bidones_incluidos_abono: int = Form(4),
    precio_bidon20: float = Form(0),
    precio_bidon10: float = Form(0),
    precio_sifon: float = Form(0),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    db.add(models.ListaPrecios(
        nombre=nombre, precio_abono=precio_abono, bidones_incluidos_abono=bidones_incluidos_abono,
        precio_bidon20=precio_bidon20, precio_bidon10=precio_bidon10, precio_sifon=precio_sifon,
        observacion=observacion,
    ))
    db.commit()
    return RedirectResponse(url="/listas-precios", status_code=303)


@app.get("/listas-precios/{lista_id}/editar", response_class=HTMLResponse)
def lista_precios_editar_form(request: Request, lista_id: int, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    lista = db.query(models.ListaPrecios).get(lista_id)
    return templates.TemplateResponse("lista_precios_form.html", {"request": request, "user": user, "lista": lista})


@app.post("/listas-precios/{lista_id}/editar")
def lista_precios_editar_submit(
    lista_id: int,
    nombre: str = Form(...),
    precio_abono: float = Form(0),
    bidones_incluidos_abono: int = Form(4),
    precio_bidon20: float = Form(0),
    precio_bidon10: float = Form(0),
    precio_sifon: float = Form(0),
    observacion: str = Form(""),
    activa: str = Form(None),
    db: Session = Depends(get_db),
):
    lista = db.query(models.ListaPrecios).get(lista_id)
    lista.nombre = nombre
    lista.precio_abono = precio_abono
    lista.bidones_incluidos_abono = bidones_incluidos_abono
    lista.precio_bidon20 = precio_bidon20
    lista.precio_bidon10 = precio_bidon10
    lista.precio_sifon = precio_sifon
    lista.observacion = observacion
    lista.activa = bool(activa)
    db.commit()
    return RedirectResponse(url="/listas-precios", status_code=303)


# ---------------- USUARIOS (solo admin) ----------------

@app.get("/usuarios", response_class=HTMLResponse)
def usuarios_list(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not es_admin(user):
        return HTMLResponse("<p style='padding:24px;font-family:sans-serif'>No tenés permisos para ver esta página "
                             "(solo administradores). <a href='/'>Volver</a></p>", status_code=403)
    usuarios = crud.listar_usuarios(db)
    return templates.TemplateResponse("usuarios_list.html", {"request": request, "user": user, "usuarios": usuarios})


@app.get("/usuarios/nuevo", response_class=HTMLResponse)
def usuario_nuevo_form(request: Request, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not es_admin(user):
        return HTMLResponse("<p style='padding:24px;font-family:sans-serif'>No tenés permisos para esta acción "
                             "(solo administradores). <a href='/'>Volver</a></p>", status_code=403)
    return templates.TemplateResponse("usuario_form.html", {"request": request, "user": user, "error": None})


@app.post("/usuarios/nuevo")
def usuario_nuevo_submit(
    request: Request,
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    rol: str = Form("repartidor"),
    db: Session = Depends(get_db),
):
    user = usuario_o_redirect(request, db)
    if not es_admin(user):
        return RedirectResponse(url="/", status_code=303)
    existe = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if existe:
        return templates.TemplateResponse("usuario_form.html", {
            "request": request, "user": user, "error": "Ya existe un usuario con ese email."
        })
    nuevo = models.Usuario(nombre=nombre, email=email, password_hash=auth.hash_password(password), rol=rol)
    db.add(nuevo)
    db.commit()
    return RedirectResponse(url="/usuarios", status_code=303)


@app.post("/usuarios/{usuario_id}/toggle")
def usuario_toggle(request: Request, usuario_id: int, db: Session = Depends(get_db)):
    user = usuario_o_redirect(request, db)
    if not es_admin(user):
        return RedirectResponse(url="/", status_code=303)
    objetivo = db.query(models.Usuario).get(usuario_id)
    if objetivo.id == user.id:
        return RedirectResponse(url="/usuarios?error=No te podés desactivar a vos mismo", status_code=303)
    objetivo.activo = not objetivo.activo
    db.commit()
    return RedirectResponse(url="/usuarios", status_code=303)
