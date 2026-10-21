import uuid
from fastapi.testclient import TestClient
from app.main import app

def account():
    c = TestClient(app)
    suffix = uuid.uuid4().hex[:10]
    r = c.post("/api/register", json={"company_name":"Proc "+suffix,"industry":"trade","email":"proc-"+suffix+"@example.com","password":"test-password-2026"})
    assert r.status_code == 200, r.text
    return c, {"Authorization":"Bearer "+r.json()["token"]}

def test_procurement_need_tenant_isolation():
    a, ha = account()
    b, hb = account()
    r = a.post("/api/procurement/needs", headers=ha, json={"product_name":"پمپ صنعتی","quantity":10,"currency":"IRR"})
    assert r.status_code == 200, r.text
    need_id = r.json()["id"]
    assert len(a.get("/api/procurement/needs", headers=ha).json()) == 1
    assert b.get("/api/procurement/needs", headers=hb).json() == []
    assert b.post(f"/api/procurement/discover?need_id={need_id}", headers=hb).status_code == 404

def test_order_requires_explicit_approval_and_quote_tenant_scope():
    c, h = account()
    need = c.post("/api/procurement/needs", headers=h, json={"product_name":"کالای آزمایشی","quantity":4,"currency":"IRR"}).json()
    supplier = c.post("/api/procurement/suppliers", headers=h, json={"name":"تأمین‌کننده نمونه","website":"https://supplier.example"}).json()
    quote = c.post("/api/procurement/quotes", headers=h, json={"need_id":need["id"],"supplier_id":supplier["id"],"unit_price":120,"currency":"IRR"}).json()
    payload = {"need_id":need["id"],"quote_id":quote["id"],"quantity":4}
    assert c.post("/api/procurement/orders", headers=h, json=payload).status_code == 409
    payload["approved_by_user"] = True
    order = c.post("/api/procurement/orders", headers=h, json=payload)
    assert order.status_code == 200, order.text
    assert order.json()["total_amount"] == 480
    assert order.json()["status"] == "approved_for_supplier_confirmation"

def test_payment_record_does_not_claim_real_transfer():
    c, h = account()
    need = c.post("/api/procurement/needs", headers=h, json={"product_name":"کالای پرداخت","quantity":2,"currency":"IRR"}).json()
    supplier = c.post("/api/procurement/suppliers", headers=h, json={"name":"تأمین‌کننده پرداخت","website":"https://pay-supplier.example"}).json()
    quote = c.post("/api/procurement/quotes", headers=h, json={"need_id":need["id"],"supplier_id":supplier["id"],"unit_price":50,"currency":"IRR"}).json()
    order = c.post("/api/procurement/orders", headers=h, json={"need_id":need["id"],"quote_id":quote["id"],"quantity":2,"approved_by_user":True}).json()
    payment = c.post(f"/api/procurement/orders/{order['id']}/payments?amount=100&reference=TEST", headers=h)
    assert payment.status_code == 200, payment.text
    assert payment.json()["real_transfer"] is False
    assert payment.json()["status"] == "recorded_not_transferred"
