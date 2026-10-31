"""Fail-closed validation for a separately deployed LEADORA customer instance."""
from __future__ import annotations

import base64
import binascii
import os
import re
from pathlib import Path
from typing import Mapping


class InstanceConfigurationError(ValueError):
    """Raised when a customer deployment could share or escape its own storage."""


_INSTANCE_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
_MAX_OFFLINE_GRACE_DAYS = 30


def _absolute_path(value: str, field: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise InstanceConfigurationError(f"{field} must be an absolute path")
    return path.resolve()


def _inside(root: Path, candidate: Path, field: str) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InstanceConfigurationError(f"{field} must stay inside the customer data volume") from exc


def customer_volume_name(instance_id: str) -> str:
    if not isinstance(instance_id, str) or not _INSTANCE_ID_RE.fullmatch(instance_id):
        raise InstanceConfigurationError("instance id must be a lowercase safe slug")
    return f"leadora-{instance_id}-data"


def validate_customer_instance_config(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str | int]:
    """Validate that one installation has a private data volume and public key only."""
    env = os.environ if environ is None else environ
    instance_id = env.get("LEADORA_INSTANCE_ID", "")
    if not isinstance(instance_id, str) or not _INSTANCE_ID_RE.fullmatch(instance_id):
        raise InstanceConfigurationError("instance id must be a lowercase safe slug")

    if env.get("LEADORA_LICENSE_PRIVATE_KEY", "").strip():
        raise InstanceConfigurationError("customer instance must never contain a license signing private key")

    data_root = _absolute_path(env.get("LEADORA_DATA_DIR", ""), "LEADORA_DATA_DIR")
    db_path = _absolute_path(env.get("LEADORA_DB", ""), "LEADORA_DB")
    backup_dir = _absolute_path(env.get("LEADORA_BACKUP_DIR", ""), "LEADORA_BACKUP_DIR")
    license_cache = _absolute_path(
        env.get("LEADORA_LICENSE_CACHE_PATH", ""), "LEADORA_LICENSE_CACHE_PATH"
    )
    for field, path in (
        ("LEADORA_DB", db_path),
        ("LEADORA_BACKUP_DIR", backup_dir),
        ("LEADORA_LICENSE_CACHE_PATH", license_cache),
    ):
        _inside(data_root, path, field)

    secret = env.get("LEADORA_SECRET", "")
    if len(secret) < 32:
        raise InstanceConfigurationError("LEADORA_SECRET must contain at least 32 characters")

    public_key = env.get("LEADORA_LICENSE_PUBLIC_KEY", "")
    try:
        decoded_key = base64.b64decode(public_key, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InstanceConfigurationError("license public key must be valid base64") from exc
    if len(decoded_key) != 32:
        raise InstanceConfigurationError("license public key must contain 32 raw bytes")

    try:
        grace_days = int(env.get("LEADORA_LICENSE_GRACE_DAYS", "14"))
    except (TypeError, ValueError) as exc:
        raise InstanceConfigurationError("offline grace must be an integer from 0 to 30") from exc
    if not 0 <= grace_days <= _MAX_OFFLINE_GRACE_DAYS:
        raise InstanceConfigurationError("offline grace must be an integer from 0 to 30")

    return {
        "instance_id": instance_id,
        "volume_name": customer_volume_name(instance_id),
        "data_dir": str(data_root),
        "db_path": str(db_path),
        "backup_dir": str(backup_dir),
        "license_cache_path": str(license_cache),
        "license_public_key": public_key,
        "offline_grace_days": grace_days,
    }
