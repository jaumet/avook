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

    r = client.get(f"/api/v1/play-auth/{qr}", headers=headers2)
    assert r.status_code == 200
    assert "signed_url" in r.json()
