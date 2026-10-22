"""Security and regression tests for LEADORA's tenant-scoped API.

The database is isolated to a temporary file before importing the application.
These tests never connect to production or touch the Railway volume.
"""
import os
import tempfile
from pathlib import Path

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="leadora-tests-"))
os.environ["LEADORA_DB"] = str(_TEST_ROOT / "test.db")
os.environ["LEADORA_ENV"] = "test"
os.environ["LEADORA_SECRET"] = "test-secret-that-is-long-enough-for-regression-tests"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def register(company, email):
    response = client.post("/api/register", json={
        "company_name": company,
        "industry": "retail",
        "email": email,
        "password": "A-strong-test-password-2026",
    })
    assert response.status_code == 200, response.text
    return response.json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_and_security_headers():
    response = client.get("/api/health", headers={"x-forwarded-proto": "https"})
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["strict-transport-security"].startswith("max-age=")


def test_private_api_rejects_missing_or_invalid_token():
    assert client.get("/api/products").status_code == 401
    assert client.get("/api/products", headers=auth("not-a-real-token")).status_code == 401


def test_register_rejects_invalid_input():
    response = client.post("/api/register", json={
        "company_name": "X",
        "industry": "retail",
        "email": "not-an-email",
        "password": "short",
    })
    assert response.status_code == 422


def test_products_are_isolated_between_tenants_and_ids():
    token_a = register("Company A", "a@example.test")
    token_b = register("Company B", "b@example.test")

    created = client.post("/api/products", headers=auth(token_a), json={
        "sku": "SKU-1", "name": "Private item", "price": 12.5, "stock": 3,
    })
    assert created.status_code == 200, created.text
    product_id = created.json()["id"]

    assert client.get("/api/products", headers=auth(token_b)).json() == []
    assert client.put(f"/api/products/{product_id}", headers=auth(token_b), json={
        "sku": "SKU-CHANGED", "name": "Unauthorized edit", "price": 0, "stock": 0,
    }).status_code == 404
    assert client.delete(f"/api/products/{product_id}", headers=auth(token_b)).status_code == 404

    own = client.get("/api/products", headers=auth(token_a)).json()
    assert len(own) == 1
    assert own[0]["name"] == "Private item"


def test_invalid_product_values_are_rejected():
    token = register("Company C", "c@example.test")
    response = client.post("/api/products", headers=auth(token), json={
        "sku": "SKU-BAD", "name": "Invalid price", "price": -10, "stock": 1,
    })
    assert response.status_code == 422


def test_tenant_backup_does_not_include_user_credentials():
    token = register("Company Backup", "backup@example.test")
    client.post("/api/products", headers=auth(token), json={
        "sku": "SAFE-1", "name": "Backup item", "price": 5, "stock": 2,
    })
    response = client.get("/api/backup.json", headers=auth(token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "leadora-tenant-backup-v2"
    assert "users" not in payload["tables"]
    assert "login_attempts" not in payload["tables"]
    assert any(row["sku"] == "SAFE-1" for row in payload["products"])
    assert "password_hash" not in response.text
    assert "LEADORA_SECRET" not in response.text
