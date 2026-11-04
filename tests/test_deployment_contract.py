"""Guardrails for independent customer and owner-control deployment templates."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_customer_worker_receives_all_required_instance_license_paths():
    compose = (ROOT / "deploy/customer-instance/compose.yaml").read_text(encoding="utf-8")
    worker = compose.split("  leadora-worker:", 1)[1]
    assert "LEADORA_ENFORCE_INSTANCE_CONFIG: \"1\"" in worker
    assert "LEADORA_DATA_DIR: /data" in worker
    assert "LEADORA_DB: /data/leadora.db" in worker
    assert "LEADORA_BACKUP_DIR: /data/backups" in worker
    assert "LEADORA_LICENSE_CACHE_PATH: /data/license/license.json" in worker
    assert "LEADORA_LICENSE_PUBLIC_KEY" not in worker  # supplied only by the protected env_file


def test_customer_web_and_worker_share_only_the_same_customer_volume():
    compose = (ROOT / "deploy/customer-instance/compose.yaml").read_text(encoding="utf-8")
    assert compose.count("- customer_data:/data") == 2
    assert 'name: leadora-${LEADORA_INSTANCE_ID:?Set a unique LEADORA_INSTANCE_ID}-data' in compose


def test_control_plane_initializes_its_separate_volume_before_dropping_privileges():
    compose = (ROOT / "deploy/control-plane/compose.yaml").read_text(encoding="utf-8")
    assert "owner_control_data:/control-data" in compose
    assert "chown -R appuser:appuser /control-data" in compose
    assert "exec gosu appuser uvicorn app.control_plane:app" in compose
    assert "leadora-data" not in compose
