import os
import sys
import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine


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
from app.models import Card, Title

app_db.DATABASE_URL = "sqlite:///./test_status.db"
app_db.engine = create_engine(
    app_db.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
SQLModel.metadata.create_all(app_db.engine)

client = TestClient(app)


def _register_and_login(client: TestClient) -> tuple[dict[str, str], str]:
    email = f"owner-{uuid.uuid4()}@example.com"
    password = "secret123"
    register_response = client.post(
        "/api/v1/register",
        json={
            "email": email,
            "password": password,
            "name": "Owner",
            "location": "Test",
        },
    )
    assert register_response.status_code == 200

    login_response = client.post(
        "/api/v1/login",
        data={"username": email, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, email


def _create_claim(client: TestClient) -> tuple[str, dict[str, str], str]:
    headers, email = _register_and_login(client)
    qr = f"ST-{uuid.uuid4()}"

    with Session(app_db.engine) as session:
        title = Title(
            title=f"Title {uuid.uuid4()}",
            author="Author",
            language="ca",
            duration_sec=3600,
            price_retail=0.0,
            currency="EUR",
        )
        session.add(title)
        session.commit()
        session.refresh(title)
        card = Card(qr=qr, title_id=title.id)
        session.add(card)
        session.commit()

    claim_response = client.post(
        f"/api/v1/claim/{qr}",
        params={"owner_email": email},
        headers=headers,
    )
    assert claim_response.status_code == 200

    return qr, headers, email


def test_abook_status_ok_default_language():
    qr, headers, email = _create_claim(client)

    response = client.get(f"/api/v1/abook/{qr}/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["qr"] == qr
    assert data["status"] == 1
    assert data["owner_email"] == email
    assert data["status_label"] == "Reclamat"
    assert data["language"] == "ca"


def test_abook_status_respects_accept_language_header():
    qr, headers, _ = _create_claim(client)

    response = client.get(
        f"/api/v1/abook/{qr}/status",
        headers={**headers, "Accept-Language": "es-ES,ca;q=0.8"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status_label"] == "Reclamado"
    assert data["language"] == "es"


def test_abook_status_respects_lang_query_param():
    qr, headers, _ = _create_claim(client)

    response = client.get(
        f"/api/v1/abook/{qr}/status",
        params={"lang": "en"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status_label"] == "Claimed"
    assert data["language"] == "en"

def test_abook_status_not_found():
    headers, _ = _register_and_login(client)
    qr = "ST-notfound"
    response = client.get(f"/api/v1/abook/{qr}/status", headers=headers)
    assert response.status_code == 404
