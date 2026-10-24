import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app, db


def register(client, company):
    suffix = uuid.uuid4().hex[:10]
    response = client.post("/api/register", json={
        "company_name": f"{company} {suffix}", "industry": "services",
        "email": f"{suffix}@example.com", "password": "secure-test-password-2026",
    })
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}, response.json()


def test_bank_accounts_are_tenant_scoped_and_never_claim_transfers():
    client = TestClient(app)
    a_headers, a = register(client, "Bank A")
    b_headers, _ = register(client, "Bank B")
    created = client.post("/api/bank-accounts", headers=a_headers, json={
        "label": "حساب اصلی", "institution": "Test Bank",
        "account_holder": "Company A", "iban_masked": "DE••••1234",
        "currency": "IRR", "is_default": True,
    })
    assert created.status_code == 200, created.text
    rows_a = client.get("/api/bank-accounts", headers=a_headers)
    rows_b = client.get("/api/bank-accounts", headers=b_headers)
    assert len(rows_a.json()) == 1
    assert rows_a.json()[0]["currency"] == "IRR"
    assert rows_b.json() == []
    status = client.get("/api/bank-accounts/status", headers=a_headers).json()
    assert status["real_transfers_enabled"] is False
    assert status["provider_integration"] == "not_configured"
    assert "1234" in rows_a.json()[0]["iban_masked"]


def test_activation_key_is_one_time_and_tenant_bound(monkeypatch):
    client = TestClient(app)
    owner_headers, owner = register(client, "Platform Owner")
    company_headers, company = register(client, "Licensed Company")
    monkeypatch.setenv("LEADORA_OWNER_USER_IDS", str(owner["user"]["id"]))
    issued = client.post("/api/platform/licenses", headers=owner_headers, json={
        "tenant_id": company["tenant"]["id"], "edition": "business"
    })
    assert issued.status_code == 200, issued.text
    key = issued.json()["activation_key"]
    activated = client.post("/api/account/license/activate", headers=company_headers, json={"activation_key": key})
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    again = client.post("/api/account/license/activate", headers=company_headers, json={"activation_key": key})
    assert again.status_code == 400
    wrong_tenant_headers, _ = register(client, "Other Company")
    wrong = client.post("/api/account/license/activate", headers=wrong_tenant_headers, json={"activation_key": key})
    assert wrong.status_code == 400


def test_trial_is_server_created_and_limited_to_90_days():
    client = TestClient(app)
    headers, registered = register(client, "Trial Company")
    response = client.get("/api/account/license", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    start = datetime.fromisoformat(data["trial_started_at"])
    end = datetime.fromisoformat(data["trial_ends_at"])
    assert data["status"] == "trial"
    assert timedelta(days=89, hours=23) < end - start <= timedelta(days=90, seconds=1)
    assert data["tenant_id"] == registered["tenant"]["id"]


def test_only_platform_owner_can_issue_keys(monkeypatch):
    client = TestClient(app)
    headers, _ = register(client, "Not Owner")
    monkeypatch.setenv("LEADORA_OWNER_USER_IDS", "")
    response = client.post("/api/platform/licenses", headers=headers, json={"tenant_id": 1})
    assert response.status_code == 403
