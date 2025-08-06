
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_abook_status_ok():
    qr = f"ST-{uuid.uuid4()}"
    client.post(f"/api/v1/claim/{qr}", params={"owner_email": "a@b.com"})
    response = client.get(f"/api/v1/abook/{qr}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["qr"] == qr
    assert data["status"] == 1
    assert data["owner_email"] == "a@b.com"
    assert data["status_label"] == "Reclamat"

def test_abook_status_not_found():
    qr = "ST-notfound"
    response = client.get(f"/api/v1/abook/{qr}/status")
    assert response.status_code == 404
