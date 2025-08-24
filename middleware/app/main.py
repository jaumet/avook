# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import init_db
from app.api.v1 import router as v1_router
from app.api.admin import router as admin_router
from app.api.su import router as su_router

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
    "http://127.0.0.1:4000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1/admin")
app.include_router(su_router, prefix="/api/v1/su")
