import os
from fastapi.testclient import TestClient
from app.main import app

def _workspace(client, suffix):
    r = client.post("/api/register", json={
        "company_name": "AI test " + suffix,
        "industry": "distribution",
        "email": "ai-" + suffix + "@example.com",
        "password": "secure-ai-test-password",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}

def test_ai_command_center_and_agent_registry_are_authenticated():
    c = TestClient(app)
    assert c.get("/api/ai/agents").status_code == 401
    h = _workspace(c, str(os.getpid()) + "-registry")
    agents = c.get("/api/ai/agents", headers=h)
    assert agents.status_code == 200
    data = agents.json()
    assert data["separate_from_ARIANA"] is True
    assert len(data["agents"]) >= 12
    assert c.get("/api/ai/command-center", headers=h).json()["summary"]["workflows_total"] == 0

def test_ai_workflows_are_tenant_isolated_and_transitions_guarded():
    c = TestClient(app)
    suffix = str(os.getpid()) + "-wf"
    a = _workspace(c, suffix + "a")
    b = _workspace(c, suffix + "b")
    created = c.post("/api/ai/workflows", headers=a, json={
        "customer_name": "Test buyer", "phone": "", "need": "bulk items",
        "source": "manual", "consent_to_follow_up": False
    })
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    assert len(c.get("/api/ai/workflows", headers=a).json()) == 1
    assert c.get("/api/ai/workflows", headers=b).json() == []
    bad_jump = c.post(f"/api/ai/workflows/{wid}/advance", headers=a, json={
        "action": "start_picking", "approved": False, "note": ""
    })
    assert bad_jump.status_code == 409
    no_consent = c.post(f"/api/ai/workflows/{wid}/advance", headers=a, json={
        "action": "qualify", "approved": False, "note": ""
    })
    assert no_consent.status_code == 200
    contact = c.post(f"/api/ai/workflows/{wid}/advance", headers=a, json={
        "action": "draft_contact", "approved": False, "note": ""
    })
    assert contact.status_code == 409
    assert c.post(f"/api/ai/workflows/{wid}/advance", headers=b, json={
        "action": "qualify", "approved": False, "note": ""
    }).status_code == 404

def test_customer_chat_persists_history_and_flags_handoff(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    c = TestClient(app)
    h = _workspace(c, str(os.getpid()) + "-chat")
    r = c.post("/api/ai/chat", headers=h, json={
        "message": "قیمت این کالا چنده؟", "customer_name": "خریدار",
        "channel": "test", "consent_to_follow_up": False
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["intent"] == "pricing"
    assert data["automation"]["live_llm"] is False
    history = c.get(f"/api/ai/chat/{data['conversation_id']}", headers=h)
    assert history.status_code == 200
    assert len(history.json()["messages"]) == 2
    complaint = c.post("/api/ai/chat", headers=h, json={"message": "شکایت دارم"})
    assert complaint.json()["handoff_required"] is True
    assert c.get("/api/ai/approvals", headers=h).json()

def test_command_center_page_is_served():
    c = TestClient(app)
    r = c.get("/ai-command-center")
    assert r.status_code == 200
    assert "فرماندهی هوشمند LEADORA" in r.text


def test_orchestrator_runs_safe_tasks_and_blocks_missing_consent():
    c = TestClient(app)
    h = _workspace(c, str(os.getpid()) + "-orchestrator")
    wf = c.post("/api/ai/workflows", headers=h, json={
        "customer_name": "Prospect", "need": "bulk order", "source": "manual",
        "consent_to_follow_up": False
    })
    assert wf.status_code == 200, wf.text
    run = c.post("/api/ai/orchestrate", headers=h)
    assert run.status_code == 200, run.text
    assert run.json()["created_tasks"] == 1
    tasks = c.get("/api/ai/tasks", headers=h)
    assert tasks.status_code == 200
    assert tasks.json()[0]["task_type"] == "qualify"
    assert tasks.json()[0]["status"] == "completed"
    second = c.post("/api/ai/orchestrate", headers=h)
    assert second.status_code == 200, second.text
    tasks = c.get("/api/ai/tasks", headers=h).json()
    draft = next(x for x in tasks if x["task_type"] == "draft_contact")
    assert draft["status"] == "blocked"
    assert "رضایت" in draft["output"]["reason"]


def test_lead_scoring_is_explainable_and_returns_targeted_questions():
    c = TestClient(app)
    h = _workspace(c, str(os.getpid()) + "-lead-score")
    wf = c.post("/api/ai/workflows", headers=h, json={
        "customer_name": "Prospect", "phone": "", "need": "", "source": "manual",
        "consent_to_follow_up": False
    })
    assert wf.status_code == 200, wf.text
    run = c.post("/api/ai/orchestrate", headers=h)
    assert run.status_code == 200, run.text
    tasks = c.get("/api/ai/tasks", headers=h).json()
    qualification = next(x for x in tasks if x["task_type"] == "qualify")
    out = qualification["output"]
    assert out["score_method"] == "explainable_rules_v1"
    assert out["lead_score"] == 10
    assert out["tier"] == "needs_enrichment"
    assert any("چه کالا" in q for q in out["targeted_questions"])
    assert any("رضایت" in q for q in out["targeted_questions"])
    assert qualification["status"] == "completed"


def test_complete_lead_gets_high_score_with_factor_breakdown():
    c = TestClient(app)
    h = _workspace(c, str(os.getpid()) + "-lead-score-full")
    wf = c.post("/api/ai/workflows", headers=h, json={
        "customer_name": "Qualified Buyer", "phone": "+49123456789",
        "need": "Bulk order of packaging materials for next month",
        "source": "referral", "consent_to_follow_up": True
    })
    assert wf.status_code == 200, wf.text
    run = c.post("/api/ai/orchestrate", headers=h)
    assert run.status_code == 200, run.text
    tasks = c.get("/api/ai/tasks", headers=h).json()
    out = next(x for x in tasks if x["task_type"] == "qualify")["output"]
    assert out["lead_score"] == 100
    assert out["tier"] == "hot"
    assert len(out["factors"]) >= 5
    assert out["targeted_questions"] == []
