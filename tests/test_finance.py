import os
import uuid
from fastapi.testclient import TestClient
from app.main import app


def register(client, company, email=None):
    suffix = uuid.uuid4().hex[:10]
    email = email or f"{company.lower().replace(' ', '-')}-{suffix}@example.com"
    response = client.post("/api/register", json={
        "company_name": f"{company} {suffix}",
        "industry": "distribution",
        "email": email,
        "password": "secure-test-password-2026",
    })
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}, response.json()


def test_finance_settings_and_manual_entry_calculation():
    client = TestClient(app)
    headers, _ = register(client, "Finance Test")
    settings = client.put("/api/finance/settings", headers=headers, json={"methods": ["manual", "csv"]})
    assert settings.status_code == 200, settings.text
    assert set(settings.json()["methods"]) == {"manual", "csv"}

    entry = client.post("/api/finance/entries", headers=headers, json={
        "period": "2026-05", "document_ref": "INV-TEST-1", "sales": "1000",
        "discounts": "100", "returns": "50", "cogs": "500",
        "direct_costs": "25", "currency": "IRR",
    })
    assert entry.status_code == 200, entry.text
    duplicate = client.post("/api/finance/entries", headers=headers, json={
        "period": "2026-05", "document_ref": "INV-TEST-1", "sales": "1000",
        "discounts": "100", "returns": "50", "cogs": "500",
        "direct_costs": "25", "currency": "IRR",
    })
    assert duplicate.status_code == 409

    report = client.post("/api/finance/reports/calculate?period=2026-05", headers=headers, json={})
    assert report.status_code == 200, report.text
    assert report.json()["net_sales"] == "850.00"
    assert report.json()["eligible_profit"] == "325.00"
    assert report.json()["owner_share"] == "0.00"


def test_finance_tenant_isolation():
    client = TestClient(app)
    headers_a, _ = register(client, "Finance A")
    headers_b, _ = register(client, "Finance B")
    response = client.post("/api/finance/entries", headers=headers_a, json={
        "period": "2026-06", "document_ref": "A-ONLY", "sales": "500",
        "discounts": "0", "returns": "0", "cogs": "200",
        "direct_costs": "0", "currency": "IRR",
    })
    assert response.status_code == 200
    rows_a = client.get("/api/finance/entries", headers=headers_a).json()
    rows_b = client.get("/api/finance/entries", headers=headers_b).json()
    assert any(row["document_ref"] == "A-ONLY" for row in rows_a)
    assert all(row["document_ref"] != "A-ONLY" for row in rows_b)


def test_csv_import_reports_duplicate_rows():
    client = TestClient(app)
    headers, _ = register(client, "Finance CSV")
    csv_content = (
        "period,document_ref,sales,discounts,returns,cogs,direct_costs,currency\n"
        "2026-07,CSV-1,1000,0,0,600,20,IRR\n"
        "2026-07,CSV-1,1000,0,0,600,20,IRR\n"
    )
    response = client.post("/api/finance/import/csv", headers=headers, json={"content": csv_content})
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 1
    assert len(response.json()["rejected"]) == 1


def test_owner_financial_participation_is_retired_and_finance_stays_in_irr(monkeypatch):
    client = TestClient(app)
    owner_headers, owner = register(client, "Retired Participation Owner")
    company_headers, _ = register(client, "IRR Only Company")
    monkeypatch.setenv("LEADORA_OWNER_USER_IDS", str(owner["user"]["id"]))

    assert client.get("/api/finance/contracts", headers=owner_headers).status_code == 404
    assert client.post("/api/finance/contracts", headers=owner_headers, json={}).status_code == 404
    assert client.get("/api/finance/owner/overview", headers=owner_headers).status_code == 404
    assert client.post("/api/finance/reports/999/settlement", headers=owner_headers,
                       json={"amount": "1", "note": "legacy"}).status_code == 404

    entry = client.post("/api/finance/entries", headers=company_headers, json={
        "period": "2026-11", "document_ref": "IRR-ONLY-1", "sales": "1000000",
        "discounts": "10000", "returns": "0", "cogs": "600000",
        "direct_costs": "5000", "currency": "IRR",
    })
    assert entry.status_code == 200, entry.text
    report = client.post("/api/finance/reports/calculate?period=2026-11",
                         headers=company_headers, json={})
    assert report.status_code == 200, report.text
    assert report.json()["currency"] == "IRR"
    assert report.json()["owner_share"] == "0.00"
    assert report.json()["share_percent"] == "0.00"

    for currency in ("IRR", "USD", "EUR"):
        rejected = client.post("/api/finance/entries", headers=company_headers, json={
            "period": "2026-12", "document_ref": "BAD-" + currency, "sales": "100",
            "discounts": "0", "returns": "0", "cogs": "10",
            "direct_costs": "0", "currency": currency,
        })
        assert rejected.status_code == 422


def test_integration_requires_provider_and_owner_access_is_restricted(monkeypatch):
    client = TestClient(app)
    headers, _ = register(client, "Finance Access")
    missing_provider = client.put("/api/finance/settings", headers=headers, json={"methods": ["manual", "integration"]})
    assert missing_provider.status_code == 422
    denied = client.get("/api/finance/owner/overview", headers=headers)
    assert denied.status_code == 403


def test_post_close_adjustment_requires_owner_approval_and_applies_next_period(monkeypatch):
    client = TestClient(app)
    owner_email = f"adjustment-owner-{uuid.uuid4().hex[:8]}@example.com"
    owner_headers, owner = register(client, "Adjustment Owner", owner_email)
    company_headers, _ = register(client, "Adjustment Company")
    monkeypatch.setenv("LEADORA_OWNER_USER_IDS", str(owner["user"]["id"]))

    entry = client.post("/api/finance/entries", headers=company_headers, json={
        "period": "2026-05", "document_ref": "ADJ-BASE", "sales": "1000",
        "discounts": "0", "returns": "0", "cogs": "500",
        "direct_costs": "0", "currency": "IRR",
    })
    assert entry.status_code == 200, entry.text
    report = client.post("/api/finance/reports/calculate?period=2026-05", headers=company_headers, json={})
    assert report.status_code == 200, report.text
    report_id = report.json()["id"]
    assert client.post(f"/api/finance/reports/{report_id}/approve", headers=owner_headers, json={}).status_code == 200

    request = client.post(f"/api/finance/reports/{report_id}/adjustments", headers=company_headers, json={
        "adjustment_period": "2026-06", "sales_adjustment": "-100",
        "discounts_adjustment": "0", "returns_adjustment": "0",
        "cogs_adjustment": "-50", "direct_costs_adjustment": "0",
        "currency": "IRR", "reason": "Corrected invoice cost after review",
    })
    assert request.status_code == 200, request.text
    adjustment_id = request.json()["id"]
    pending = client.post("/api/finance/reports/calculate?period=2026-06", headers=company_headers, json={})
    assert pending.status_code == 422

    review = client.post(f"/api/finance/adjustments/{adjustment_id}/review?decision=approve", headers=owner_headers, json={})
    assert review.status_code == 200, review.text
    report_next = client.post("/api/finance/reports/calculate?period=2026-06", headers=company_headers, json={})
    assert report_next.status_code == 200, report_next.text
    assert report_next.json()["gross_sales"] == "-100.00"
    assert report_next.json()["cogs"] == "-50.00"
    assert report_next.json()["eligible_profit"] == "-50.00"


def test_owner_bootstrap_is_one_time_and_rejects_other_accounts(monkeypatch):
    client = TestClient(app)
    monkeypatch.delenv("LEADORA_OWNER_USER_IDS", raising=False)
    bootstrap = "test-owner-bootstrap-token-0123456789-abcdef"
    monkeypatch.setenv("LEADORA_OWNER_BOOTSTRAP_TOKEN", bootstrap)
    owner_headers, owner = register(client, "Bootstrap Owner")
    other_headers, other = register(client, "Bootstrap Other")
    monkeypatch.setenv("LEADORA_OWNER_BOOTSTRAP_EMAIL", owner["user"]["email"])

    wrong = client.post("/api/finance/owner/claim", headers=owner_headers, json={"token": "wrong-token-that-is-long-enough-123"})
    assert wrong.status_code == 403

    claimed = client.post("/api/finance/owner/claim", headers=owner_headers, json={"token": bootstrap})
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["is_platform_owner"] is True
    identity = client.get("/api/finance/identity", headers=owner_headers)
    assert identity.status_code == 200
    assert identity.json()["is_platform_owner"] is True

    duplicate = client.post("/api/finance/owner/claim", headers=other_headers, json={"token": bootstrap})
    assert duplicate.status_code == 403
    denied = client.get("/api/finance/owner/overview", headers=other_headers)
    assert denied.status_code == 403
    allowed = client.get("/api/finance/owner/overview", headers=owner_headers)
    assert allowed.status_code == 200

    # Recovery is an explicit, separately gated path for a wrongly claimed owner account.
    recovery_headers, recovery = register(client, "Recovery Owner")

    # Fail closed if the recovery token reuses the bootstrap token.
    monkeypatch.setenv("LEADORA_OWNER_RECOVERY_TOKEN", bootstrap)
    monkeypatch.setenv("LEADORA_OWNER_RECOVERY_EMAIL", recovery["user"]["email"])
    same_token = client.post(
        "/api/finance/owner/recover", headers=recovery_headers, json={"token": bootstrap}
    )
    assert same_token.status_code == 503

    # Missing recovery email must fail closed.
    recovery_token = "test-owner-recovery-token-0123456789-abcdef"
    monkeypatch.setenv("LEADORA_OWNER_RECOVERY_TOKEN", recovery_token)
    monkeypatch.delenv("LEADORA_OWNER_RECOVERY_EMAIL", raising=False)
    missing_email = client.post(
        "/api/finance/owner/recover", headers=recovery_headers, json={"token": recovery_token}
    )
    assert missing_email.status_code == 503

    # An explicit server-side owner ID list takes precedence over form recovery.
    monkeypatch.setenv("LEADORA_OWNER_RECOVERY_EMAIL", recovery["user"]["email"])
    monkeypatch.setenv("LEADORA_OWNER_USER_IDS", "999999999")
    server_owned = client.post(
        "/api/finance/owner/recover", headers=recovery_headers, json={"token": recovery_token}
    )
    assert server_owned.status_code == 409
    monkeypatch.delenv("LEADORA_OWNER_USER_IDS", raising=False)

    monkeypatch.setenv("LEADORA_OWNER_RECOVERY_TOKEN", recovery_token)
    monkeypatch.setenv("LEADORA_OWNER_RECOVERY_EMAIL", recovery["user"]["email"])

    bad_token = client.post(
        "/api/finance/owner/recover",
        headers=recovery_headers,
        json={"token": "wrong-owner-recovery-token-0123456789"},
    )
    assert bad_token.status_code == 403

    wrong_account = client.post(
        "/api/finance/owner/recover",
        headers=other_headers,
        json={"token": recovery_token},
    )
    assert wrong_account.status_code == 403

    recovered = client.post(
        "/api/finance/owner/recover",
        headers=recovery_headers,
        json={"token": recovery_token},
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["is_platform_owner"] is True
    assert client.get("/api/finance/identity", headers=recovery_headers).json()["is_platform_owner"] is True
    assert client.get("/api/finance/identity", headers=owner_headers).json()["is_platform_owner"] is False
    assert client.get("/api/finance/owner/overview", headers=owner_headers).status_code == 403
    assert client.get("/api/finance/owner/overview", headers=recovery_headers).status_code == 200


def test_integration_webhook_key_rotation_ingest_and_tenant_isolation():
    client = TestClient(app)
    headers_a, _ = register(client, "Webhook A")
    headers_b, _ = register(client, "Webhook B")
    configured = client.put("/api/finance/settings", headers=headers_a, json={
        "methods": ["integration"], "integration_provider": "generic-webhook-test"
    })
    assert configured.status_code == 200, configured.text
    created = client.post("/api/finance/integration/key", headers=headers_a, json={})
    assert created.status_code == 200, created.text
    key_a = created.json()["integration_key"]

    missing = client.post("/api/finance/integration/ingest", json={"entries": [{
        "period": "2026-10", "document_ref": "WEB-1", "sales": "1000",
        "discounts": "0", "returns": "0", "cogs": "600", "direct_costs": "0",
        "currency": "IRR"
    }]})
    assert missing.status_code == 401

    batch = client.post("/api/finance/integration/ingest", headers={"X-LEADORA-Integration-Key": key_a}, json={"entries": [
        {"period": "2026-10", "document_ref": "WEB-1", "sales": "1000", "discounts": "0", "returns": "0", "cogs": "600", "direct_costs": "0", "currency": "IRR", "source_key": "erp-1"},
        {"period": "2026-10", "document_ref": "WEB-1", "sales": "1000", "discounts": "0", "returns": "0", "cogs": "600", "direct_costs": "0", "currency": "IRR", "source_key": "erp-1"},
    ]})
    assert batch.status_code == 200, batch.text
    assert batch.json()["imported"] == 1
    assert len(batch.json()["rejected"]) == 1

    entries_a = client.get("/api/finance/entries", headers=headers_a)
    entries_b = client.get("/api/finance/entries", headers=headers_b)
    assert entries_a.status_code == 200
    assert any(row["document_ref"] == "WEB-1" and row["source"] == "integration" for row in entries_a.json())
    assert all(row["document_ref"] != "WEB-1" for row in entries_b.json())

    rotated = client.post("/api/finance/integration/key", headers=headers_a, json={})
    assert rotated.status_code == 200
    key_b = rotated.json()["integration_key"]
    old_key = client.post("/api/finance/integration/ingest", headers={"X-LEADORA-Integration-Key": key_a}, json={"entries": [
        {"period": "2026-10", "document_ref": "WEB-2", "sales": "10", "discounts": "0", "returns": "0", "cogs": "5", "direct_costs": "0", "currency": "IRR"}
    ]})
    assert old_key.status_code == 401
    new_key = client.post("/api/finance/integration/ingest", headers={"X-LEADORA-Integration-Key": key_b}, json={"entries": [
        {"period": "2026-10", "document_ref": "WEB-2", "sales": "10", "discounts": "0", "returns": "0", "cogs": "5", "direct_costs": "0", "currency": "IRR"}
    ]})
    assert new_key.status_code == 200, new_key.text
