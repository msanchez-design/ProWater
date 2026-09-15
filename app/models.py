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

    cantidad_dispensers = Column(Integer, default=0)
    abono_mensual = Column(Float, default=0)       # precio del abono base (incluye X bidones)
    precio_bidon20 = Column(Float, default=0)      # precio de bidón 20L extra (fuera de abono)
    precio_bidon10 = Column(Float, default=0)
    precio_sifon = Column(Float, default=0)

    activo = Column(Boolean, default=True)
    observacion = Column(Text)
    creado = Column(DateTime, default=datetime.utcnow)

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
    abono = Column(Float, default=0)
    bidones_20_extra = Column(Integer, default=0)
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


class Pago(Base):
    """Pago recibido de un cliente (se aplica a la cuenta corriente general)."""
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    fecha = Column(Date, default=date.today, nullable=False)
    monto = Column(Float, nullable=False)
    medio_pago = Column(String(50))  # efectivo, transferencia, etc.
    observacion = Column(Text)
    creado = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="pagos")
