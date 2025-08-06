import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_stop_lend():
    qr = f"SL-{uuid.uuid4()}"

    # Registra i fa login del propietari
    client.post("/api/v1/register", json={"email": "p@b.com", "password": "abc"})
    login1 = client.post("/api/v1/login", data={"username": "p@b.com", "password": "abc"})
    token1 = login1.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    # Claim
    client.post(f"/api/v1/claim/{qr}", params={"owner_email": "p@b.com"}, headers=headers1)

    # Registra i login del prestatari
    client.post("/api/v1/register", json={"email": "x@y.com", "password": "xyz"})
    login2 = client.post("/api/v1/login", data={"username": "x@y.com", "password": "xyz"})
    token2 = login2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # Lend
    client.post(f"/api/v1/lend/{qr}", json={"borrower_email": "x@y.com"}, headers=headers1)

    # Stop lend (recupera el llibre)
    r = client.post(f"/api/v1/abook/{qr}/stop-lend", headers=headers1)
    assert r.status_code == 200
    assert r.json()["message"] == "Préstec aturat"

    # Verifica que un altre intent no autoritzat falla
    r2 = client.post(f"/api/v1/abook/{qr}/stop-lend", headers=headers2)
    assert r2.status_code == 403
