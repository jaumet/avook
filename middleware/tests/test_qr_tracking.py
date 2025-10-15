import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

os.environ.setdefault("BACKUP_RUN_ON_START", "0")

DATABASE_FILE = Path("test_qr_tracking.db")
if DATABASE_FILE.exists():
    DATABASE_FILE.unlink()


class _FakeRedisClient:
    def get(self, _key):
        return None

    def setex(self, _key, _ttl, _value):
        return True

    def set(self, _key, _value):
        return True

    def delete(self, _key):
        return True


def _install_fake_redis():
    fake_redis = SimpleNamespace(
        Redis=SimpleNamespace(from_url=lambda *args, **kwargs: _FakeRedisClient())
    )
    fake_exceptions = SimpleNamespace(RedisError=Exception)
    sys.modules.setdefault("redis", fake_redis)
    sys.modules.setdefault("redis.exceptions", fake_exceptions)


_install_fake_redis()

from app import db as app_db  # noqa: E402

app_db.DATABASE_URL = f"sqlite:///{DATABASE_FILE}"
app_db.engine = create_engine(
    app_db.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
SQLModel.metadata.create_all(app_db.engine)

from app.main import app  # noqa: E402
from app.api.admin import get_current_config_superuser  # noqa: E402
from app.models import CustomQr, QrScanEvent  # noqa: E402

app.dependency_overrides[get_current_config_superuser] = lambda: {"sub": "tests"}

client = TestClient(app)


def test_custom_qr_creation_and_tracking():
    payload = {
        "slug": "press-kit",
        "target_url": "https://audiovook.test/press",
        "campaign": "press-tour",
        "label": "Press Kit",
        "notes": "For media kits",
    }

    response = client.post(
        "/api/v1/admin/qr/custom",
        json=payload,
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == payload["slug"]
    assert body["scan_count"] == 0

    visit = client.get(
        f"/api/v1/qr/custom/{payload['slug']}",
        params={"source": "instagram"},
        headers={"User-Agent": "pytest"},
    )
    assert visit.status_code == 200
    visit_body = visit.json()
    assert visit_body["scan_count"] == 1
    assert visit_body["campaign"] == "press-tour"

    second_visit = client.get(f"/api/v1/qr/custom/{payload['slug']}")
    assert second_visit.status_code == 200
    assert second_visit.json()["scan_count"] == 2

    with Session(app_db.engine) as session:
        record = session.get(CustomQr, payload["slug"])
        assert record is not None
        assert record.scan_count == 2
        assert record.last_scanned_at is not None
        last_scan = record.last_scanned_at
        if last_scan.tzinfo is None:
            last_scan = last_scan.replace(tzinfo=timezone.utc)
        assert abs((last_scan - datetime.now(timezone.utc)).total_seconds()) < 10

        events = session.exec(
            select(QrScanEvent)
            .where(QrScanEvent.slug == payload["slug"])
            .order_by(QrScanEvent.scanned_at.asc())
        ).all()
        assert len(events) == 2
        assert events[0].source == "instagram"
        assert events[0].user_agent == "pytest"
        assert events[1].source is None


def test_custom_qr_svg_and_deletion():
    payload = {
        "slug": "launch-day",
        "target_url": "https://audiovook.test/launch",
    }

    create = client.post(
        "/api/v1/admin/qr/custom",
        json=payload,
        headers={"Authorization": "Bearer test"},
    )
    assert create.status_code == 200

    svg_response = client.get(
        f"/api/v1/admin/qr/custom/{payload['slug']}/svg",
        headers={"Authorization": "Bearer test"},
    )
    assert svg_response.status_code == 200
    assert svg_response.headers["content-type"] == "image/svg+xml"
    assert "<svg" in svg_response.text

    delete = client.delete(
        f"/api/v1/admin/qr/custom/{payload['slug']}",
        headers={"Authorization": "Bearer test"},
    )
    assert delete.status_code == 204

    follow_up = client.get(
        f"/api/v1/admin/qr/custom/{payload['slug']}",
        headers={"Authorization": "Bearer test"},
    )
    assert follow_up.status_code == 404

    with Session(app_db.engine) as session:
        record = session.get(CustomQr, payload["slug"])
        assert record is None
        scans = session.exec(
            select(QrScanEvent).where(QrScanEvent.slug == payload["slug"])
        ).all()
        assert scans == []


def teardown_module(_module):
    app.dependency_overrides.pop(get_current_config_superuser, None)
    client.close()
    if DATABASE_FILE.exists():
        DATABASE_FILE.unlink()
