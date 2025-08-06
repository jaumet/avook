import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_claim_once():
    client.post("/api/v1/register", json={"email": "jaume@example.com", "password": "1234"})
    login = client.post("/api/v1/login", data={"username": "jaume@example.com", "password": "1234"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    qr = f"TEST-{uuid.uuid4()}"
    r = client.post(f"/api/v1/claim/{qr}", params={"owner_email": "jaume@example.com"}, headers=headers)
    assert r.status_code == 200
