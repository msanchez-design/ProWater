from datetime import date
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from . import models


# ---------- Clientes ----------

def listar_clientes(db: Session, solo_activos: bool = True, buscar: str = None):
    q = db.query(models.Cliente)
    if solo_activos:
        q = q.filter(models.Cliente.activo == True)  # noqa: E712
    if buscar:
        q = q.filter(models.Cliente.nombre.ilike(f"%{buscar}%"))
    return q.order_by(models.Cliente.nombre).all()


def obtener_cliente(db: Session, cliente_id: int):
    return db.query(models.Cliente).get(cliente_id)


# ---------- Saldo / cuenta corriente ----------

def saldos_todos(db: Session, cliente_ids=None) -> dict:
    """Calcula el saldo de MUCHOS clientes de una sola vez (2 consultas agrupadas en
    vez de 1 consulta por cliente), para que las listas no se pongan lentas."""
    q_fact = db.query(
        models.Facturacion.cliente_id,
        func.coalesce(func.sum(models.Facturacion.total), 0.0),
    ).group_by(models.Facturacion.cliente_id)
    q_pagos = db.query(
        models.Pago.cliente_id,
        func.coalesce(func.sum(models.Pago.monto), 0.0),
    ).group_by(models.Pago.cliente_id)

    if cliente_ids is not None:
        q_fact = q_fact.filter(models.Facturacion.cliente_id.in_(cliente_ids))
        q_pagos = q_pagos.filter(models.Pago.cliente_id.in_(cliente_ids))

    facturado = dict(q_fact.all())
    pagado = dict(q_pagos.all())

    ids = set(facturado.keys()) | set(pagado.keys())
    if cliente_ids is not None:
        ids |= set(cliente_ids)

    return {cid: round(facturado.get(cid, 0) - pagado.get(cid, 0), 2) for cid in ids}


def saldo_cliente(db: Session, cliente_id: int) -> float:
    """Saldo = total facturado - total pagado. Positivo = el cliente debe."""
    total_facturado = db.query(func.coalesce(func.sum(models.Facturacion.total), 0.0)) \
        .filter(models.Facturacion.cliente_id == cliente_id).scalar()
    total_pagado = db.query(func.coalesce(func.sum(models.Pago.monto), 0.0)) \
        .filter(models.Pago.cliente_id == cliente_id).scalar()
    return round((total_facturado or 0) - (total_pagado or 0), 2)


def resumen_deuda_clientes(db: Session):
    """Devuelve lista de (cliente, saldo) para todos los clientes activos, ordenado por deuda."""
    clientes = listar_clientes(db, solo_activos=True)
    saldos = saldos_todos(db, [c.id for c in clientes])
    resumen = [(c, saldos.get(c.id, 0.0)) for c in clientes]
    resumen.sort(key=lambda x: x[1], reverse=True)
    return resumen


def facturaciones_pendientes_cliente(db: Session, cliente_id: int):
    """Devuelve las facturaciones del cliente que todavía tienen saldo pendiente
    (total - pagos ya imputados a ese período), de la más reciente a la más vieja.
    Sirve para el desplegable 'Aplicar pago a...'."""
    facturaciones = db.query(models.Facturacion).filter(
        models.Facturacion.cliente_id == cliente_id
    ).order_by(models.Facturacion.periodo.desc()).all()

    pagado_por_facturacion = dict(
        db.query(models.Pago.facturacion_id, func.coalesce(func.sum(models.Pago.monto), 0.0))
        .filter(models.Pago.cliente_id == cliente_id, models.Pago.facturacion_id.isnot(None))
        .group_by(models.Pago.facturacion_id).all()
    )

    pendientes = []
    for f in facturaciones:
        pendiente = round(f.total - pagado_por_facturacion.get(f.id, 0.0), 2)
        if pendiente > 0.01:
            pendientes.append((f, pendiente))
    return pendientes



def movimientos_cliente(db: Session, cliente_id: int):
    """Arma el 'libro mayor' del cliente: facturaciones (débito) + pagos (crédito), ordenado
    por fecha, con saldo acumulado corrida."""
    facturaciones = db.query(models.Facturacion).filter(
        models.Facturacion.cliente_id == cliente_id
    ).all()
    pagos = db.query(models.Pago).options(joinedload(models.Pago.facturacion)).filter(
        models.Pago.cliente_id == cliente_id
    ).all()

    movimientos = []
    for f in facturaciones:
        # Ordenamos facturaciones por período (string YYYY-MM ordena bien alfabéticamente)
        movimientos.append({
            "fecha": f.periodo + "-01",
            "tipo": "Facturación",
            "detalle": f"Período {f.periodo}" + (" (facturado)" if f.facturado else " (pendiente)"),
            "debito": f.total,
            "credito": 0,
        })
    for p in pagos:
        detalle = p.medio_pago or "Pago"
        if p.facturacion_id and p.facturacion:
            detalle += f" (aplicado a período {p.facturacion.periodo})"
        else:
            detalle += " (a cuenta, sin asignar)"
        movimientos.append({
            "fecha": p.fecha.isoformat(),
            "tipo": "Pago",
            "detalle": detalle,
            "debito": 0,
            "credito": p.monto,
        })

    movimientos.sort(key=lambda m: m["fecha"])

    saldo = 0
    for m in movimientos:
        saldo += m["debito"] - m["credito"]
        m["saldo"] = round(saldo, 2)

    return movimientos


def pagado_por_facturacion(db: Session, facturacion_ids):
    """Total pagado (imputado) para cada facturación, en una sola consulta agrupada."""
    if not facturacion_ids:
        return {}
    rows = db.query(models.Pago.facturacion_id, func.coalesce(func.sum(models.Pago.monto), 0.0)) \
        .filter(models.Pago.facturacion_id.in_(facturacion_ids)) \
        .group_by(models.Pago.facturacion_id).all()
    return dict(rows)


# ---------- Facturación automática ----------

def generar_facturacion_periodo(db: Session, periodo: str, quien_factura: str = ""):
    """
    Genera (o actualiza si ya existe y no está marcada como facturada) la fila de
    facturación de TODOS los clientes activos para el período "YYYY-MM", sumando
    los remitos cargados en ese mes como "extras" sobre el abono base.
    """
    anio, mes = periodo.split("-")
    anio, mes = int(anio), int(mes)

    clientes = listar_clientes(db, solo_activos=True)
    creadas, actualizadas, saltadas = 0, 0, 0

    # Traemos los extras de TODOS los clientes de una sola consulta agrupada
    extras_query = db.query(
        models.Remito.cliente_id,
        func.coalesce(func.sum(models.Remito.bidones_20), 0),
        func.coalesce(func.sum(models.Remito.bidones_10), 0),
        func.coalesce(func.sum(models.Remito.sifones), 0),
    ).filter(
        func.extract("year", models.Remito.fecha) == anio,
        func.extract("month", models.Remito.fecha) == mes,
    ).group_by(models.Remito.cliente_id).all()
    extras_por_cliente = {row[0]: (row[1], row[2], row[3]) for row in extras_query}

    # Y las facturaciones ya existentes del período, también de una sola consulta
    existentes_query = db.query(models.Facturacion).filter(
        models.Facturacion.periodo == periodo
    ).all()
    existentes_por_cliente = {f.cliente_id: f for f in existentes_query}

    for cliente in clientes:
        b20, b10, sif = extras_por_cliente.get(cliente.id, (0, 0, 0))
        existente = existentes_por_cliente.get(cliente.id)

        if existente and existente.facturado:
            saltadas += 1
            continue  # no pisamos algo que ya se facturó y quedó cerrado

        total = (
            (cliente.abono_mensual or 0)
            + b20 * (cliente.precio_bidon20 or 0)
            + b10 * (cliente.precio_bidon10 or 0)
            + sif * (cliente.precio_sifon or 0)
        )

        if existente:
            existente.dispensers = cliente.cantidad_dispensers
            existente.abono = cliente.abono_mensual
            existente.bidones_20_extra = b20
            existente.precio_bidon20 = cliente.precio_bidon20
            existente.bidones_10_extra = b10
            existente.precio_bidon10 = cliente.precio_bidon10
            existente.sifones = sif
            existente.precio_sifon = cliente.precio_sifon
            existente.total = total
            if quien_factura:
                existente.quien_factura = quien_factura
            actualizadas += 1
        else:
            nueva = models.Facturacion(
                cliente_id=cliente.id,
                periodo=periodo,
                dispensers=cliente.cantidad_dispensers,
                abono=cliente.abono_mensual,
                bidones_20_extra=b20,
                precio_bidon20=cliente.precio_bidon20,
                bidones_10_extra=b10,
                precio_bidon10=cliente.precio_bidon10,
                sifones=sif,
                precio_sifon=cliente.precio_sifon,
                total=total,
                quien_factura=quien_factura,
            )
            db.add(nueva)
            creadas += 1

    db.commit()
    return {"creadas": creadas, "actualizadas": actualizadas, "saltadas_ya_facturadas": saltadas}
