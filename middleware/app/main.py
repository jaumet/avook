# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import init_db
from app.api import v1, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()          # s’executa al startup
    yield              # aquí vindria el shutdown, si cal

app = FastAPI(title="Audiovook Middleware",
              version="0.1.0",
              lifespan=lifespan)

origins = [
    "http://localhost",
    "http://localhost:4000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1/admin")
