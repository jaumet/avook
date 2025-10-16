import os
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine


class _FakeRedisClient:
    def get(self, _key):
        return None

    def setex(self, _key, _ttl, _value):
        return True

    def set(self, _key, _value):
        return True

    def delete(self, _key):
        return True


fake_redis = SimpleNamespace(
    Redis=SimpleNamespace(from_url=lambda *args, **kwargs: _FakeRedisClient())
)
fake_exceptions = SimpleNamespace(RedisError=Exception)

sys.modules.setdefault("redis", fake_redis)
sys.modules.setdefault("redis.exceptions", fake_exceptions)

from app.main import app
from app import db as app_db

app_db.DATABASE_URL = "sqlite:///./test_i18n.db"
app_db.engine = create_engine(
    app_db.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
SQLModel.metadata.create_all(app_db.engine)

client = TestClient(app)


def test_get_translations_returns_errors_by_default():
    response = client.get("/api/v1/translations/ca")
    assert response.status_code == 200
    data = response.json()
    assert "QR_NOT_FOUND" in data
    assert data["ALREADY_CLAIMED"].startswith("Aquesta targeta")


def test_get_translations_all_namespace_includes_statuses():
    response = client.get("/api/v1/translations/es", params={"namespace": "all"})
    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "es"
    assert data["statuses"]["1"] == "Reclamado"
    assert data["errors"]["QR_NOT_FOUND"].startswith("Código")


def test_get_translations_status_namespace():
    response = client.get("/api/v1/translations/en", params={"namespace": "statuses"})
    assert response.status_code == 200
    data = response.json()
    assert data["2"] == "On loan"
