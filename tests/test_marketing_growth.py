import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def account():
    suffix = str(os.getpid()) + "-marketing-growth"
    response = client.post("/api/register", json={
        "company_name": "Marketing Growth " + suffix,
        "industry": "services",
        "email": "marketing-" + suffix + "@example.com",
        "password": "secure-marketing-growth-password",
    })
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}

def test_marketing_growth_catalog_requires_auth_and_preserves_single_ownership():
    assert client.get("/api/marketing-growth/modules").status_code == 401
    headers = account()
    response = client.get("/api/marketing-growth/modules", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["product"] == "LEADORA"
    assert data["total"] == 11
    ids = [item["id"] for item in data["modules"]]
    assert len(ids) == len(set(ids)) == 11
    assert data["execution_policy"]["outbound_messaging_enabled"] is False
    assert data["execution_policy"]["social_publishing_enabled"] is False
    assert data["execution_policy"]["human_approval_required_for_external_actions"] is True
    assert data["shared_dependencies"][0]["owner"] == "ARIA / NEGAH"
    assert client.get("/api/marketing-growth/modules", headers=headers).json()["modules"] == data["modules"]
