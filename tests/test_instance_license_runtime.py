"""End-to-end customer runtime gate for signed instance licenses."""
import base64
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.instance_licensing import sign_license_token
from app.main import app


def _register(client):
    suffix = uuid.uuid4().hex[:10]
    response = client.post("/api/register", json={
        "company_name": f"Signed Instance {suffix}",
        "industry": "distribution",
        "email": f"{suffix}@example.test",
        "password": "secure-test-password-2026",
    })
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def _keypair():
    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return (
        base64.b64encode(private_bytes).decode("ascii"),
        base64.b64encode(public_bytes).decode("ascii"),
    )


def _configure_instance(monkeypatch, tmp_path, public_key):
    monkeypatch.setenv("LEADORA_ENFORCE_INSTANCE_CONFIG", "1")
    monkeypatch.setenv("LEADORA_INSTANCE_ID", "runtime-customer-alpha")
    monkeypatch.setenv("LEADORA_CUSTOMER_REF", "runtime-contract-alpha")
    monkeypatch.setenv("LEADORA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LEADORA_DB", str(tmp_path / "leadora.db"))
    monkeypatch.setenv("LEADORA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("LEADORA_LICENSE_CACHE_PATH", str(tmp_path / "license" / "license.json"))
    monkeypatch.setenv("LEADORA_LICENSE_PUBLIC_KEY", public_key)
    monkeypatch.setenv("LEADORA_LICENSE_GRACE_DAYS", "14")
    monkeypatch.setenv("LEADORA_SECRET", "runtime-test-secret-that-is-at-least-32-characters")


def _license(private_key, customer_ref="runtime-contract-alpha"):
    now = datetime.now(timezone.utc)
    return sign_license_token({
        "schema_version": 1,
        "license_id": "lic-runtime-test",
        "instance_id": "runtime-customer-alpha",
        "customer_ref": customer_ref,
        "edition": "business",
        "modules": ["distribution", "accounting", "prospecting"],
        "issued_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
        "offline_grace_days": 14,
    }, private_key)


def test_customer_business_routes_require_and_accept_matching_signed_license(monkeypatch, tmp_path):
    client = TestClient(app)
    headers = _register(client)
    private_key, public_key = _keypair()
    _configure_instance(monkeypatch, tmp_path, public_key)

    blocked = client.get("/api/finance/entries", headers=headers)
    assert blocked.status_code == 402

    token = _license(private_key)
    imported = client.post(
        "/api/account/license/import",
        headers=headers,
        json={"license_token": token},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["status"] == "active"

    license_path = tmp_path / "license" / "license.json"
    assert license_path.is_file()
    assert os.stat(license_path).st_mode & 0o777 == 0o600
    assert client.get("/api/account/license", headers=headers).json()["status"] == "active"
    assert client.get("/api/finance/entries", headers=headers).status_code == 200


def test_signed_license_for_another_customer_is_rejected(monkeypatch, tmp_path):
    client = TestClient(app)
    headers = _register(client)
    private_key, public_key = _keypair()
    _configure_instance(monkeypatch, tmp_path, public_key)

    imported = client.post(
        "/api/account/license/import",
        headers=headers,
        json={"license_token": _license(private_key, "different-customer")},
    )
    assert imported.status_code == 403
    assert not (tmp_path / "license" / "license.json").exists()
