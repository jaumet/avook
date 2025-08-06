# app/auth.py
from datetime import datetime, timedelta
from app import db
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.db import get_user_by_email, get_session
from app.models import User
from sqlmodel import Session
import os


SECRET_KEY = os.getenv("SECRET_KEY")
#SECRET_KEY = "canvia-aquesta-clau-per-una-segura"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

#oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "sub": str(data["sub"]),  # <- això és l’UUID com a string
        "exp": expire
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


from uuid import UUID

# app/auth.py

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_session)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get(User, user_id)  # ← Retorna l'objecte complet
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return user  # 👈 NO return user.id!




from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
