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

def test_pwa_assets_are_served():
    c = TestClient(app)
    manifest = c.get("/manifest.webmanifest")
    worker = c.get("/service-worker.js")
    icon = c.get("/icon.svg")
    assert manifest.status_code == 200
    assert manifest.json()["display"] == "standalone"
    assert worker.status_code == 200
    assert "serviceWorker" not in worker.text
    assert icon.status_code == 200
    assert "<svg" in icon.text


def test_tenant_isolation_for_products_and_customers():
    c = TestClient(app)
    suffix = str(os.getpid())
    first = c.post("/api/register", json={
        "company_name": "Isolation A " + suffix,
        "industry": "retail",
        "email": "isolation-a-" + suffix + "@example.com",
        "password": "secure-test-password-A",
    })
    second = c.post("/api/register", json={
        "company_name": "Isolation B " + suffix,
        "industry": "retail",
        "email": "isolation-b-" + suffix + "@example.com",
        "password": "secure-test-password-B",
    })
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    headers_a = {"Authorization": "Bearer " + first.json()["token"]}
    headers_b = {"Authorization": "Bearer " + second.json()["token"]}

    assert c.post("/api/products", headers=headers_a, json={
        "sku": "PRIVATE-" + suffix, "name": "Private product", "price": 10, "stock": 3,
    }).status_code == 200
    assert c.post("/api/customers", headers=headers_a, json={
        "name": "Private customer", "phone": "000",
    }).status_code == 200

    assert c.get("/api/products", headers=headers_a).json()
    assert c.get("/api/customers", headers=headers_a).json()
    assert c.get("/api/products", headers=headers_b).json() == []
    assert c.get("/api/customers", headers=headers_b).json() == []
