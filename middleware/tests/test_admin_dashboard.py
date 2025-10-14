import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
from uuid import uuid4
import sys

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

os.environ.setdefault("BACKUP_RUN_ON_START", "0")

DATABASE_FILE = Path("test_admin_dashboard.db")
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


fake_redis = SimpleNamespace(
    Redis=SimpleNamespace(from_url=lambda *args, **kwargs: _FakeRedisClient())
)
fake_exceptions = SimpleNamespace(RedisError=Exception)

sys.modules.setdefault("redis", fake_redis)
sys.modules.setdefault("redis.exceptions", fake_exceptions)

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
from app.models import Card, Title, User  # noqa: E402

app.dependency_overrides[get_current_config_superuser] = lambda: {"sub": "tests"}

client = TestClient(app)


def _seed_data():
    SQLModel.metadata.drop_all(app_db.engine)
    SQLModel.metadata.create_all(app_db.engine)

    now = datetime.now(timezone.utc)
    with Session(app_db.engine) as session:
        title = Title(
            title="Dashboard Title",
            author="Author",
            language="ca",
            duration_sec=3600,
            price_retail=9.99,
            currency="EUR",
            abs_share_code="dashboard-share",
        )
        session.add(title)
        session.commit()
        session.refresh(title)
        title_id = title.id
        title_share = title.abs_share_code

        owner = User(email="owner@example.com", password_hash="hash", name="Owner")
        borrower = User(email="borrower@example.com", password_hash="hash", name="Borrower")
        session.add(owner)
        session.add(borrower)
        session.commit()
        session.refresh(owner)
        session.refresh(borrower)

        recent_claim = Card(
            qr=f"CLAIM-{uuid4()}",
            title_id=title.id,
            owner_user_id=owner.id,
            user_state=1,
            claimed_at=now - timedelta(days=5),
        )
        recent_loan = Card(
            qr=f"LOAN-{uuid4()}",
            title_id=title.id,
            owner_user_id=owner.id,
            borrower_user_id=borrower.id,
            user_state=2,
            claimed_at=now - timedelta(days=2),
            lent_at=now - timedelta(days=1),
        )
        old_claim = Card(
            qr=f"OLD-{uuid4()}",
            title_id=title.id,
            owner_user_id=owner.id,
            user_state=1,
            claimed_at=now - timedelta(days=50),
        )
        untouched = Card(
            qr=f"FREE-{uuid4()}",
            title_id=title.id,
        )
        session.add_all([recent_claim, recent_loan, old_claim, untouched])
        session.commit()

    return SimpleNamespace(id=title_id, abs_share_code=title_share)


def test_admin_dashboard_includes_activation_and_loan_metrics():
    _seed_data()

    response = client.get("/api/v1/admin/dashboard", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200

    payload = response.json()
    assert payload["totals"]["users"] == 2
    assert payload["totals"]["titles"] == 1
    assert payload["totals"]["cards"] == 4
    assert payload["totals"]["claimed_cards"] == 3
    assert payload["totals"]["active_loans"] == 1
    assert payload["activations_last_30_days"] == 2
    assert payload["loans_last_30_days"] == 1

    assert len(payload["activations_trend"]) == 30
    assert len(payload["loans_trend"]) == 30

    activation_counts = {point["date"]: point["count"] for point in payload["activations_trend"]}
    loan_counts = {point["date"]: point["count"] for point in payload["loans_trend"]}

    today = datetime.now(timezone.utc).date().isoformat()
    assert activation_counts[today] >= 0
    assert loan_counts[today] >= 0

    loan_day = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    assert loan_counts[loan_day] == 1

    activation_day = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    assert activation_counts[activation_day] >= 1


def test_admin_titles_listing_and_share_lookup():
    title = _seed_data()

    list_response = client.get(
        "/api/v1/admin/titles",
        headers={"Authorization": "Bearer test"},
    )
    assert list_response.status_code == 200
    titles = list_response.json()
    assert any(item["abs_share_code"] == "dashboard-share" for item in titles)

    lookup_response = client.get(
        f"/api/v1/admin/titles/by-share/{title.abs_share_code}",
        headers={"Authorization": "Bearer test"},
    )
    assert lookup_response.status_code == 200
    payload = lookup_response.json()
    assert payload["id"] == title.id

    encoded_url = quote("https://example.test/share/dashboard-share", safe="")
    url_lookup = client.get(
        f"/api/v1/admin/titles/by-share/{encoded_url}",
        headers={"Authorization": "Bearer test"},
    )
    assert url_lookup.status_code == 200
    assert url_lookup.json()["id"] == title.id

    missing = client.get(
        "/api/v1/admin/titles/by-share/not-a-real-share",
        headers={"Authorization": "Bearer test"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "TITLE_NOT_FOUND_FOR_SHARE"


def teardown_module(_module):
    app.dependency_overrides.pop(get_current_config_superuser, None)
    if DATABASE_FILE.exists():
        DATABASE_FILE.unlink()
