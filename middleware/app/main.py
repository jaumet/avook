# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import init_db
from app.api import v1

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()          # s’executa al startup
    yield              # aquí vindria el shutdown, si cal

app = FastAPI(title="Audiovook Middleware",
              version="0.1.0",
              lifespan=lifespan)

app.include_router(v1.router, prefix="/api/v1")
