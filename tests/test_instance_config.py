"""Deployment contract tests for strictly separate customer installations."""
import base64

import pytest

from app.instance_config import InstanceConfigurationError, validate_customer_instance_config


def valid_env(instance_id="customer-alpha"):
    return {
        "LEADORA_INSTANCE_ID": instance_id,
        "LEADORA_CUSTOMER_REF": "customer-contract-alpha",
        "LEADORA_CONTROL_PLANE_URL": "https://control.example.test",
        "LEADORA_DATA_DIR": "/data",
        "LEADORA_DB": "/data/leadora.db",
        "LEADORA_BACKUP_DIR": "/data/backups",
        "LEADORA_LICENSE_CACHE_PATH": "/data/license/license.json",
        "LEADORA_LICENSE_PUBLIC_KEY": base64.b64encode(b"p" * 32).decode("ascii"),
        "LEADORA_SECRET": "x" * 48,
        "LEADORA_LICENSE_GRACE_DAYS": "14",
        "LEADORA_ENFORCE_INSTANCE_CONFIG": "1",
    }


def test_customer_installation_uses_its_own_persistent_data_root():
    config = validate_customer_instance_config(valid_env("customer-alpha"))
    assert config["instance_id"] == "customer-alpha"
    assert config["db_path"] == "/data/leadora.db"
    assert config["backup_dir"] == "/data/backups"
    assert config["license_cache_path"] == "/data/license/license.json"
    assert config["offline_grace_days"] == 14


def test_database_and_backups_cannot_escape_customer_volume():
    env = valid_env()
    env["LEADORA_DB"] = "/shared/leadora.db"
    with pytest.raises(InstanceConfigurationError, match="inside"):
        validate_customer_instance_config(env)


def test_customer_instance_must_never_receive_license_signing_private_key():
    env = valid_env()
    env["LEADORA_LICENSE_PRIVATE_KEY"] = base64.b64encode(b"s" * 32).decode("ascii")
    with pytest.raises(InstanceConfigurationError, match="private key"):
        validate_customer_instance_config(env)


def test_customer_instance_id_must_be_a_safe_unique_slug():
    env = valid_env("../shared")
    with pytest.raises(InstanceConfigurationError, match="instance id"):
        validate_customer_instance_config(env)


def test_public_key_and_offline_grace_are_validated():
    env = valid_env()
    env["LEADORA_LICENSE_PUBLIC_KEY"] = "not-a-key"
    with pytest.raises(InstanceConfigurationError, match="public key"):
        validate_customer_instance_config(env)

    env = valid_env()
    env["LEADORA_LICENSE_GRACE_DAYS"] = "365"
    with pytest.raises(InstanceConfigurationError, match="grace"):
        validate_customer_instance_config(env)


def test_each_customer_gets_a_deterministic_but_distinct_volume_name():
    from app.instance_config import customer_volume_name

    assert customer_volume_name("customer-alpha") == "leadora-customer-alpha-data"
    assert customer_volume_name("customer-beta") == "leadora-customer-beta-data"
    assert customer_volume_name("customer-alpha") != customer_volume_name("customer-beta")
