"""Legacy participation records remain intact while retired routes stay unavailable."""
import uuid

from fastapi.testclient import TestClient

from app.main import app, db


def register(client, name):
    suffix = uuid.uuid4().hex[:10]
    response = client.post("/api/register", json={
        "company_name": f"{name} {suffix}",
        "industry": "distribution",
        "email": f"{suffix}@example.test",
        "password": "secure-test-password-2026",
    })
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}, response.json()


def test_legacy_participation_history_is_preserved_without_active_contract_or_settlement_routes(monkeypatch):
    client = TestClient(app)
    owner_headers, owner = register(client, "Legacy History Owner")
    company_headers, company = register(client, "Legacy History Company")
    monkeypatch.setenv("LEADORA_OWNER_USER_IDS", str(owner["user"]["id"]))

    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS finance_contracts(
                 id INTEGER PRIMARY KEY,
                 tenant_id INTEGER NOT NULL,
                 goal_name TEXT NOT NULL,
                 share_percent TEXT NOT NULL,
                 status TEXT NOT NULL
               )"""
        )
        contract_id = conn.execute(
            "INSERT INTO finance_contracts(tenant_id,goal_name,share_percent,status) VALUES(?,?,?,?)",
            (company["tenant"]["id"], "legacy agreement", "12.5", "terminated"),
        ).lastrowid

    entry = client.post("/api/finance/entries", headers=company_headers, json={
        "period": "2026-10", "document_ref": "LEGACY-REPORT-1",
        "sales": "100000", "discounts": "0", "returns": "0",
        "cogs": "50000", "direct_costs": "0", "currency": "IRR",
    })
    assert entry.status_code == 200, entry.text
    report = client.post(
        "/api/finance/reports/calculate?period=2026-10",
        headers=company_headers,
        json={},
    )
    assert report.status_code == 200, report.text
    report_id = report.json()["id"]

    with db() as conn:
        conn.execute(
            """UPDATE finance_reports
               SET owner_share='12500.00', share_percent='12.5',
                   contract_id=?, settlement_status='unsettled', settled_amount='0.00'
               WHERE id=?""",
            (contract_id, report_id),
        )

    assert client.get("/api/finance/contracts", headers=owner_headers).status_code == 404
    assert client.get("/api/finance/owner/overview", headers=owner_headers).status_code == 404
    assert client.post(
        f"/api/finance/reports/{report_id}/settlement",
        headers=owner_headers,
        json={"amount": "12500", "note": "legacy"},
    ).status_code == 404

    with db() as conn:
        history = conn.execute(
            "SELECT goal_name,share_percent,status FROM finance_contracts WHERE id=?",
            (contract_id,),
        ).fetchone()
        report_history = conn.execute(
            "SELECT owner_share,share_percent,contract_id,settlement_status FROM finance_reports WHERE id=?",
            (report_id,),
        ).fetchone()

    assert tuple(history) == ("legacy agreement", "12.5", "terminated")
    assert tuple(report_history) == ("12500.00", "12.5", contract_id, "unsettled")
