import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.db import engine
from app.models import Card, Title


client = TestClient(app)


def _ensure_title(session: Session) -> Title:
    title = session.exec(select(Title)).first()
    if title:
        return title

    title = Title(
        title="Sample",
        author="Author",
        language="ca",
        duration_sec=3600,
        price_retail=12.34,
        currency="EUR",
        abs_share_code="sample-share",
    )
    session.add(title)
    session.commit()
    session.refresh(title)
    return title


def test_lend_auto_expires():
    previous = os.environ.get("LEND_TTL_HOURS")
    os.environ["LEND_TTL_HOURS"] = "1"
    try:
        with Session(engine) as session:
            title = _ensure_title(session)
            qr = f"EXP-{uuid.uuid4()}"
            card = Card(qr=qr, title_id=title.id)
            session.add(card)
            session.commit()

        client.post("/api/v1/register", json={"email": "owner@exp.com", "password": "pass"})
        owner_login = client.post(
            "/api/v1/login", data={"username": "owner@exp.com", "password": "pass"}
        )
        owner_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}

        client.post("/api/v1/register", json={"email": "borrower@exp.com", "password": "pass"})
        borrower_login = client.post(
            "/api/v1/login", data={"username": "borrower@exp.com", "password": "pass"}
        )
        borrower_headers = {"Authorization": f"Bearer {borrower_login.json()['access_token']}"}

        client.post(f"/api/v1/claim/{qr}", params={"owner_email": "owner@exp.com"}, headers=owner_headers)
        client.post(
            f"/api/v1/lend/{qr}",
            json={"borrower_email": "borrower@exp.com"},
            headers=owner_headers,
        )

        with Session(engine) as session:
            card = session.get(Card, qr)
            card.lent_at = datetime.now(timezone.utc) - timedelta(hours=2)
            session.add(card)
            session.commit()

        status = client.get(f"/api/v1/abook/{qr}/status", headers=borrower_headers)
        assert status.status_code == 200
        payload = status.json()
        assert payload["status"] == 1
        assert payload["borrower_email"] is None
    finally:
        if previous is None:
            os.environ.pop("LEND_TTL_HOURS", None)
        else:
            os.environ["LEND_TTL_HOURS"] = previous
