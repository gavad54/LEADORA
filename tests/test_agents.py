import os
from datetime import date, timedelta
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def account(label):
    suffix = str(os.getpid()) + "-" + label
    r = client.post("/api/register", json={
        "company_name": "Agents " + suffix,
        "industry": "multi-industry",
        "email": "agents-" + suffix + "@example.com",
        "password": "secure-agent-test-password",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}

def test_invoice_payment_aging_and_tenant_isolation():
    a, b = account("a"), account("b")
    past = (date.today() - timedelta(days=40)).isoformat()
    issue = (date.today() - timedelta(days=70)).isoformat()
    invoice = client.post("/api/invoices", headers=a, json={
        "invoice_number": "INV-TEST-" + str(os.getpid()), "issue_date": issue,
        "due_date": past, "amount": 1000, "note": "test",
    })
    assert invoice.status_code == 200, invoice.text
    invoice_id = invoice.json()["id"]
    assert client.get("/api/invoices", headers=b).json() == []
    payment = client.post("/api/payments", headers=a, json={
        "invoice_id": invoice_id, "paid_at": date.today().isoformat(), "amount": 250,
        "method": "transfer", "reference": "test",
    })
    assert payment.status_code == 200, payment.text
    overview = client.get("/api/agents/overview", headers=a)
    assert overview.status_code == 200, overview.text
    data = overview.json()
    assert data["receivables"]["outstanding_total"] == 750
    assert data["receivables"]["aging"]["31_60"] == 750
    assert data["receivables"]["overdue"][0]["days_overdue"] == 40
    assert client.post("/api/payments", headers=a, json={
        "invoice_id": invoice_id, "paid_at": date.today().isoformat(), "amount": 1000,
    }).status_code == 422

def test_expense_opportunity_campaign_and_action_approval():
    h = account("business")
    due = (date.today() + timedelta(days=3)).isoformat()
    assert client.post("/api/expenses", headers=h, json={
        "title": "Rent", "category": "fixed", "amount": 500, "due_date": due,
    }).status_code == 200
    assert client.post("/api/opportunities", headers=h, json={
        "title": "Potential project", "stage": "qualified", "estimated_value": 2000,
        "last_contact_date": (date.today() - timedelta(days=20)).isoformat(),
    }).status_code == 200
    assert client.post("/api/campaigns", headers=h, json={
        "name": "Autumn", "channel": "social", "spend": 100, "leads": 20,
        "conversions": 3, "revenue": 350,
    }).status_code == 200
    overview = client.get("/api/agents/overview", headers=h).json()
    assert overview["sales"]["pipeline_value"] == 2000
    assert overview["marketing"]["campaigns"][0]["roi"] == 2.5
    assert overview["cashflow"]["pending_expenses"] == 1
    action = client.post("/api/agents/actions", headers=h, json={
        "agent": "receivables", "title": "Follow-up", "rationale": "Invoice overdue",
        "recommendation": "Prepare reminder", "sensitive": True,
    })
    assert action.status_code == 200
    assert action.json()["status"] == "suggested"
    action_id = action.json()["id"]
    assert client.post(f"/api/agents/actions/{action_id}/decision", headers=h,
        json={"decision": "approved"}).status_code == 200

def test_csv_row_import_reports_invalid_rows():
    h = account("import")
    r = client.post("/api/import/rows", headers=h, json={
        "dataset": "expenses",
        "rows": [
            {"title": "Utilities", "category": "fixed", "amount": 90,
             "due_date": date.today().isoformat(), "status": "pending"},
            {"title": "", "category": "fixed", "amount": -1,
             "due_date": "not-a-date", "status": "pending"},
        ],
    })
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1, r.json()
    assert r.json()["rejected"] == 1


def test_multisource_business_lead_import_deduplicates_and_is_tenant_scoped():
    a, b = account("leads-a"), account("leads-b")
    payload = {"source": "licensed-directory", "records": [
        {"name": "Example Market", "phone": "+98 21 12345678", "city": "Tehran",
         "category": "retail", "website": "https://example.test"},
        {"name": "", "city": "Tehran"},
    ]}
    first = client.post("/api/prospecting/import", headers=a, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["imported"] == 1
    assert first.json()["rejected"] == 1
    second = client.post("/api/prospecting/import", headers=a, json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["updated"] == 1
    leads = client.get("/api/prospecting/business-leads", headers=a)
    assert leads.status_code == 200, leads.text
    assert leads.json()["total"] == 1
    assert leads.json()["items"][0]["name"] == "Example Market"
    assert client.get("/api/prospecting/business-leads", headers=b).json()["total"] == 0
    runs = client.get("/api/prospecting/source-runs", headers=a)
    assert len(runs.json()) >= 2
    sources = client.get("/api/prospecting/sources", headers=a).json()["sources"]
    assert {item["id"] for item in sources} >= {"openstreetmap", "balad", "neshan", "snapp"}


def test_scheduled_prospecting_settings_are_tenant_scoped_and_validated():
    a, b = account("scheduled-a"), account("scheduled-b")
    assert client.get("/api/prospecting/settings", headers=a).json()["configured"] is False
    saved = client.put("/api/prospecting/settings", headers=a, json={
        "latitude": 35.6892, "longitude": 51.3890, "radius_m": 5000,
        "category": "shop", "enabled": True, "interval_seconds": 900,
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["enabled"] == 1
    assert saved.json()["interval_seconds"] == 900
    assert client.get("/api/prospecting/settings", headers=b).json()["configured"] is False
    status = client.get("/api/prospecting/worker/status", headers=a)
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert "worker_process" in status.json()
    invalid = client.put("/api/prospecting/settings", headers=a, json={
        "latitude": 300, "longitude": 0, "radius_m": 1000,
        "category": "all", "enabled": True, "interval_seconds": 60,
    })
    assert invalid.status_code == 422
