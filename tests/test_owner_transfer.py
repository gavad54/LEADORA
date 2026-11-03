"""Owner transfer requires two independent email OTP confirmations."""
import json
import re
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app, db

client = TestClient(app)


def register_account(label):
    suffix = uuid.uuid4().hex[:10]
    email = f"{label}-{suffix}@example.test"
    response = client.post("/api/register", json={
        "company_name": f"{label} transfer test {suffix}",
        "industry": "retail",
        "email": email,
        "password": "A-strong-test-password-2026",
    })
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    user_id = int(token.split(".", 1)[0].split(":", 1)[0])
    return email, user_id, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner_and_target():
    owner_email, owner_id, owner_headers = register_account("owner")
    target_email, target_id, target_headers = register_account("target")
    with db() as conn:
        conn.execute("DELETE FROM finance_platform_owner")
        conn.execute("DELETE FROM platform_owner_transfer_requests")
        conn.execute("DELETE FROM platform_owner_transfer_audit")
        conn.execute("DELETE FROM user_session_revocations")
        conn.execute(
            "INSERT INTO finance_platform_owner(singleton,user_id,email) VALUES(1,?,?)",
            (str(owner_id), owner_email),
        )
    yield {
        "owner_email": owner_email,
        "owner_id": owner_id,
        "owner_headers": owner_headers,
        "target_email": target_email,
        "target_id": target_id,
        "target_headers": target_headers,
    }
    with db() as conn:
        conn.execute("DELETE FROM finance_platform_owner")
        conn.execute("DELETE FROM platform_owner_transfer_requests")
        conn.execute("DELETE FROM platform_owner_transfer_audit")
        conn.execute("DELETE FROM user_session_revocations")


def extract_code(message):
    match = re.search(r"کد تأیید: ([A-Za-z0-9_-]+)", message)
    assert match, message
    return match.group(1)


def test_owner_transfer_requires_both_distinct_email_codes_and_revokes_old_session(
    monkeypatch, owner_and_target
):
    monkeypatch.setenv("BREVO_API_KEY", "test-api-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "noreply@example.test")
    sent = []

    def fake_send(recipient, subject, text_content, html_content=None, tags=None):
        sent.append({"recipient": recipient, "text": text_content})
        return f"message-{len(sent)}"

    monkeypatch.setattr("app.main.send_transactional_email", fake_send)
    request = client.post(
        "/api/platform/owner/transfer/request",
        headers=owner_and_target["owner_headers"],
        json={"target_email": owner_and_target["target_email"]},
    )
    assert request.status_code == 200, request.text
    transfer_id = request.json()["transfer_id"]
    assert request.json()["codes_returned"] is False
    assert {item["recipient"] for item in sent} == {
        owner_and_target["owner_email"], owner_and_target["target_email"]
    }

    owner_code = extract_code(next(x["text"] for x in sent if x["recipient"] == owner_and_target["owner_email"]))
    target_code = extract_code(next(x["text"] for x in sent if x["recipient"] == owner_and_target["target_email"]))
    assert owner_code != target_code

    owner_confirm = client.post(
        "/api/platform/owner/transfer/confirm-current",
        headers=owner_and_target["owner_headers"],
        json={"transfer_id": transfer_id, "code": owner_code},
    )
    assert owner_confirm.status_code == 200, owner_confirm.text
    assert owner_confirm.json()["completed"] is False

    target_accept = client.post(
        "/api/platform/owner/transfer/accept",
        headers=owner_and_target["target_headers"],
        json={"transfer_id": transfer_id, "code": target_code},
    )
    assert target_accept.status_code == 200, target_accept.text
    assert target_accept.json()["completed"] is True

    with db() as conn:
        owner = conn.execute("SELECT user_id,email FROM finance_platform_owner WHERE singleton=1").fetchone()
        transfer = conn.execute(
            "SELECT current_code_hash,target_code_hash,status FROM platform_owner_transfer_requests WHERE id=?",
            (transfer_id,),
        ).fetchone()
        revoked = conn.execute(
            "SELECT revoked_before FROM user_session_revocations WHERE user_id=?",
            (owner_and_target["owner_id"],),
        ).fetchone()
        assert str(owner["user_id"]) == str(owner_and_target["target_id"])
        assert owner["email"] == owner_and_target["target_email"]
        assert transfer["status"] == "completed"
        assert owner_code not in transfer["current_code_hash"]
        assert target_code not in transfer["target_code_hash"]
        assert revoked is not None

    assert client.get("/api/platform/email/status", headers=owner_and_target["owner_headers"]).status_code == 401
    assert client.get("/api/platform/email/status", headers=owner_and_target["target_headers"]).status_code == 200


def test_owner_transfer_rejects_non_owner_and_does_not_send_email(monkeypatch, owner_and_target):
    called = []
    monkeypatch.setattr("app.main.send_transactional_email", lambda *args, **kwargs: called.append(args))
    response = client.post(
        "/api/platform/owner/transfer/request",
        headers=owner_and_target["target_headers"],
        json={"target_email": owner_and_target["owner_email"]},
    )
    assert response.status_code == 403
    assert called == []


def test_owner_transfer_cancels_request_if_either_email_send_fails(monkeypatch, owner_and_target):
    monkeypatch.setenv("BREVO_API_KEY", "test-api-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "noreply@example.test")
    calls = []

    def fail_second_send(recipient, subject, text_content, html_content=None, tags=None):
        calls.append(recipient)
        if len(calls) == 2:
            from app.email_service import EmailDeliveryError
            raise EmailDeliveryError("email delivery failed")
        return "first-message"

    monkeypatch.setattr("app.main.send_transactional_email", fail_second_send)
    response = client.post(
        "/api/platform/owner/transfer/request",
        headers=owner_and_target["owner_headers"],
        json={"target_email": owner_and_target["target_email"]},
    )
    assert response.status_code == 503
    with db() as conn:
        owner = conn.execute("SELECT user_id FROM finance_platform_owner WHERE singleton=1").fetchone()
        pending = conn.execute(
            "SELECT status FROM platform_owner_transfer_requests ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        assert str(owner["user_id"]) == str(owner_and_target["owner_id"])
        assert pending["status"] == "cancelled"


def test_owner_transfer_expired_code_is_rejected(monkeypatch, owner_and_target):
    monkeypatch.setenv("BREVO_API_KEY", "test-api-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "noreply@example.test")
    sent = []
    monkeypatch.setattr(
        "app.main.send_transactional_email",
        lambda recipient, subject, text_content, html_content=None, tags=None: (
            sent.append({"recipient": recipient, "text": text_content}) or f"message-{len(sent)}"
        ),
    )
    request = client.post(
        "/api/platform/owner/transfer/request",
        headers=owner_and_target["owner_headers"],
        json={"target_email": owner_and_target["target_email"]},
    )
    assert request.status_code == 200, request.text
    transfer_id = request.json()["transfer_id"]
    code = extract_code(next(x["text"] for x in sent if x["recipient"] == owner_and_target["owner_email"]))
    with db() as conn:
        conn.execute(
            "UPDATE platform_owner_transfer_requests SET expires_at=? WHERE id=?",
            (int(time.time()) - 1, transfer_id),
        )
    response = client.post(
        "/api/platform/owner/transfer/confirm-current",
        headers=owner_and_target["owner_headers"],
        json={"transfer_id": transfer_id, "code": code},
    )
    assert response.status_code == 410
