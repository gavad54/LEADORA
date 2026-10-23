import uuid
from fastapi.testclient import TestClient
from app.main import app


def register(client):
    suffix = uuid.uuid4().hex[:10]
    response = client.post("/api/register", json={
        "company_name": f"Route Regression {suffix}",
        "industry": "distribution",
        "email": f"route-{suffix}@example.com",
        "password": "secure-test-password-2026",
    })
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def test_business_routes_are_registered_once_and_use_current_schema():
    paths = [
        ("POST", "/api/invoices"), ("GET", "/api/invoices"),
        ("POST", "/api/expenses"), ("GET", "/api/expenses"),
        ("POST", "/api/opportunities"), ("GET", "/api/opportunities"),
        ("GET", "/api/agents/overview"),
    ]
    for method, path in paths:
        matches = [route for route in app.routes if getattr(route, "path", None) == path and method in getattr(route, "methods", set())]
        assert len(matches) == 1, f"{method} {path} registered {len(matches)} times"

    client = TestClient(app)
    headers = register(client)
    expense = client.post("/api/expenses", headers=headers, json={
        "title": "Regression expense", "category": "office", "amount": 125,
        "due_date": "2026-11-01", "status": "planned",
    })
    assert expense.status_code == 200, expense.text
    listed_expenses = client.get("/api/expenses", headers=headers)
    assert listed_expenses.status_code == 200, listed_expenses.text
    assert any(row["title"] == "Regression expense" for row in listed_expenses.json())

    opportunity = client.post("/api/opportunities", headers=headers, json={
        "title": "Regression opportunity", "stage": "qualified", "estimated_value": 2500,
        "expected_close_date": "2026-12-01", "last_contact_date": "2026-10-20",
    })
    assert opportunity.status_code == 200, opportunity.text
    listed_opportunities = client.get("/api/opportunities", headers=headers)
    assert listed_opportunities.status_code == 200, listed_opportunities.text
    assert any(row["title"] == "Regression opportunity" for row in listed_opportunities.json())

    overview = client.get("/api/agents/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    data = overview.json()
    assert data["sales"]["opportunities"] == 1
    assert data["sales"]["pipeline_value"] == 2500

    created_action = client.post("/api/agents/actions", headers=headers, json={
        "agent": "sales_analytics", "title": "Regression action", "rationale": "Test rationale",
        "recommendation": "Test recommendation", "sensitive": True,
    })
    assert created_action.status_code == 200, created_action.text
    action_id = created_action.json()["id"]
    action_rows = client.get("/api/agents/actions", headers=headers)
    assert action_rows.status_code == 200, action_rows.text
    assert any(row["id"] == action_id and row["rationale"] == "Test rationale" for row in action_rows.json())
    assert client.post(f"/api/agents/actions/{action_id}/resolve", headers=headers).status_code == 409
    decision = client.post(f"/api/agents/actions/{action_id}/decision", headers=headers, json={"decision": "approved"})
    assert decision.status_code == 200, decision.text
    resolved = client.post(f"/api/agents/actions/{action_id}/resolve", headers=headers)
    assert resolved.status_code == 200, resolved.text
    assert any(row["id"] == action_id and row["status"] == "done" for row in client.get("/api/agents/actions", headers=headers).json())

    template = client.get("/api/import/template/expenses.csv", headers=headers)
    assert template.status_code == 200, template.text
    assert "title,category,amount,due_date" in template.text
    campaign_template = client.get("/api/import/template/campaigns.csv", headers=headers)
    assert campaign_template.status_code == 200, campaign_template.text
    assert "name,channel,spend,leads,conversions,revenue,start_date,end_date" in campaign_template.text


def test_api_routes_are_registered_once_across_modules():
    from collections import Counter

    registrations = Counter()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        for method in getattr(route, "methods", set()) or set():
            if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                registrations[(method, path)] += 1

    duplicates = {key: count for key, count in registrations.items() if count != 1}
    assert duplicates == {}, f"Duplicate API route registrations: {duplicates}"


def test_owner_recovery_requires_authenticated_account():
    client = TestClient(app)
    response = client.post(
        "/api/finance/owner/recover",
        json={"token": "a-valid-looking-recovery-token-0123456789"},
    )
    assert response.status_code == 401, response.text


def test_business_module_read_routes_require_authentication():
    client = TestClient(app)
    protected_gets = [
        # Company operations, reports, exports, backup and workflows.
        "/api/products", "/api/customers", "/api/audit-log",
        "/api/export/products.csv", "/api/backup.json", "/api/insights",
        "/api/invoices", "/api/expenses", "/api/opportunities", "/api/campaigns",
        "/api/agents/overview", "/api/agents/actions",
        "/api/import/template/expenses.csv", "/api/backup/full.json",
        "/api/storage/status", "/api/workflow/statuses", "/api/workflow/documents",
        "/api/workflow/followups",
        # Prospecting and lead sources.
        "/api/prospecting/leads", "/api/prospecting/summary",
        "/api/prospecting/sources", "/api/prospecting/business-leads",
        "/api/prospecting/source-runs", "/api/prospecting/settings",
        "/api/prospecting/worker/status", "/api/prospecting/business-leads/export.csv",
        # Financial participation and owner-only operations.
        "/api/finance/identity", "/api/finance/settings",
        "/api/finance/integration/status", "/api/finance/entries",
        "/api/finance/reports", "/api/finance/adjustments",
        "/api/finance/owner/overview", "/api/finance/owner/audit",
        # Distribution ERP and accounting.
        "/api/distribution/fiscal-years", "/api/distribution/overview",
        "/api/distribution/accounts", "/api/distribution/warehouses",
        "/api/distribution/sales", "/api/distribution/journals",
        "/api/distribution/reports/balance-sheet",
        "/api/distribution/reports/receivables", "/api/distribution/reports/payables",
        "/api/distribution/reports/trial-balance", "/api/distribution/reports/profit-loss",
        "/api/distribution/reports/stock-movements", "/api/distribution/treasury/accounts",
        "/api/distribution/import/catalog", "/api/distribution/import/batches",
        # Module access, AI command center and observability.
        "/api/modules", "/api/owner/pricing",
        "/api/ai/followups", "/api/ai/agents", "/api/ai/command-center",
        "/api/ai/workflows", "/api/ai/approvals", "/api/ai/tasks",
        "/api/ai/health", "/api/ai/observability",
    ]

    failures = []
    for path in protected_gets:
        response = client.get(path)
        if response.status_code not in {401, 403}:
            failures.append((path, response.status_code, response.text[:120]))

    assert failures == [], f"Protected GET routes did not reject anonymous requests: {failures}"


def test_removed_participation_contract_routes_are_not_registered():
    removed = {
        ("GET", "/api/finance/contracts"),
        ("POST", "/api/finance/contracts"),
        ("POST", "/api/finance/contracts/{contract_id}/goal"),
        ("POST", "/api/finance/contracts/{contract_id}/activate"),
    }
    registered = {
        (method, getattr(route, "path", None))
        for route in app.routes
        for method in (getattr(route, "methods", set()) or set())
    }
    assert not (removed & registered)
