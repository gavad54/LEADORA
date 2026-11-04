"""One-time platform-owner bootstrap claim tests.

All tests use the isolated LEADORA test database and never access Railway.
"""
from test_security_regression import client, register, auth


def test_owner_bootstrap_claim_grants_platform_owner_only_to_matching_account(monkeypatch):
    token = register("Platform Owner", "owner@example.test")
    user_id = token.split(".", 1)[0].split(":", 1)[0]
    monkeypatch.setenv("LEADORA_OWNER_BOOTSTRAP_EMAIL", "owner@example.test")
    monkeypatch.setenv("LEADORA_OWNER_BOOTSTRAP_TOKEN", "a-test-bootstrap-token-with-more-than-32-characters")

    claimed = client.post(
        "/api/platform/owner/claim",
        headers=auth(token),
        json={"bootstrap_token": "a-test-bootstrap-token-with-more-than-32-characters"},
    )

    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["status"] == "claimed"
    assert claimed.json()["owner_user_id"] == int(user_id)
    assert client.get("/api/platform/licenses", headers=auth(token)).status_code == 200


def test_owner_bootstrap_claim_rejects_wrong_email_or_token_without_granting_access(monkeypatch):
    token = register("Not Platform Owner", "not-owner@example.test")
    monkeypatch.setenv("LEADORA_OWNER_BOOTSTRAP_EMAIL", "owner@example.test")
    monkeypatch.setenv("LEADORA_OWNER_BOOTSTRAP_TOKEN", "a-test-bootstrap-token-with-more-than-32-characters")

    response = client.post(
        "/api/platform/owner/claim",
        headers=auth(token),
        json={"bootstrap_token": "wrong-bootstrap-token-with-more-than-32-characters"},
    )

    assert response.status_code == 403
    assert client.get("/api/platform/licenses", headers=auth(token)).status_code == 403


def test_owner_bootstrap_claim_is_one_time_and_cannot_replace_existing_owner(monkeypatch):
    first_token = register("First Owner", "first-owner@example.test")
    second_token = register("Second Owner", "second-owner@example.test")
    monkeypatch.setenv("LEADORA_OWNER_BOOTSTRAP_EMAIL", "first-owner@example.test")
    monkeypatch.setenv("LEADORA_OWNER_BOOTSTRAP_TOKEN", "a-test-bootstrap-token-with-more-than-32-characters")
    claim = {
        "bootstrap_token": "a-test-bootstrap-token-with-more-than-32-characters",
    }

    first = client.post("/api/platform/owner/claim", headers=auth(first_token), json=claim)
    second = client.post("/api/platform/owner/claim", headers=auth(second_token), json=claim)

    assert first.status_code == 200, first.text
    assert second.status_code == 403
    assert client.get("/api/platform/licenses", headers=auth(first_token)).status_code == 200
    assert client.get("/api/platform/licenses", headers=auth(second_token)).status_code == 403


def test_owner_bootstrap_claim_fails_closed_when_bootstrap_configuration_is_missing(monkeypatch):
    token = register("Unconfigured Owner", "unconfigured-owner@example.test")
    monkeypatch.delenv("LEADORA_OWNER_BOOTSTRAP_EMAIL", raising=False)
    monkeypatch.delenv("LEADORA_OWNER_BOOTSTRAP_TOKEN", raising=False)

    response = client.post(
        "/api/platform/owner/claim",
        headers=auth(token),
        json={"bootstrap_token": "a-test-bootstrap-token-with-more-than-32-characters"},
    )

    assert response.status_code == 503
    assert client.get("/api/platform/licenses", headers=auth(token)).status_code == 403
