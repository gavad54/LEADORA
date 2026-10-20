import io
import json
import os
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app


def _workspace(client, suffix):
    r = client.post("/api/register", json={
        "company_name": "Local AI test " + suffix,
        "industry": "distribution",
        "email": "local-ai-" + suffix + "@example.com",
        "password": "secure-local-ai-test-password",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_chat_uses_local_ollama_provider(monkeypatch):
    monkeypatch.setenv("LEADORA_AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_urlopen(request, timeout=0):
        assert request.full_url == "http://127.0.0.1:11434/api/chat"
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["model"] == "qwen2.5:3b"
        assert payload["messages"][0]["role"] == "system"
        return io.BytesIO(json.dumps({
            "message": {"role": "assistant", "content": "پاسخ آزمایشی مدل محلی"}
        }).encode("utf-8"))

    c = TestClient(app)
    headers = _workspace(c, str(os.getpid()) + "-ollama")
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        r = c.post("/api/ai/chat", headers=headers, json={"message": "سلام"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reply"] == "پاسخ آزمایشی مدل محلی"
    assert data["automation"]["live_llm"] is True
    assert data["automation"]["external_message_sent"] is False


def test_ollama_unavailable_falls_back_without_claiming_llm(monkeypatch):
    monkeypatch.setenv("LEADORA_AI_PROVIDER", "ollama")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    c = TestClient(app)
    headers = _workspace(c, str(os.getpid()) + "-ollama-down")
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        r = c.post("/api/ai/chat", headers=headers, json={"message": "سلام"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["automation"]["live_llm"] is False
    assert "خوش آمدید" in data["reply"]


def test_health_reports_selected_local_provider(monkeypatch):
    monkeypatch.setenv("LEADORA_AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    c = TestClient(app)
    headers = _workspace(c, str(os.getpid()) + "-ollama-health")
    r = c.get("/api/ai/health", headers=headers)
    assert r.status_code == 200
    assert r.json()["ai_provider"] == {
        "provider": "ollama", "configured": True, "model": "qwen2.5:3b"
    }
