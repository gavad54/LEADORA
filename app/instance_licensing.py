"""Offline-verifiable Ed25519 licenses bound to one LEADORA installation.

The signing private key belongs only to the owner-side control plane. Customer
instances receive the public key and a signed claim; they never receive the
private key or call the control plane on every request.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class LicenseValidationError(ValueError):
    """Raised when a signed license is malformed, invalid, or no longer valid."""


_MAX_OFFLINE_GRACE_DAYS = 30
_MAX_TOKEN_BYTES = 16_384
_REQUIRED_FIELDS = {
    "schema_version",
    "license_id",
    "instance_id",
    "customer_ref",
    "edition",
    "modules",
    "issued_at",
    "expires_at",
    "offline_grace_days",
}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > _MAX_TOKEN_BYTES:
        raise LicenseValidationError("license encoding is invalid")
    try:
        return base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, base64.binascii.Error) as exc:
        raise LicenseValidationError("license encoding is invalid") from exc


def _decode_key(value: str, expected_length: int, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise LicenseValidationError(f"{label} is not valid base64") from exc
    if len(decoded) != expected_length:
        raise LicenseValidationError(f"{label} has an invalid length")
    return decoded


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise LicenseValidationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LicenseValidationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise LicenseValidationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_claim(claim: dict[str, Any]) -> tuple[datetime, datetime, int]:
    if not isinstance(claim, dict) or not _REQUIRED_FIELDS.issubset(claim):
        raise LicenseValidationError("license claim is missing required fields")
    if claim["schema_version"] != 1:
        raise LicenseValidationError("unsupported license schema version")
    for field in ("license_id", "instance_id", "customer_ref", "edition"):
        if not isinstance(claim[field], str) or not claim[field].strip():
            raise LicenseValidationError(f"{field} must be a non-empty string")
    modules = claim["modules"]
    if (
        not isinstance(modules, list)
        or not modules
        or any(not isinstance(item, str) or not item.strip() for item in modules)
        or len(set(modules)) != len(modules)
    ):
        raise LicenseValidationError("modules must be a non-empty unique string list")
    grace = claim["offline_grace_days"]
    if isinstance(grace, bool) or not isinstance(grace, int) or not 0 <= grace <= _MAX_OFFLINE_GRACE_DAYS:
        raise LicenseValidationError("offline grace must be between 0 and 30 days")
    issued = _parse_datetime(claim["issued_at"], "issued_at")
    expires = _parse_datetime(claim["expires_at"], "expires_at")
    if expires <= issued:
        raise LicenseValidationError("license expiry must be after issue time")
    return issued, expires, grace


def sign_license_token(claim: dict[str, Any], private_key_b64: str) -> str:
    """Sign a canonical claim with a raw 32-byte Ed25519 private key in base64."""
    _validate_claim(claim)
    private_bytes = _decode_key(private_key_b64, 32, "private key")
    private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    payload = json.dumps(
        claim, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    signature = private_key.sign(payload)
    return f"{_b64encode(payload)}.{_b64encode(signature)}"


def verify_license_token(
    token: str,
    public_key_b64: str,
    expected_instance_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify signature, installation binding, validity, and offline grace.

    Returns a copy of the signed claim with status set to active or grace.
    Expired or misbound claims always fail closed.
    """
    if not isinstance(expected_instance_id, str) or not expected_instance_id.strip():
        raise LicenseValidationError("expected instance id is required")
    if not isinstance(token, str) or len(token) > _MAX_TOKEN_BYTES:
        raise LicenseValidationError("license token is invalid")
    parts = token.split(".")
    if len(parts) != 2:
        raise LicenseValidationError("license token format is invalid")
    payload_bytes = _b64decode(parts[0])
    signature = _b64decode(parts[1])
    if len(signature) != 64:
        raise LicenseValidationError("license signature has an invalid length")
    public_bytes = _decode_key(public_key_b64, 32, "public key")
    try:
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, payload_bytes)
    except InvalidSignature as exc:
        raise LicenseValidationError("license signature verification failed") from exc
    except ValueError as exc:
        raise LicenseValidationError("public key is invalid") from exc

    try:
        claim = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseValidationError("license payload is invalid") from exc
    issued, expires, grace_days = _validate_claim(claim)
    if claim["instance_id"] != expected_instance_id:
        raise LicenseValidationError("license instance binding does not match")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise LicenseValidationError("verification time must include a timezone")
    current = current.astimezone(timezone.utc)
    if issued > current + timedelta(minutes=5):
        raise LicenseValidationError("license issue time is in the future")
    if current <= expires:
        status = "active"
    elif current <= expires + timedelta(days=grace_days):
        status = "grace"
    else:
        raise LicenseValidationError("license expired beyond offline grace")
    return {**claim, "status": status}
