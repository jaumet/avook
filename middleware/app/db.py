# app/db.py

import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session, select
from passlib.context import CryptContext
from app.models import User, Title, Card, Store, Batch, Claim, PlaySession, ListeningProgress

# 🔧 Load .env i crea engine SQLModel
load_dotenv("/code/.env")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/postgres")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        echo=True,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(DATABASE_URL, echo=True)

# 🔄 Inici BD
def init_db():
    SQLModel.metadata.create_all(engine)

# 🧪 Dependency per FastAPI
def get_session():
    with Session(engine) as session:
        yield session

# 🔐 Contrasenyes
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# 👤 Consultes usuari
def get_user_by_email(email: str, db: Session) -> User | None:
    return db.exec(select(User).where(User.email == email)).first()
