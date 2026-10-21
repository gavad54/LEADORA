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
