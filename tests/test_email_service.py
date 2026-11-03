"""Brevo transactional email integration tests; all network calls are mocked."""
import json
import os
import tempfile
from urllib.request import Request
import pytest

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="leadora-email-tests-"))
os.environ["LEADORA_DB"] = str(_TEST_ROOT / "email-test.db")
os.environ["LEADORA_ENV"] = "test"
os.environ["LEADORA_SECRET"] = "test-secret-that-is-long-enough-for-email-tests"

from fastapi.testclient import TestClient
from app.main import app, db

client = TestClient(app)


@pytest.fixture
def owner_headers():
    response = client.post("/api/register", json={
        "company_name": "Email Service Test Company",
        "industry": "retail",
        "email": "email-owner@example.test",
        "password": "A-strong-test-password-2026",
    })
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    user_id = token.split(".", 1)[0].split(":")[0]
    with db() as conn:
        conn.execute("DELETE FROM finance_platform_owner")
        conn.execute("INSERT INTO finance_platform_owner(singleton,user_id,email) VALUES(1,?,?)",
                     (user_id, "email-owner@example.test"))
    headers = {"Authorization": f"Bearer {token}"}
    yield headers
    with db() as conn:
        conn.execute("DELETE FROM finance_platform_owner WHERE user_id=?", (user_id,))


def test_platform_owner_can_send_a_test_email_only_to_their_own_account(monkeypatch, owner_headers):
    headers = owner_headers
    monkeypatch.setenv("BREVO_API_KEY", "test-api-key-never-return-this")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "noreply@example.test")
    monkeypatch.setenv("BREVO_SENDER_NAME", "LEADORA")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"messageId":"test-message-123"}'

    def fake_urlopen(request, timeout):
        assert isinstance(request, Request)
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.email_service.urlopen", fake_urlopen)
    response = client.post("/api/platform/email/test", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["sent"] is True
    assert response.json()["message_id"] == "test-message-123"
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["headers"]["Api-key"] == "test-api-key-never-return-this"
    assert captured["body"]["to"] == [{"email": "email-owner@example.test"}]
    assert captured["body"]["sender"]["email"] == "noreply@example.test"
    assert captured["timeout"] <= 15
    assert "test-api-key-never-return-this" not in response.text


def test_platform_email_status_does_not_expose_provider_credentials(monkeypatch, owner_headers):
    headers = owner_headers
    monkeypatch.setenv("BREVO_API_KEY", "secret-value-that-must-never-be-returned")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "noreply@example.test")
    response = client.get("/api/platform/email/status", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "brevo"
    assert response.json()["configured"] is True
    assert "secret-value-that-must-never-be-returned" not in response.text
