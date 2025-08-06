import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_lend():
    client.post("/api/v1/register", json={"email": "o@b.com", "password": "abc"})
    login = client.post("/api/v1/login", data={"username": "o@b.com", "password": "abc"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    qr = f"LD-{uuid.uuid4()}"
    client.post(f"/api/v1/claim/{qr}", params={"owner_email": "o@b.com"}, headers=headers)
    r = client.post(f"/api/v1/lend/{qr}", json={"borrower_email": "x@y.com"}, headers=headers)
    assert r.status_code == 200
