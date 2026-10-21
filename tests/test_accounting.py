import uuid
from fastapi.testclient import TestClient
from app.main import app

def account():
    c=TestClient(app); s=uuid.uuid4().hex[:10]
    r=c.post("/api/register",json={"company_name":"GL "+s,"industry":"distribution","email":"gl-"+s+"@example.com","password":"test-password-2026"})
    assert r.status_code==200,r.text
    return c,{"Authorization":"Bearer "+r.json()["token"]}

def test_double_entry_and_reports():
    c,h=account()
    assert c.get("/api/accounting/accounts",headers=h).status_code==200
    r=c.post("/api/accounting/journals",headers=h,json={"journal_date":"2026-10-21","description":"فاکتور آزمون","source_ref":"GL-TEST-1","lines":[{"account_code":"1100","debit":"125","credit":"0"},{"account_code":"4000","debit":"0","credit":"125"}]})
    assert r.status_code==200,r.text
    jid=r.json()["id"]
    assert c.post(f"/api/accounting/journals/{jid}/post",headers=h).json()["status"]=="posted"
    tb=c.get("/api/accounting/trial-balance",headers=h).json()
    assert tb["balanced"] and tb["total_debit"]==tb["total_credit"]==125

def test_rejects_unbalanced_and_duplicate_reference():
    c,h=account()
    r=c.post("/api/accounting/journals",headers=h,json={"journal_date":"2026-10-21","description":"سند نامتوازن","lines":[{"account_code":"1100","debit":"100","credit":"0"},{"account_code":"4000","debit":"0","credit":"90"}]})
    assert r.status_code==422
    p={"journal_date":"2026-10-21","document_ref":"INV-42","party":"مشتری","amount":"250"}
    assert c.post("/api/accounting/automation/sales-voucher",headers=h,json=p).status_code==200
    assert c.post("/api/accounting/automation/sales-voucher",headers=h,json=p).status_code==409

def test_tenant_isolation():
    c,a=account(); _,b=account()
    r=c.post("/api/accounting/journals",headers=a,json={"journal_date":"2026-10-21","description":"خصوصی","source_ref":"PRIVATE-A","lines":[{"account_code":"1100","debit":"50","credit":"0"},{"account_code":"4000","debit":"0","credit":"50"}]})
    assert r.status_code==200,r.text
    assert any(x["source_ref"]=="PRIVATE-A" for x in c.get("/api/accounting/journals",headers=a).json())
    assert all(x["source_ref"]!="PRIVATE-A" for x in c.get("/api/accounting/journals",headers=b).json())
