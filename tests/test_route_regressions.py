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
        "category": "office", "description": "Regression expense", "amount": 125,
        "due_date": "2026-11-01", "status": "planned", "vendor": "Test vendor",
    })
    assert expense.status_code == 200, expense.text
    listed_expenses = client.get("/api/expenses", headers=headers)
    assert listed_expenses.status_code == 200, listed_expenses.text
    assert any(row["description"] == "Regression expense" for row in listed_expenses.json())

    opportunity = client.post("/api/opportunities", headers=headers, json={
        "title": "Regression opportunity", "stage": "qualified", "estimated_value": 2500,
        "expected_close_date": "2026-12-01", "last_contact_at": "2026-10-20",
    })
    assert opportunity.status_code == 200, opportunity.text
    listed_opportunities = client.get("/api/opportunities", headers=headers)
    assert listed_opportunities.status_code == 200, listed_opportunities.text
    assert any(row["title"] == "Regression opportunity" for row in listed_opportunities.json())

    overview = client.get("/api/agents/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["mode"] == "rules_based"
