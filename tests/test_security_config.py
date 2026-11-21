import pytest

from app.security_config import load_leadora_secret


def test_production_rejects_missing_secret():
    with pytest.raises(RuntimeError, match="LEADORA_SECRET"):
        load_leadora_secret("production", "")


def test_production_rejects_short_secret():
    with pytest.raises(RuntimeError, match="32 characters"):
        load_leadora_secret("production", "too-short")


def test_all_environments_reject_explicit_short_secret():
    with pytest.raises(RuntimeError, match="32 characters"):
        load_leadora_secret("test", "too-short")


def test_development_uses_distinct_ephemeral_secrets_when_unset():
    first = load_leadora_secret("development", None)
    second = load_leadora_secret("development", None)
    assert len(first) >= 32
    assert first != second


def test_valid_secret_is_trimmed_and_preserved():
    secret = "L" * 48
    assert load_leadora_secret("production", f"  {secret}  ") == secret


def test_environment_is_case_insensitive():
    with pytest.raises(RuntimeError, match="LEADORA_SECRET"):
        load_leadora_secret("PRODUCTION", None)
