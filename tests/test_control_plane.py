"""Owner-only control-plane tests; this database must never contain customer business records."""
import base64
import hashlib
import hmac
import struct
import time
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.control_plane import create_app
from app.instance_licensing import verify_license_token


def make_settings():
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
    return {
        "LEADORA_ENV": "test",
        "LEADORA_CONTROL_SECRET": "control-plane-test-secret-32-characters",
        "LEADORA_LICENSE_PRIVATE_KEY": base64.b64encode(private_bytes).decode("ascii"),
        "LEADORA_LICENSE_PUBLIC_KEY": base64.b64encode(public_bytes).decode("ascii"),
        "LEADORA_OWNER_EMAIL": "owner@example.test",
        "LEADORA_OWNER_KEYWORD": "کلیدواژه‌مالک‌اصلی",
        "LEADORA_OWNER_MFA_SECRET": base64.b32encode(b"0123456789abcdef0123").decode("ascii").rstrip("="),
    }


def totp(secret, timestamp=None):
    timestamp = int(time.time() if timestamp is None else timestamp)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = struct.pack(">Q", timestamp // 30)
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1_000_000:06d}"


def owner_headers(client, settings):
    response = client.post("/api/control/auth/owner/login", json={
        "email": settings["LEADORA_OWNER_EMAIL"],
        "keyword": settings["LEADORA_OWNER_KEYWORD"],
        "totp": totp(settings["LEADORA_OWNER_MFA_SECRET"]),
    })
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_owner_requires_persian_keyword_and_independent_totp(tmp_path):
    settings = make_settings()
    client = TestClient(create_app(tmp_path / "control.sqlite3", settings=settings))

    denied = client.post("/api/control/auth/owner/login", json={
        "email": settings["LEADORA_OWNER_EMAIL"],
        "keyword": settings["LEADORA_OWNER_KEYWORD"],
        "totp": "000000",
    })
    assert denied.status_code == 401

    headers = owner_headers(client, settings)
    identity = client.get("/api/control/owner/identity", headers=headers)
    assert identity.status_code == 200
    assert identity.json()["role"] == "owner"


def test_staff_permissions_are_scoped_and_revocable(tmp_path):
    settings = make_settings()
    client = TestClient(create_app(tmp_path / "control.sqlite3", settings=settings))
    owner = owner_headers(client, settings)

    invite = client.post("/api/control/staff/invitations", headers=owner, json={
        "email": "auditor@example.test",
        "scopes": ["licenses:read", "audit:read"],
    })
    assert invite.status_code == 200, invite.text
    activated = client.post("/api/control/staff/activate", json={
        "invitation_code": invite.json()["invitation_code"],
        "password": "staff-password-strong-2026",
    })
    assert activated.status_code == 200, activated.text

    login = client.post("/api/control/auth/staff/login", json={
        "email": "auditor@example.test",
        "password": "staff-password-strong-2026",
    })
    assert login.status_code == 200, login.text
    staff = {"Authorization": "Bearer " + login.json()["access_token"]}

    assert client.get("/api/control/licenses", headers=staff).status_code == 200
    denied = client.post("/api/control/licenses", headers=staff, json={})
    assert denied.status_code == 403

    staff_id = activated.json()["staff_id"]
    revoked = client.patch(f"/api/control/staff/{staff_id}", headers=owner, json={"active": False})
    assert revoked.status_code == 200, revoked.text
    assert client.get("/api/control/licenses", headers=staff).status_code == 401


def test_owner_issues_instance_bound_signed_license_and_can_revoke_it(tmp_path):
    settings = make_settings()
    client = TestClient(create_app(tmp_path / "control.sqlite3", settings=settings))
    owner = owner_headers(client, settings)

    issued = client.post("/api/control/licenses", headers=owner, json={
        "instance_id": "customer-alpha",
        "customer_ref": "customer-contract-001",
        "edition": "business",
        "modules": ["distribution", "accounting", "prospecting"],
        "expires_at": "2030-01-01T00:00:00+00:00",
        "offline_grace_days": 14,
    })
    assert issued.status_code == 200, issued.text
    token = issued.json()["license_token"]
    verified = verify_license_token(
        token,
        settings["LEADORA_LICENSE_PUBLIC_KEY"],
        "customer-alpha",
        now=datetime(2029, 1, 1, tzinfo=timezone.utc),
    )
    assert verified["status"] == "active"
    assert verified["customer_ref"] == "customer-contract-001"

    wrong_instance = client.post("/api/control/licenses", headers=owner, json={
        "instance_id": "customer-alpha",
        "customer_ref": "different-customer",
        "edition": "business",
        "modules": ["distribution"],
        "expires_at": "2030-01-01T00:00:00+00:00",
        "offline_grace_days": 14,
    })
    assert wrong_instance.status_code == 409

    license_id = issued.json()["license_id"]
    revoked = client.post(f"/api/control/licenses/{license_id}/revoke", headers=owner)
    assert revoked.status_code == 200
    rows = client.get("/api/control/licenses", headers=owner).json()
    assert rows[0]["status"] == "revoked"


def test_control_plane_database_contains_no_customer_business_tables(tmp_path):
    settings = make_settings()
    database = tmp_path / "control.sqlite3"
    client = TestClient(create_app(database, settings=settings))
    owner_headers(client, settings)

    import sqlite3
    with sqlite3.connect(database) as conn:
        names = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert "control_users" in names
    assert "control_licenses" in names
    assert "tenants" not in names
    assert "products" not in names
    assert "customers" not in names
    assert "users" not in names


def test_owner_login_is_rate_limited_after_repeated_invalid_attempts(tmp_path):
    settings = make_settings()
    client = TestClient(create_app(tmp_path / "control.sqlite3", settings=settings))
    payload = {
        "email": settings["LEADORA_OWNER_EMAIL"],
        "keyword": "wrong-persian-keyword",
        "totp": "000000",
    }
    for _ in range(5):
        assert client.post("/api/control/auth/owner/login", json=payload).status_code == 401
    limited = client.post("/api/control/auth/owner/login", json=payload)
    assert limited.status_code == 429
