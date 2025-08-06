
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_save_progress_new():
    qr = f"PR-{uuid.uuid4()}"
    client.post(f"/api/v1/claim/{qr}", params={"owner_email": "a@b.com"})
    response = client.post(f"/api/v1/abook/{qr}/progress", json={"position": 123.45})
    assert response.status_code == 200
    data = response.json()
    assert data["qr"] == qr
    assert data["position"] == 123.45

def test_save_progress_update():
    qr = f"PR-{uuid.uuid4()}"
    client.post(f"/api/v1/claim/{qr}", params={"owner_email": "a@b.com"})
    client.post(f"/api/v1/abook/{qr}/progress", json={"position": 100.0})
    response = client.post(f"/api/v1/abook/{qr}/progress", json={"position": 200.0})
    assert response.status_code == 200
    data = response.json()
    assert data["position"] == 200.0
