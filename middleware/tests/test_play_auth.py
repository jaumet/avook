import uuid
from urllib.parse import urlparse, parse_qs

from fastapi.testclient import TestClient
from app.main import app
from app.api.v1 import _get_abs_client


class _DummyABSClient:
    def ensure_share_available(self, share_code: str):
        return {
            "streamUrl": f"http://abs.local/stream/{share_code}",
            "webUrl": f"http://abs.local/book/{share_code}",
        }


app.dependency_overrides[_get_abs_client] = lambda: _DummyABSClient()

client = TestClient(app)

def test_play_auth():
    qr = f"PA-{uuid.uuid4()}"

    client.post("/api/v1/register", json={"email": "a@b.com", "password": "123"})
    login1 = client.post("/api/v1/login", data={"username": "a@b.com", "password": "123"})
    token1 = login1.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    client.post(f"/api/v1/claim/{qr}", params={"owner_email": "a@b.com"}, headers=headers1)

    client.post("/api/v1/register", json={"email": "c@d.com", "password": "456"})
    login2 = client.post("/api/v1/login", data={"username": "c@d.com", "password": "456"})
    token2 = login2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    client.post(f"/api/v1/lend/{qr}", json={"borrower_email": "c@d.com"}, headers=headers1)

    r = client.get(f"/api/v1/play-auth/{qr}", headers=headers2, params={"device_id": "device-a"})
    assert r.status_code == 200
    assert "signed_url" in r.json()


def test_play_auth_rejects_second_device():
    qr = f"PA2-{uuid.uuid4()}"

    client.post("/api/v1/register", json={"email": "owner@a.com", "password": "123"})
    owner_login = client.post("/api/v1/login", data={"username": "owner@a.com", "password": "123"})
    owner_token = owner_login.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    client.post(f"/api/v1/claim/{qr}", params={"owner_email": "owner@a.com"}, headers=owner_headers)

    client.post("/api/v1/register", json={"email": "borrower@a.com", "password": "456"})
    borrower_login = client.post("/api/v1/login", data={"username": "borrower@a.com", "password": "456"})
    borrower_token = borrower_login.json()["access_token"]
    borrower_headers = {"Authorization": f"Bearer {borrower_token}"}

    client.post(f"/api/v1/lend/{qr}", json={"borrower_email": "borrower@a.com"}, headers=owner_headers)

    first_device = client.get(
        f"/api/v1/play-auth/{qr}",
        headers=borrower_headers,
        params={"device_id": "tablet-1"},
    )
    assert first_device.status_code == 200

    second_device = client.get(
        f"/api/v1/play-auth/{qr}",
        headers=borrower_headers,
        params={"device_id": "phone-2"},
    )
    assert second_device.status_code == 409


def test_proxy_validator_accepts_signed_token():
    qr = f"PA3-{uuid.uuid4()}"

    client.post("/api/v1/register", json={"email": "auth@a.com", "password": "123"})
    owner_login = client.post("/api/v1/login", data={"username": "auth@a.com", "password": "123"})
    owner_token = owner_login.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    client.post(f"/api/v1/claim/{qr}", params={"owner_email": "auth@a.com"}, headers=owner_headers)

    client.post("/api/v1/register", json={"email": "borrow@a.com", "password": "456"})
    borrower_login = client.post("/api/v1/login", data={"username": "borrow@a.com", "password": "456"})
    borrower_token = borrower_login.json()["access_token"]
    borrower_headers = {"Authorization": f"Bearer {borrower_token}"}

    client.post(f"/api/v1/lend/{qr}", json={"borrower_email": "borrow@a.com"}, headers=owner_headers)

    auth_response = client.get(
        f"/api/v1/play-auth/{qr}",
        headers=borrower_headers,
        params={"device_id": "proxy-device"},
    )
    assert auth_response.status_code == 200
    signed_url = auth_response.json()["signed_url"]

    query = parse_qs(urlparse(signed_url).query)

    validation = client.get(
        "/api/v1/proxy/validate",
        params={
            "qr": qr,
            "uid": query["uid"][0],
            "exp": query["exp"][0],
            "sig": query["sig"][0],
            "did": query["did"][0],
        },
    )
    assert validation.status_code == 200
    body = validation.json()
    assert body["ok"] is True
    assert body["qr"] == qr
