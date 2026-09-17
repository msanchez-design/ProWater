from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, Text
)
from sqlalchemy.orm import relationship
from .database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(20), default="repartidor")  # admin | repartidor
    activo = Column(Boolean, default=True)
    creado = Column(DateTime, default=datetime.utcnow)


class ListaPrecios(Base):
    """Lista de precios reutilizable: se la asignás a varios clientes, y si cambian
    los precios, editás la lista una sola vez en vez de cliente por cliente."""
    __tablename__ = "listas_precios"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    precio_abono = Column(Float, default=0)
    bidones_incluidos_abono = Column(Integer, default=4)
    precio_bidon20 = Column(Float, default=0)
    precio_bidon10 = Column(Float, default=0)
    precio_sifon = Column(Float, default=0)
    activa = Column(Boolean, default=True)
    observacion = Column(Text)
    creado = Column(DateTime, default=datetime.utcnow)

    clientes = relationship("Cliente", back_populates="lista_precios")


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(200), nullable=False, index=True)
    cuit = Column(String(50))
    condicion_fiscal = Column(String(50))     # RESPONSABLE INSCRIPTO, EXENTO, etc.
    tipo_factura = Column(String(50))         # A, B, C
    telefono = Column(String(50))
    direccion = Column(String(250))
    barrio = Column(String(100))

    cantidad_dispensers = Column(Integer, default=0)  # dispensers instalados (dato físico/logístico)
    cantidad_abonos = Column(Integer, default=0)       # cuántos abonos factura (normalmente = dispensers,
                                                        # pero puede diferir por excepciones)
    abono_mensual = Column(Float, default=0)       # precio de UN abono (1 dispenser + bidones incluidos)
    bidones_incluidos_abono = Column(Integer, default=4)  # bidones 20L incluidos por CADA abono
    precio_bidon20 = Column(Float, default=0)      # precio de bidón 20L extra (por encima de lo incluido)
    precio_bidon10 = Column(Float, default=0)
    precio_sifon = Column(Float, default=0)

    activo = Column(Boolean, default=True)
    observacion = Column(Text)
    saldo_inicial = Column(Float, default=0)  # deuda (o a favor, si es negativo) al momento de migrar
    lista_precios_id = Column(Integer, ForeignKey("listas_precios.id"), nullable=True)
    creado = Column(DateTime, default=datetime.utcnow)

    lista_precios = relationship("ListaPrecios", back_populates="clientes")
    remitos = relationship("Remito", back_populates="cliente")
    facturaciones = relationship("Facturacion", back_populates="cliente")
    pagos = relationship("Pago", back_populates="cliente")


class Remito(Base):
    """Cada entrega/reparto que hace un chofer a un cliente."""
    __tablename__ = "remitos"

    id = Column(Integer, primary_key=True)
    numero = Column(String(30))  # número de remito físico, si lo usan
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    fecha = Column(Date, default=date.today, nullable=False)

    bidones_20 = Column(Integer, default=0)
    bidones_10 = Column(Integer, default=0)
    sifones = Column(Integer, default=0)
    dispensers_entregados = Column(Integer, default=0)  # instalación de dispenser nuevo
    dispensers_retirados = Column(Integer, default=0)

    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    observacion = Column(Text)
    creado = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="remitos")
    usuario = relationship("Usuario")


class Facturacion(Base):
    """Consumo/facturación de un cliente en un período (mes-año)."""
    __tablename__ = "facturaciones"

    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    periodo = Column(String(7), nullable=False)  # formato "YYYY-MM"

    dispensers = Column(Integer, default=0)
    cantidad_abonos = Column(Integer, default=0)         # abonos facturados este período
    abono = Column(Float, default=0)                      # total de abono (cantidad_abonos * precio unitario)
    bidones_20_incluidos = Column(Integer, default=0)    # bidones 20L incluidos por los abonos, ese período
    bidones_20_entregados = Column(Integer, default=0)   # bidones 20L que salieron según remitos ese período
    bidones_20_extra = Column(Integer, default=0)        # lo que se cobra aparte (entregados - incluidos)
    precio_bidon20 = Column(Float, default=0)
    bidones_10_extra = Column(Integer, default=0)
    precio_bidon10 = Column(Float, default=0)
    sifones = Column(Integer, default=0)
    precio_sifon = Column(Float, default=0)
    total = Column(Float, default=0)

    facturado = Column(Boolean, default=False)
    quien_factura = Column(String(100))
    avisado = Column(Boolean, default=False)
    observacion = Column(Text)

    creado = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="facturaciones")


class Producto(Base):
    """Catálogo de productos que se venden aparte del abono (no son parte del reparto
    mensual): bidón con canilla, dispenser de agua natural, etc."""
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    precio = Column(Float, default=0)
    activo = Column(Boolean, default=True)
    observacion = Column(Text)
    creado = Column(DateTime, default=datetime.utcnow)


class Venta(Base):
    """Venta puntual de un producto a un cliente (no es parte del abono mensual).
    Queda en la cuenta corriente del cliente igual que una facturación."""
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=True)
    nombre_producto = Column(String(150))  # copia del nombre al momento de vender
    fecha = Column(Date, default=date.today, nullable=False)
    cantidad = Column(Integer, default=1)
    precio_unitario = Column(Float, default=0)
    total = Column(Float, default=0)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    observacion = Column(Text)
    creado = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente")
    producto = relationship("Producto")
    usuario = relationship("Usuario")


class Pago(Base):
    """Pago recibido de un cliente (se aplica a la cuenta corriente general)."""
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    facturacion_id = Column(Integer, ForeignKey("facturaciones.id"), nullable=True)  # None = pago a cuenta
    fecha = Column(Date, default=date.today, nullable=False)
    monto = Column(Float, nullable=False)
    medio_pago = Column(String(50))  # efectivo, transferencia, etc.
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    observacion = Column(Text)
    creado = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="pagos")
    facturacion = relationship("Facturacion")
    usuario = relationship("Usuario")
