import secrets
from fastapi.testclient import TestClient
from app.main import app

def _account(client):
    suffix = secrets.token_hex(5)
    r = client.post("/api/register", json={
        "company_name": "Pricing test " + suffix,
        "industry": "distribution",
        "email": "pricing-" + suffix + "@example.com",
        "password": "Strong-test-password-93"
    })
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}

def test_plans_are_modular_and_accounting_is_optional():
    client = TestClient(app)
    plans = client.get("/api/plans")
    assert plans.status_code == 200
    data = plans.json()
    assert data["product"] == "LEADORA"
    assert data["separate_from_ARIANA"] is True
    keys = {m["module_key"] for m in data["modules"]}
    assert "accounting" in keys
    assert data["billing_enabled"] is False

def test_customer_can_request_accounting_without_automatic_activation():
    client = TestClient(app)
    headers = _account(client)
    before = client.get("/api/modules", headers=headers)
    assert before.status_code == 200
    accounting = next(m for m in before.json()["modules"] if m["module_key"] == "accounting")
    assert accounting["status"] == "off"
    requested = client.put("/api/modules/accounting/request", headers=headers)
    assert requested.status_code == 200
    assert requested.json()["status"] == "requested"
    after = client.get("/api/modules", headers=headers)
    accounting_after = next(m for m in after.json()["modules"] if m["module_key"] == "accounting")
    assert accounting_after["status"] == "requested"

def test_owner_pricing_requires_secret_and_can_update(monkeypatch):
    client = TestClient(app)
    denied = client.get("/api/owner/pricing")
    assert denied.status_code == 403
    monkeypatch.setenv("LEADORA_OWNER_KEY", "test-owner-key-with-more-than-24-chars")
    headers = {"X-LEADORA-OWNER-KEY": "test-owner-key-with-more-than-24-chars"}
    current = client.get("/api/owner/pricing", headers=headers)
    assert current.status_code == 200
    old = current.json()
    body = {
        "modules": {m["module_key"]: m["monthly_price"] for m in old["modules"]},
        "active_modules": [m["module_key"] for m in old["modules"] if m["active"]],
        "currency": old["settings"]["currency"],
        "currency_label": old["settings"]["currency_label"],
        "base_monthly_price": old["settings"]["base_monthly_price"],
        "pricing_note": old["settings"]["pricing_note"]
    }
    saved = client.put("/api/owner/pricing", headers=headers, json=body)
    assert saved.status_code == 200
    assert saved.json()["saved"] is True
