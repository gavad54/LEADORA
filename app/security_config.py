"""Fail-closed LEADORA signing-secret configuration."""

import secrets


def load_leadora_secret(app_env: str | None, configured_secret: str | None) -> str:
    """Require strong configured keys and use an ephemeral key only outside production."""
    environment = (app_env or "development").strip().lower()
    normalized_secret = (configured_secret or "").strip()

    if normalized_secret:
        if len(normalized_secret) < 32:
            raise RuntimeError("LEADORA_SECRET must contain at least 32 characters.")
        return normalized_secret

    if environment == "production":
        raise RuntimeError("LEADORA_SECRET is required in production.")

    return secrets.token_urlsafe(48)
