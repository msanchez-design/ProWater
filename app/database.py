import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local_dev.db")

# Si pegaste la cadena de conexión tal cual te la da Supabase (postgresql://...),
# la adaptamos automáticamente para usar el driver pg8000, que no necesita
# herramientas de compilación instaladas en Windows/Mac/Linux.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+pg8000://", 1)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # Solo se usa si no configuraste Supabase todavía (modo prueba local)
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql+pg8000"):
    import ssl
    ssl_context = ssl.create_default_context()
    # No verificamos la cadena del certificado: el "pooler" de Supabase la presenta
    # de una forma que Render no puede validar, aunque la conexión sigue yendo
    # encriptada igual. Sin esto, el deploy falla con CERTIFICATE_VERIFY_FAILED.
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connect_args = {"ssl_context": ssl_context, "timeout": 10}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,  # evita usar conexiones que Supabase ya cerró por inactividad
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()