import uuid
from fastapi.testclient import TestClient
from app.main import app

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
