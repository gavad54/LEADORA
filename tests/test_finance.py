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
        "direct_costs": "25", "currency": "IRT",
    })
    assert entry.status_code == 200, entry.text
    duplicate = client.post("/api/finance/entries", headers=headers, json={
        "period": "2026-05", "document_ref": "INV-TEST-1", "sales": "1000",
        "discounts": "100", "returns": "50", "cogs": "500",
        "direct_costs": "25", "currency": "IRT",
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
        "direct_costs": "0", "currency": "IRT",
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
        "2026-07,CSV-1,1000,0,0,600,20,IRT\n"
        "2026-07,CSV-1,1000,0,0,600,20,IRT\n"
    )
    response = client.post("/api/finance/import/csv", headers=headers, json={"content": csv_content})
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 1
    assert len(response.json()["rejected"]) == 1


def test_owner_contract_goal_share_and_closed_report_is_immutable(monkeypatch):
    client = TestClient(app)
    owner_email = f"leadora-owner-{uuid.uuid4().hex[:8]}@example.com"
    owner_headers, _ = register(client, "LEADORA Owner", owner_email)
    company_headers, company = register(client, "Profit Share Company")
    monkeypatch.setenv("LEADORA_OWNER_EMAILS", owner_email)

    contract = client.post("/api/finance/contracts", headers=owner_headers, json={
        "tenant_id": company["tenant_id"],
        "trial_start": "2026-01-01", "trial_end": "2026-03-31",
        "contract_start": "2026-01-01", "contract_end": "2026-12-31",
        "goal_name": "Increase net sales", "baseline": "100", "target": "120",
        "share_percent": "10", "direct_costs": ["direct_costs"], "notes": "test agreement",
    })
    assert contract.status_code == 200, contract.text
    contract_id = contract.json()["id"]
    assert client.post(f"/api/finance/contracts/{contract_id}/activate", headers=owner_headers, json={}).status_code == 200
    goal = client.post(f"/api/finance/contracts/{contract_id}/goal", headers=owner_headers, json={
        "achieved": True, "evidence": "Reviewed and verified monthly sales records",
    })
    assert goal.status_code == 200, goal.text

    entry = client.post("/api/finance/entries", headers=company_headers, json={
        "period": "2026-05", "document_ref": "SHARE-1", "sales": "1000",
        "discounts": "100", "returns": "0", "cogs": "600",
        "direct_costs": "50", "currency": "IRT",
    })
    assert entry.status_code == 200, entry.text
    report = client.post("/api/finance/reports/calculate?period=2026-05", headers=company_headers, json={})
    assert report.status_code == 200, report.text
    assert report.json()["eligible_profit"] == "250.00"
    assert report.json()["owner_share"] == "25.00"

    approved = client.post(f"/api/finance/reports/{report.json()['id']}/approve", headers=owner_headers, json={})
    assert approved.status_code == 200, approved.text
    rerun = client.post("/api/finance/reports/calculate?period=2026-05", headers=company_headers, json={})
    assert rerun.status_code == 409


def test_integration_requires_provider_and_owner_access_is_restricted(monkeypatch):
    client = TestClient(app)
    headers, _ = register(client, "Finance Access")
    missing_provider = client.put("/api/finance/settings", headers=headers, json={"methods": ["manual", "integration"]})
    assert missing_provider.status_code == 422
    denied = client.get("/api/finance/owner/overview", headers=headers)
    assert denied.status_code == 403
