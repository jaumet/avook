import os
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import sys
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

os.environ.setdefault("BACKUP_RUN_ON_START", "0")

DATABASE_FILE = Path("test_promo_codes.db")
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
from app.auth import get_current_user  # noqa: E402
from app.models import Title, User, PromoCode, PromoRedemption, Card  # noqa: E402

app.dependency_overrides[get_current_config_superuser] = lambda: {"sub": "tests"}

client = TestClient(app)


def _create_title(session: Session) -> Title:
    title = Title(
        title="Promo Title",
        author="Author",
        language="ca",
        duration_sec=1800,
        price_retail=12.0,
        currency="EUR",
    )
    session.add(title)
    session.commit()
    session.refresh(title)
    return title


def _create_user(session: Session) -> User:
    user = User(
        email=f"user-{uuid4()}@example.com",
        password_hash="hash",
        name="Promo User",
        location="Barcelona",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_promo_code_creation_and_redemption_flow():
    with Session(app_db.engine) as session:
        title = _create_title(session)
        user = _create_user(session)
        title_id = title.id

    payload = {
        "code": "PRESS2024",
        "title_id": title_id,
        "label": "Premsa",
        "kind": "press",
        "campaign": "press-tour",
        "max_uses": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }

    response = client.post(
        "/api/v1/admin/promo-codes",
        json=payload,
        headers={"Authorization": "Bearer test"},
    )
    assert response.status_code == 200
    created = response.json()
    assert created["code"] == payload["code"]
    assert created["remaining_uses"] == 1

    app.dependency_overrides[get_current_user] = lambda: user

    redeem_response = client.post(
        "/api/v1/promo/redeem",
        json={"code": payload["code"], "device_id": "ios", "source": "press-kit"},
    )
    assert redeem_response.status_code == 200
    redeemed = redeem_response.json()
    assert redeemed["title_id"] == title_id
    assert redeemed["remaining_uses"] == 0
    assert redeemed["message"] == "PROMO_REDEEMED"

    with Session(app_db.engine) as session:
        promo = session.get(PromoCode, payload["code"])
        assert promo is not None
        assert promo.usage_count == 1

        redemption = session.exec(
            select(PromoRedemption).where(
                PromoRedemption.promo_code_code == payload["code"]
            )
        ).one()
        assert redemption.source == "press-kit"
        assert redemption.device_id == "ios"

        card = session.get(Card, redeemed["qr"])
        assert card is not None
        assert card.owner_user_id == user.id
        assert card.promo_code == payload["code"]
        assert card.campaign == "press-tour"
        assert card.user_state == 1

    detail = client.get(
        f"/api/v1/admin/promo-codes/{payload['code']}",
        headers={"Authorization": "Bearer test"},
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["usage_count"] == 1
    assert len(detail_body["redemptions"]) == 1
    assert detail_body["redemptions"][0]["qr"] == redeemed["qr"]

    app.dependency_overrides.pop(get_current_user, None)


def teardown_module(_module):
    app.dependency_overrides.pop(get_current_config_superuser, None)
    client.close()
    if DATABASE_FILE.exists():
        DATABASE_FILE.unlink()
