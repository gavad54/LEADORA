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
    assert "microphone=(self)" in response.headers["permissions-policy"]
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
    response = client.get("/api/backup/full.json", headers=auth(token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "leadora-tenant-backup-v2"
    assert "users" not in payload["tables"]
    assert "login_attempts" not in payload["tables"]
    assert any(row["sku"] == "SAFE-1" for row in payload["tables"]["products"])
    assert "password_hash" not in response.text
    assert "LEADORA_SECRET" not in response.text


def test_logout_revokes_the_bearer_token_server_side():
    token = register("Logout Revocation Company", "logout-revocation@example.test")
    headers = auth(token)
    assert client.get("/api/products", headers=headers).status_code == 200

    logged_out = client.post("/api/logout", headers=headers)
    assert logged_out.status_code == 200, logged_out.text
    assert logged_out.json()["ok"] is True

    # Clearing localStorage alone is not enough: the previously issued bearer token
    # must no longer authorize API requests after the server confirms logout.
    assert client.get("/api/products", headers=headers).status_code == 401
    assert client.post("/api/logout", headers=headers).status_code == 401


def test_customers_are_isolated_between_tenants_and_ids():
    token_a = register("Customer Company A", "customer-a@example.test")
    token_b = register("Customer Company B", "customer-b@example.test")

    created = client.post("/api/customers", headers=auth(token_a), json={
        "name": "Private customer", "phone": "12345",
    })
    assert created.status_code == 200, created.text
    customer_id = created.json()["id"]

    assert client.get("/api/customers", headers=auth(token_b)).json() == []
    assert client.put(f"/api/customers/{customer_id}", headers=auth(token_b), json={
        "name": "Unauthorized edit", "phone": "99999",
    }).status_code == 404
    assert client.delete(f"/api/customers/{customer_id}", headers=auth(token_b)).status_code == 404

    own = client.get("/api/customers", headers=auth(token_a)).json()
    assert len(own) == 1
    assert own[0]["name"] == "Private customer"


def test_bank_accounts_are_tenant_scoped_and_account_numbers_are_masked():
    token_a = register("Bank Company A", "bank-a@example.test")
    token_b = register("Bank Company B", "bank-b@example.test")

    created = client.post("/api/bank-accounts", headers=auth(token_a), json={
        "label": "Business account",
        "institution": "Test Bank",
        "account_holder": "Company A",
        "iban_masked": "DE89370400440532013000",
        "currency": "EUR",
        "is_default": True,
        "provider": "manual",
    })
    assert created.status_code == 200, created.text
    account_id = created.json()["id"]

    own = client.get("/api/bank-accounts", headers=auth(token_a))
    assert own.status_code == 200
    assert len(own.json()) == 1
    assert own.json()[0]["iban_masked"].endswith("3000")
    assert "DE89370400440532013000" not in own.text

    assert client.get("/api/bank-accounts", headers=auth(token_b)).json() == []
    assert client.delete(f"/api/bank-accounts/{account_id}", headers=auth(token_b)).status_code == 404
    assert len(client.get("/api/bank-accounts", headers=auth(token_a)).json()) == 1


def test_platform_license_management_rejects_regular_tenant_users():
    token = register("License Tenant", "license-tenant@example.test")
    response = client.get("/api/platform/licenses", headers=auth(token))
    assert response.status_code == 403

def test_full_database_backup_is_owner_only_and_can_be_verified_offline(monkeypatch, tmp_path):
    token = register("Platform Backup Owner", "platform-owner-backup@example.test")
    user_id = token.split(".", 1)[0].split(":", 1)[0]
    monkeypatch.setenv("LEADORA_OWNER_USER_IDS", user_id)
    monkeypatch.setenv("LEADORA_BACKUP_DIR", str(tmp_path / "backups"))
    client.post("/api/products", headers=auth(token), json={
        "sku": "DB-BACKUP-1", "name": "Backup validation item", "price": 7, "stock": 4,
    })

    created = client.post("/api/platform/backup/database", headers=auth(token))
    assert created.status_code == 200, created.text
    metadata = created.json()
    assert metadata["status"] == "verified"
    assert metadata["integrity_check"] == "ok"
    assert metadata["bytes"] > 0
    assert len(metadata["sha256"]) == 64

    downloaded = client.get(metadata["download_path"], headers=auth(token))
    assert downloaded.status_code == 200
    assert downloaded.content[:16] == b"SQLite format 3\x00"
    assert len(downloaded.content) == metadata["bytes"]

    verified = client.post("/api/platform/backup/verify", headers=auth(token),
                           files={"file": ("leadora-backup.sqlite3", downloaded.content, "application/vnd.sqlite3")})
    assert verified.status_code == 200, verified.text
    assert verified.json()["integrity_check"] == "ok"
    assert verified.json()["production_database_changed"] is False


def test_full_database_backup_endpoints_reject_regular_tenant(monkeypatch):
    token = register("Regular Backup Tenant", "regular-backup@example.test")
    monkeypatch.setenv("LEADORA_OWNER_USER_IDS", "not-the-user")
    assert client.post("/api/platform/backup/database", headers=auth(token)).status_code == 403
    assert client.post("/api/platform/backup/verify", headers=auth(token),
                       files={"file": ("backup.sqlite3", b"not a database", "application/octet-stream")}).status_code == 403
