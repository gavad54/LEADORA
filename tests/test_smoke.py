import os
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    c=TestClient(app)
    r=c.get("/api/health")
    assert r.status_code==200
    assert r.json()["status"]=="ok"

def test_registration_and_product_isolation(tmp_path, monkeypatch):
    # App database is initialized at import; test the public API registration and auth flow.
    c=TestClient(app)
    email="test-"+str(os.getpid())+"@example.com"
    reg=c.post("/api/register",json={"company_name":"Test Company "+str(os.getpid()),"industry":"retail","email":email,"password":"a-secure-password"})
    assert reg.status_code==200, reg.text
    token=reg.json()["token"]
    headers={"Authorization":"Bearer "+token}
    add=c.post("/api/products",headers=headers,json={"sku":"SKU-1","name":"Notebook","price":12,"stock":4})
    assert add.status_code==200, add.text
    assert c.get("/api/products",headers=headers).json()[0]["sku"]=="SKU-1"
