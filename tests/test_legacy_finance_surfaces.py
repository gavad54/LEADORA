import os
import subprocess
import sys
from pathlib import Path


def test_legacy_finance_and_accounting_surfaces_are_not_publicly_routed(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "LEADORA_DB": str(tmp_path / "leadora-test.sqlite"),
            "LEADORA_BACKUP_DIR": str(tmp_path / "backups"),
            "LEADORA_SECRET": "test-only-secret-that-is-not-used-in-production",
            "LEADORA_ENV": "test",
        }
    )
    script = r"""
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    for path in (
        "/api/finance/entries",
        "/api/finance/contracts",
        "/api/accounting/accounts",
        "/api/accounting/journals",
        "/finance",
        "/accounting",
        "/static/finance.html",
        "/static/accounting.html",
    ):
        response = client.get(path)
        assert response.status_code == 404, (
            f"{path} must not expose retired finance/accounting UI; "
            f"received HTTP {response.status_code}"
        )

    home = client.get("/")
    assert home.status_code == 200
    assert "location.href='/finance'" not in home.text
    assert "location.href='/accounting'" not in home.text
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
