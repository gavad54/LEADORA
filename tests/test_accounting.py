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

def test_receipt_payment_and_csv_import():
    c,h=account()
    receipt={"journal_date":"2026-10-21","document_ref":"RCPT-1","party":"مشتری","amount":"40"}
    payment={"journal_date":"2026-10-21","document_ref":"PAY-1","party":"تامین‌کننده","amount":"15"}
    r=c.post("/api/accounting/automation/receipt-voucher",headers=h,json=receipt)
    assert r.status_code==200,r.text
    p=c.post("/api/accounting/automation/payment-voucher",headers=h,json=payment)
    assert p.status_code==200,p.text
    journals=c.get("/api/accounting/journals",headers=h).json()
    assert {j["source_type"] for j in journals}>={"receipt","payment"}
    csv_content="date,document_ref,type,amount,party,account_code,description\n2026-10-21,CSV-S-1,sales,120,مشتری,4000,فروش CSV\n2026-10-21,CSV-E-1,expense,30,فروشنده,6300,هزینه CSV\n"
    imported=c.post("/api/accounting/import/csv",headers=h,json={"content":csv_content})
    assert imported.status_code==200,imported.text
    assert imported.json()["count"]==2 and imported.json()["all_drafts"] is True

def test_expense_defaults_to_expense_account_and_rejects_wrong_group():
    c,h=account()
    p={"journal_date":"2026-10-21","document_ref":"EXP-DEFAULT-1","amount":"22"}
    r=c.post("/api/accounting/automation/expense-voucher",headers=h,json=p)
    assert r.status_code==200,r.text
    journal=next(j for j in c.get("/api/accounting/journals",headers=h).json() if j["source_ref"]=="EXP-DEFAULT-1")
    assert journal["lines"][0]["account_code"]=="6300"
    bad={**p,"document_ref":"EXP-BAD-1","account_code":"4000"}
    assert c.post("/api/accounting/automation/expense-voucher",headers=h,json=bad).status_code==422

def test_csv_import_rolls_back_on_duplicate_reference():
    c,h=account()
    content="date,document_ref,type,amount\n2026-10-21,CSV-DUP,sales,10\n2026-10-21,CSV-DUP,sales,20\n"
    r=c.post("/api/accounting/import/csv",headers=h,json={"content":content})
    assert r.status_code==409
    assert all(j["source_ref"]!="CSV-DUP" for j in c.get("/api/accounting/journals",headers=h).json())


def test_account_parent_must_exist_and_cannot_be_self():
    c,h=account()
    base={"code":"7000","name":"حساب آزمایشی","account_type":"expense","normal_side":"debit"}
    assert c.post("/api/accounting/accounts",headers=h,json={**base,"parent_code":"MISSING"}).status_code==422
    assert c.post("/api/accounting/accounts",headers=h,json={**base,"parent_code":"7000"}).status_code==422
    parent={"code":"7001","name":"هزینه‌های فرعی","account_type":"expense","normal_side":"debit"}
    assert c.post("/api/accounting/accounts",headers=h,json=parent).status_code==200
    child={"code":"7002","name":"هزینه بسته‌بندی","account_type":"expense","normal_side":"debit","parent_code":"7001"}
    assert c.post("/api/accounting/accounts",headers=h,json=child).status_code==200


def test_csv_import_accepts_utf8_bom():
    c,h=account()
    content="\ufeffdate,document_ref,type,amount\n2026-10-21,BOM-S-1,sales,15\n"
    r=c.post("/api/accounting/import/csv",headers=h,json={"content":content})
    assert r.status_code==200,r.text
    assert r.json()["count"]==1
