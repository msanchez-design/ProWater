import bcrypt
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from . import models


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def usuario_actual(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.Usuario).get(user_id)


def requerir_login(request: Request, db: Session):
    user = usuario_actual(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user
