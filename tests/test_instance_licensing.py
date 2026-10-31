"""Offline-verifiable, per-installation license contract tests."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.instance_licensing import (
    LicenseValidationError,
    sign_license_token,
    verify_license_token,
)


def keypair():
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


def claim(**overrides):
    issued = datetime(2026, 10, 31, 10, 0, tzinfo=timezone.utc)
    payload = {
        "schema_version": 1,
        "license_id": "lic-test-001",
        "instance_id": "customer-alpha",
        "customer_ref": "cust-alpha",
        "edition": "business",
        "modules": ["distribution", "accounting", "prospecting"],
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(days=365)).isoformat(),
        "offline_grace_days": 14,
    }
    payload.update(overrides)
    return payload


def test_license_is_signed_and_bound_to_exact_customer_instance():
    private_key, public_key = keypair()
    token = sign_license_token(claim(), private_key)

    verified = verify_license_token(
        token,
        public_key,
        "customer-alpha",
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )

    assert verified["status"] == "active"
    assert verified["instance_id"] == "customer-alpha"
    assert verified["modules"] == ["distribution", "accounting", "prospecting"]


def test_license_cannot_be_reused_by_another_customer_instance():
    private_key, public_key = keypair()
    token = sign_license_token(claim(), private_key)

    with pytest.raises(LicenseValidationError, match="instance"):
        verify_license_token(
            token,
            public_key,
            "customer-beta",
            now=datetime(2026, 11, 1, tzinfo=timezone.utc),
        )


def test_license_allows_bounded_offline_grace_after_expiry():
    private_key, public_key = keypair()
    issued = datetime(2026, 10, 1, tzinfo=timezone.utc)
    token = sign_license_token(
        claim(
            issued_at=issued.isoformat(),
            expires_at=(issued + timedelta(days=30)).isoformat(),
            offline_grace_days=14,
        ),
        private_key,
    )

    result = verify_license_token(
        token,
        public_key,
        "customer-alpha",
        now=issued + timedelta(days=35),
    )
    assert result["status"] == "grace"


def test_license_is_rejected_after_offline_grace_ends():
    private_key, public_key = keypair()
    issued = datetime(2026, 10, 1, tzinfo=timezone.utc)
    token = sign_license_token(
        claim(
            issued_at=issued.isoformat(),
            expires_at=(issued + timedelta(days=30)).isoformat(),
            offline_grace_days=14,
        ),
        private_key,
    )

    with pytest.raises(LicenseValidationError, match="expired"):
        verify_license_token(
            token,
            public_key,
            "customer-alpha",
            now=issued + timedelta(days=45),
        )


def test_modified_license_payload_fails_signature_verification():
    private_key, public_key = keypair()
    token = sign_license_token(claim(), private_key)
    encoded_payload, signature = token.split(".", 1)
    payload = json.loads(base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4)))
    payload["modules"] = ["owner-console"]
    tampered = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=") + "." + signature

    with pytest.raises(LicenseValidationError, match="signature"):
        verify_license_token(
            tampered,
            public_key,
            "customer-alpha",
            now=datetime(2026, 11, 1, tzinfo=timezone.utc),
        )


def test_customer_license_verifier_requires_public_key_only():
    private_key, public_key = keypair()
    token = sign_license_token(claim(), private_key)
    result = verify_license_token(
        token,
        public_key,
        "customer-alpha",
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    assert result["license_id"] == "lic-test-001"
    assert "private_key" not in result
