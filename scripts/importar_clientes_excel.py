"""
Importa los clientes existentes desde tus dos planillas actuales a la base de datos
nueva. Es seguro correrlo más de una vez: si el cliente ya existe (por nombre), lo
actualiza en vez de duplicarlo. Si una fila tiene datos raros, la salta y sigue
(te muestra un resumen al final con lo que se saltó).

Uso (desde la carpeta water_app, con el entorno virtual activado):

    python scripts/importar_clientes_excel.py "ruta/a/FACTURACION_MENSUAL_...xlsx" "ruta/a/ESTADO_DEUDA_CLIENTES...xlsx"
"""
import sys
import os
import warnings
import openpyxl

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from app.database import SessionLocal, engine, Base  # noqa: E402
from app import models  # noqa: E402

Base.metadata.create_all(bind=engine)

MAX_NOMBRE = 200
MAX_CORTO = 50


def limpiar_cuit(valor):
    if valor is None:
        return None
    s = str(valor).strip()
    if s.startswith("#") or s == "":
        return None
    return s[:-2] if s.endswith(".0") else s


def truncar(valor, largo=MAX_CORTO):
    if valor is None:
        return None
    s = str(valor).strip()
    if s == "":
        return None
    return s[:largo]


def num(valor):
    try:
        if valor is None or valor == "":
            return None
        return float(valor)
    except (TypeError, ValueError):
        return None


def importar(path_facturacion, path_deuda):
    db = SessionLocal()
    avisos = []

    # 1) Condición fiscal / CUIT desde "CONDICION Y CUIT NUEVO" (por posición: A,B,C,D)
    condiciones = {}
    if path_facturacion:
        wb = openpyxl.load_workbook(path_facturacion, data_only=True)
        if "CONDICION Y CUIT NUEVO" in wb.sheetnames:
            ws = wb["CONDICION Y CUIT NUEVO"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                nombre = row[0] if len(row) > 0 else None
                cuit = row[1] if len(row) > 1 else None
                tipo_fact = row[2] if len(row) > 2 else None
                condicion = row[3] if len(row) > 3 else None
                if not nombre:
                    continue
                tipo_fact_corto = None
                if tipo_fact:
                    tipo_fact_corto = str(tipo_fact).replace("FACTURA", "").strip()
                condiciones[str(nombre).strip().upper()] = {
                    "cuit": limpiar_cuit(cuit),
                    "tipo_factura": truncar(tipo_fact_corto),
                    "condicion_fiscal": truncar(condicion),
                }

    # 2) Teléfonos desde "Contacto" (por posición: A,B)
    telefonos = {}
    ultimos = {}
    if path_deuda:
        wb2 = openpyxl.load_workbook(path_deuda, data_only=True)
        if "Contacto" in wb2.sheetnames:
            ws2 = wb2["Contacto"]
            for row in ws2.iter_rows(min_row=2, values_only=True):
                nombre = row[0] if len(row) > 0 else None
                tel = row[1] if len(row) > 1 else None
                if not nombre:
                    continue
                telefonos[str(nombre).strip().upper()] = truncar(tel)

        # 3) Últimos datos de abono/precio desde "CC Clientes"
        #    OJO: en esta hoja los encabezados están corridos respecto a los datos;
        #    leemos por POSICIÓN de columna, no por nombre de encabezado:
        #    A=periodo, B=cliente, C=dispensers, D=abono, E=bidon20 extra, F=precio bidon20
        if "CC Clientes" in wb2.sheetnames:
            ws3 = wb2["CC Clientes"]
            for row in ws3.iter_rows(min_row=2, values_only=True):
                if len(row) < 6:
                    continue
                nombre = row[1]
                if not nombre or not isinstance(nombre, str):
                    continue
                nombre_upper = nombre.strip().upper()
                ultimos[nombre_upper] = {
                    "dispensers": num(row[2]),
                    "abono": num(row[3]),
                    "precio_bidon20": num(row[5]) if len(row) > 5 else None,
                }  # nos quedamos con la última fila encontrada (son cronológicas)

    creados, actualizados, saltados = 0, 0, 0
    nombres_vistos = set()

    fuente_nombres = list(condiciones.keys()) + list(telefonos.keys()) + list(ultimos.keys())
    for nombre_upper in sorted(set(fuente_nombres)):
        if nombre_upper in nombres_vistos or not nombre_upper.strip():
            continue
        nombres_vistos.add(nombre_upper)

        try:
            info_fiscal = condiciones.get(nombre_upper, {})
            telefono = telefonos.get(nombre_upper)
            datos = ultimos.get(nombre_upper, {})

            cliente = db.query(models.Cliente).filter(
                models.Cliente.nombre.ilike(nombre_upper)
            ).first()

            if not cliente:
                cliente = models.Cliente(nombre=truncar(nombre_upper.title(), MAX_NOMBRE))
                db.add(cliente)
                creados += 1
            else:
                actualizados += 1

            cliente.cuit = truncar(info_fiscal.get("cuit")) or cliente.cuit
            cliente.tipo_factura = truncar(info_fiscal.get("tipo_factura")) or cliente.tipo_factura
            cliente.condicion_fiscal = truncar(info_fiscal.get("condicion_fiscal")) or cliente.condicion_fiscal
            cliente.telefono = truncar(telefono) or cliente.telefono

            if datos.get("dispensers") is not None:
                cliente.cantidad_dispensers = int(datos["dispensers"])
            if datos.get("abono") is not None:
                cliente.abono_mensual = datos["abono"]
            if datos.get("precio_bidon20") is not None:
                cliente.precio_bidon20 = datos["precio_bidon20"]

            db.flush()  # para detectar errores fila por fila, no recién al final

        except Exception as e:  # noqa: BLE001
            db.rollback()
            saltados += 1
            avisos.append(f"  - {nombre_upper}: {e}")
            continue

    db.commit()
    db.close()

    print(f"\nListo. Clientes creados: {creados} | actualizados: {actualizados} | saltados: {saltados}")
    if avisos:
        print("\nFilas salteadas por datos raros (revisalas a mano si querés):")
        for a in avisos[:30]:
            print(a)
        if len(avisos) > 30:
            print(f"  ... y {len(avisos) - 30} más.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python scripts/importar_clientes_excel.py <FACTURACION.xlsx> <ESTADO_DEUDA.xlsx>")
        sys.exit(1)
    importar(sys.argv[1], sys.argv[2])
