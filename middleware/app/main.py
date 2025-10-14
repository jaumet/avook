# app/main.py
from contextlib import asynccontextmanager
from os import getenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import init_db, engine
from app.api.v1 import router as v1_router
from app.api.admin import router as admin_router
from app.api.su import router as su_router
from app.backup import get_backup_scheduler
from app.monitoring import configure_logging, RequestMonitoringMiddleware


configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()          # s’executa al startup
    scheduler = get_backup_scheduler(engine)
    await scheduler.start()
    try:
        yield          # aquí vindria el shutdown, si cal
    finally:
        await scheduler.stop()

app = FastAPI(title="Audiovook Middleware",
              version="0.1.0",
              lifespan=lifespan)

default_origins = {
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:4000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:4000",
    "http://127.0.0.1:5173",
}

extra_origins = getenv("CORS_ALLOW_ORIGINS")
if extra_origins:
    default_origins.update({origin.strip() for origin in extra_origins.split(",") if origin.strip()})

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(default_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestMonitoringMiddleware)

app.include_router(v1_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1/admin")
app.include_router(su_router, prefix="/api/v1/su")
