import io
import sqlite3
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from app.distribution_erp import create_router

def factory(path):
    def db():
        c=sqlite3.connect(path,timeout=10);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");return c
    with db() as c:
        c.executescript("""
        CREATE TABLE tenants(id INTEGER PRIMARY KEY,name TEXT,industry TEXT);
        CREATE TABLE users(id INTEGER PRIMARY KEY,tenant_id INTEGER,email TEXT,salt TEXT,password_hash TEXT);
        CREATE TABLE products(id INTEGER PRIMARY KEY,tenant_id INTEGER,sku TEXT,name TEXT,price REAL,stock REAL,UNIQUE(tenant_id,sku));
        CREATE TABLE customers(id INTEGER PRIMARY KEY,tenant_id INTEGER,name TEXT,phone TEXT);
        CREATE TABLE audit_log(id INTEGER PRIMARY KEY,tenant_id INTEGER,action TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO tenants VALUES(1,'One','distribution');INSERT INTO tenants VALUES(2,'Two','distribution');
        INSERT INTO customers VALUES(1,1,'Customer One','111');INSERT INTO customers VALUES(2,2,'Customer Two','222');
        INSERT INTO products VALUES(1,1,'SKU1','Item One',10,20);INSERT INTO products VALUES(2,2,'SKU1','Item Two',10,20);
        """)
    return db

def client(db,tid):
    app=FastAPI();app.include_router(create_router(db,lambda:{'tenant_id':tid,'id':tid}))
    return TestClient(app)

def test_sales_posting_is_balanced_and_tenant_scoped(tmp_path):
    db=factory(tmp_path/'db.sqlite');c=client(db,1)
    r=c.post('/api/distribution/sales',json={'order_no':'SO-1','customer_id':1,'order_date':'2026-10-20','lines':[{'product_id':1,'quantity':2,'unit_price':'12.50','discount':'0'}]})
    assert r.status_code==200,r.text
    oid=r.json()['id'];posted=c.post(f'/api/distribution/sales/{oid}/post')
    assert posted.status_code==200,posted.text
    assert posted.json()['revenue']=='25.00'
    assert c.get('/api/distribution/reports/trial-balance').json()['balanced'] is True
    assert c.get('/api/distribution/overview').json()['sales_orders']==1
    other=client(db,2)
    assert other.get('/api/distribution/overview').json()['sales_orders']==0
    assert other.post(f'/api/distribution/sales/{oid}/post').status_code==404

def test_insufficient_stock_is_rejected_at_dispatch_not_invoice_posting(tmp_path):
    db=factory(tmp_path/'db.sqlite');c=client(db,1)
    order=c.post('/api/distribution/sales',json={'order_no':'SO-2','customer_id':1,'order_date':'2026-10-20','lines':[{'product_id':1,'quantity':200,'unit_price':'1'}]}).json()
    r=c.post(f"/api/distribution/sales/{order['id']}/post")
    assert r.status_code==200,r.text
    with db() as conn:
        assert conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0] == 20
    dispatched=c.post(f"/api/distribution/sales/{order['id']}/deliver",json={"delivery_date":"2026-10-21"})
    assert dispatched.status_code==409
    with db() as conn:
        assert conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0] == 20
        assert conn.execute("SELECT status FROM dist_sales WHERE tenant_id=1 AND id=?",(order['id'],)).fetchone()[0] == "POSTED"
        assert conn.execute("SELECT COUNT(*) FROM dist_deliveries WHERE tenant_id=1").fetchone()[0] == 0
    assert c.get('/api/distribution/reports/trial-balance').json()['balanced'] is True

def test_xlsx_template_and_staged_import(tmp_path):
    db=factory(tmp_path/'db.sqlite');c=client(db,1)
    t=c.get('/api/distribution/import/template/customers')
    assert t.status_code==200 and t.headers['content-type'].startswith('application/vnd.openxmlformats')
    w=Workbook();s=w.active;s.append(['کد مشتری','نام مشتری','موبایل','مانده طلب افتتاحیه']);s.append(['C-2','Customer Two New','555',0])
    b=io.BytesIO();w.save(b);b.seek(0)
    p=c.post('/api/distribution/import/customers/preview',files={'file':('customers.xlsx',b.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert p.status_code==200,p.text
    assert p.json()['valid'] is True
    done=c.post('/api/distribution/import/'+p.json()['batch_id']+'/commit')
    assert done.status_code==200,done.text
    assert done.json()['imported']==1
    assert c.post('/api/distribution/import/'+p.json()['batch_id']+'/commit').status_code==409

def test_import_preview_reports_missing_columns(tmp_path):
    db=factory(tmp_path/'db.sqlite');c=client(db,1)
    w=Workbook();w.active.append(['نام اشتباه']);b=io.BytesIO();w.save(b);b.seek(0)
    r=c.post('/api/distribution/import/items/preview',files={'file':('items.xlsx',b.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert r.status_code==422


def test_jalali_fiscal_year_close_and_carry_forward(tmp_path):
    db=factory(tmp_path/'fiscal.sqlite');c=client(db,1)
    y=c.post('/api/distribution/fiscal-years',json={'jalali_year':1405})
    assert y.status_code==200,y.text
    fy=y.json()
    assert fy['start_date']=='2026-03-21'
    assert fy['end_date']=='2027-03-20'
    assert c.post('/api/distribution/fiscal-years',json={'jalali_year':1405}).status_code==409
    nxt=c.post('/api/distribution/fiscal-years',json={'jalali_year':1406})
    assert nxt.status_code==200,nxt.text
    closed=c.post('/api/distribution/fiscal-years/'+str(fy['id'])+'/close')
    assert closed.status_code==200,closed.text
    carried=c.post('/api/distribution/fiscal-years/'+str(fy['id'])+'/carry-forward')
    assert carried.status_code==200,carried.text
    assert carried.json()['to_year']==1406
    assert c.post('/api/distribution/fiscal-years/'+str(fy['id'])+'/carry-forward').status_code==409

def test_fiscal_year_close_blocks_new_journals_in_closed_year(tmp_path):
    db=factory(tmp_path/'fiscal-lock.sqlite');c=client(db,1)
    fy=c.post('/api/distribution/fiscal-years',json={'jalali_year':1405}).json()
    assert c.post('/api/distribution/fiscal-years/'+str(fy['id'])+'/close').status_code==200
    order=c.post('/api/distribution/sales',json={'order_no':'SO-LOCK','customer_id':1,'order_date':'2026-04-01','lines':[{'product_id':1,'quantity':1,'unit_price':'10'}]})
    assert order.status_code==200,order.text
    posted=c.post('/api/distribution/sales/'+str(order.json()['id'])+'/post')
    assert posted.status_code==409


def _posted_invoice(client, order_no, customer_id=1, product_id=1, price="10"):
    created = client.post("/api/distribution/sales", json={
        "order_no": order_no,
        "customer_id": customer_id,
        "order_date": "2026-10-20",
        "lines": [{"product_id": product_id, "quantity": 1, "unit_price": price}],
    })
    assert created.status_code == 200, created.text
    order_id = created.json()["id"]
    posted = client.post(f"/api/distribution/sales/{order_id}/post")
    assert posted.status_code == 200, posted.text
    return order_id


def test_dispatch_manifest_totals_and_tenant_isolation(tmp_path):
    db = factory(tmp_path / "dispatch.sqlite")
    c = client(db, 1)
    first = _posted_invoice(c, "SO-MAN-1")
    second = _posted_invoice(c, "SO-MAN-2", price="20")
    with db() as conn:
        stock_before = conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0]
        journal_count_before = conn.execute("SELECT COUNT(*) FROM dist_journals WHERE tenant_id=1").fetchone()[0]

    response = c.post("/api/distribution/dispatch/manifests", json={
        "manifest_no": "MAN-2026-001",
        "dispatch_date": "2026-10-21",
        "distributor_name": "Route A",
        "invoices": [
            {"order_id": first, "cash_amount": "10.00", "check_amount": "0", "credit_amount": "0"},
            {"order_id": second, "cash_amount": "0", "check_amount": "5.00", "credit_amount": "15.00"},
        ],
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["invoice_count"] == 2
    assert data["total"] == "30.00"
    assert data["cash_total"] == "10.00"
    assert data["check_total"] == "5.00"
    assert data["credit_total"] == "15.00"

    listed = c.get("/api/distribution/dispatch/manifests")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    detail = c.get(f"/api/distribution/dispatch/manifests/{data['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["invoices"]) == 2
    other = client(db, 2)
    assert other.get(f"/api/distribution/dispatch/manifests/{data['id']}").status_code == 404
    assert other.get("/api/distribution/dispatch/manifests").json() == []
    with db() as conn:
        stock_after = conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0]
        journal_count_after = conn.execute("SELECT COUNT(*) FROM dist_journals WHERE tenant_id=1").fetchone()[0]
    assert stock_after == stock_before
    assert journal_count_after == journal_count_before


def test_dispatch_manifest_rejects_invalid_allocations_and_duplicate_manifest(tmp_path):
    db = factory(tmp_path / "dispatch-invalid.sqlite")
    c = client(db, 1)
    order_id = _posted_invoice(c, "SO-MAN-INVALID")
    base = {
        "manifest_no": "MAN-UNIQUE",
        "dispatch_date": "2026-10-21",
        "distributor_name": "Route B",
        "invoices": [{"order_id": order_id, "cash_amount": "10", "check_amount": "0", "credit_amount": "0"}],
    }
    mismatch = {**base, "manifest_no": "MAN-MISMATCH",
                "invoices": [{"order_id": order_id, "cash_amount": "9", "check_amount": "0", "credit_amount": "0"}]}
    assert c.post("/api/distribution/dispatch/manifests", json=mismatch).status_code == 422

    duplicate_invoice = {**base, "manifest_no": "MAN-REPEATED",
        "invoices": [base["invoices"][0], base["invoices"][0]]}
    assert c.post("/api/distribution/dispatch/manifests", json=duplicate_invoice).status_code == 422

    other = client(db, 2)
    cross_tenant = {**base, "manifest_no": "MAN-CROSS-TENANT"}
    assert other.post("/api/distribution/dispatch/manifests", json=cross_tenant).status_code == 404

    first = c.post("/api/distribution/dispatch/manifests", json=base)
    assert first.status_code == 200, first.text
    another_order = _posted_invoice(c, "SO-MAN-DUPLICATE")
    duplicate_number = {**base, "invoices": [
        {"order_id": another_order, "cash_amount": "10", "check_amount": "0", "credit_amount": "0"}
    ]}
    assert c.post("/api/distribution/dispatch/manifests", json=duplicate_number).status_code == 409
    another_manifest = {**base, "manifest_no": "MAN-ALREADY-ASSIGNED"}
    assert c.post("/api/distribution/dispatch/manifests", json=another_manifest).status_code == 409


def test_dispatch_collection_remittance_and_check_lifecycle(tmp_path):
    db = factory(tmp_path / "dispatch-settlement.sqlite")
    c = client(db, 1)
    order_id = _posted_invoice(c, "SO-SETTLE")
    manifest = c.post("/api/distribution/dispatch/manifests", json={
        "manifest_no": "MAN-SETTLE",
        "dispatch_date": "2026-10-21",
        "distributor_name": "Route Settlement",
        "invoices": [{"order_id": order_id, "cash_amount": "6", "check_amount": "4", "credit_amount": "0"}],
    })
    assert manifest.status_code == 200, manifest.text
    mid = manifest.json()["id"]
    dispatched=c.post(f"/api/distribution/dispatch/manifests/{mid}/dispatch")
    assert dispatched.status_code==200,dispatched.text
    assert dispatched.json()["invoice_count"]==1
    cash = c.post(f"/api/distribution/dispatch/manifests/{mid}/collections", json={
        "order_id": order_id, "payment_type": "CASH", "amount": "6",
        "txn_date": "2026-10-21", "reference": "cash-001",
    })
    assert cash.status_code == 200, cash.text
    check = c.post(f"/api/distribution/dispatch/manifests/{mid}/collections", json={
        "order_id": order_id, "payment_type": "CHECK", "amount": "4",
        "txn_date": "2026-10-21", "reference": "check-001",
    })
    assert check.status_code == 200, check.text
    assert c.post(f"/api/distribution/dispatch/manifests/{mid}/collections", json={
        "order_id": order_id, "payment_type": "CASH", "amount": "0.01",
        "txn_date": "2026-10-21",
    }).status_code == 409

    assert c.post(f"/api/distribution/dispatch/transactions/{check.json()['id']}/clear-check", json={
        "txn_date": "2026-10-22"
    }).status_code == 409
    handed = c.post(f"/api/distribution/dispatch/transactions/{check.json()['id']}/handoff-check")
    assert handed.status_code == 200, handed.text
    cleared = c.post(f"/api/distribution/dispatch/transactions/{check.json()['id']}/clear-check", json={
        "txn_date": "2026-10-22"
    })
    assert cleared.status_code == 200, cleared.text
    assert c.post(f"/api/distribution/dispatch/transactions/{check.json()['id']}/clear-check", json={
        "txn_date": "2026-10-22"
    }).status_code == 409

    account = c.post("/api/distribution/treasury/accounts", json={
        "code": "BANK-SETTLE", "name": "Company bank", "kind": "BANK", "opening_balance": "0"
    })
    assert account.status_code == 200, account.text
    remittance = c.post(f"/api/distribution/dispatch/manifests/{mid}/remittances", json={
        "cash_code": "BANK-SETTLE", "amount": "6",
        "txn_date": "2026-10-21", "reference": "remit-001",
    })
    assert remittance.status_code == 200, remittance.text
    assert c.post(f"/api/distribution/dispatch/manifests/{mid}/remittances", json={
        "cash_code": "BANK-SETTLE", "amount": "0.01",
        "txn_date": "2026-10-21",
    }).status_code == 409

    summary = c.get(f"/api/distribution/dispatch/manifests/{mid}/settlement")
    assert summary.status_code == 200, summary.text
    assert len(summary.json()["transactions"]) == 3
    receivables = c.get("/api/distribution/reports/receivables")
    assert receivables.status_code == 200, receivables.text
    assert receivables.json()["total_outstanding"] == "0.00"
    assert c.get("/api/distribution/reports/trial-balance").json()["balanced"] is True
    assert c.get("/api/distribution/treasury/accounts").json()[0]["balance"] == "6.00"

    other = client(db, 2)
    assert other.get(f"/api/distribution/dispatch/manifests/{mid}/settlement").status_code == 404
    assert other.post(f"/api/distribution/dispatch/transactions/{check.json()['id']}/handoff-check").status_code == 404


def test_sales_return_approval_restores_stock_and_reverses_receivable(tmp_path):
    db = factory(tmp_path / "returns.sqlite")
    c = client(db, 1)
    created = c.post("/api/distribution/sales", json={
        "order_no": "SO-RETURN", "customer_id": 1, "order_date": "2026-10-20",
        "lines": [{"product_id": 1, "quantity": 2, "unit_price": "10.00"}],
    })
    assert created.status_code == 200, created.text
    order_id = created.json()["id"]
    assert c.post(f"/api/distribution/sales/{order_id}/post").status_code == 200
    with db() as conn:
        assert conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0] == 20
    before_delivery=c.post("/api/distribution/returns",json={"order_id":order_id,"return_no":"RET-TOO-EARLY","return_date":"2026-10-21","lines":[{"product_id":1,"quantity":"1"}]})
    assert before_delivery.status_code==409
    delivered=c.post(f"/api/distribution/sales/{order_id}/deliver",json={"delivery_date":"2026-10-21"})
    assert delivered.status_code==200,delivered.text
    with db() as conn:
        assert conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0] == 18
    draft = c.post("/api/distribution/returns", json={
        "order_id": order_id, "return_no": "RET-1", "return_date": "2026-10-21",
        "reason": "damaged packaging", "lines": [{"product_id": 1, "quantity": "1"}],
    })
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "DRAFT"
    with db() as conn:
        assert conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0] == 18
    approved = c.post(f"/api/distribution/returns/{draft.json()['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["revenue_reversed"] == "10.00"
    with db() as conn:
        assert conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0] == 19
        assert conn.execute("SELECT COUNT(*) FROM dist_stock_moves WHERE tenant_id=1 AND kind='RETURN_IN'").fetchone()[0] == 1
    assert c.get("/api/distribution/reports/receivables").json()["total_outstanding"] == "10.00"
    assert c.get("/api/distribution/reports/trial-balance").json()["balanced"] is True
    assert c.post(f"/api/distribution/returns/{draft.json()['id']}/approve").status_code == 409


def test_sales_return_cannot_exceed_sold_quantity_or_cross_tenant(tmp_path):
    db = factory(tmp_path / "returns-tenant.sqlite")
    c = client(db, 1)
    order_id = _posted_invoice(c, "SO-RETURN-LIMIT")
    assert c.post(f"/api/distribution/sales/{order_id}/deliver",json={"delivery_date":"2026-10-21"}).status_code==200
    invalid = c.post("/api/distribution/returns", json={
        "order_id": order_id, "return_no": "RET-OVER", "return_date": "2026-10-21",
        "lines": [{"product_id": 1, "quantity": "2"}],
    })
    assert invalid.status_code == 409
    other = client(db, 2)
    assert other.post("/api/distribution/returns", json={
        "order_id": order_id, "return_no": "RET-CROSS", "return_date": "2026-10-21",
        "lines": [{"product_id": 1, "quantity": "1"}],
    }).status_code == 404


def test_manifest_dispatch_is_atomic_and_posts_cogs_only_after_stock_is_available(tmp_path):
    db = factory(tmp_path / "dispatch-atomic.sqlite")
    c = client(db, 1)
    first = c.post("/api/distribution/sales", json={
        "order_no": "SO-DISPATCH-OK", "customer_id": 1, "order_date": "2026-10-20",
        "lines": [{"product_id": 1, "quantity": 1, "unit_price": "10"}],
    }).json()
    second = c.post("/api/distribution/sales", json={
        "order_no": "SO-DISPATCH-FAIL", "customer_id": 1, "order_date": "2026-10-20",
        "lines": [{"product_id": 1, "quantity": 200, "unit_price": "1"}],
    }).json()
    assert c.post(f"/api/distribution/sales/{first['id']}/post").status_code == 200
    assert c.post(f"/api/distribution/sales/{second['id']}/post").status_code == 200
    with db() as conn:
        before_stock = conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0]
        before_deliveries = conn.execute("SELECT COUNT(*) FROM dist_deliveries WHERE tenant_id=1").fetchone()[0]
    manifest = c.post("/api/distribution/dispatch/manifests", json={
        "manifest_no": "MAN-ATOMIC", "dispatch_date": "2026-10-21", "distributor_name": "Route A",
        "invoices": [
            {"order_id": first["id"], "cash_amount": "10", "check_amount": "0", "credit_amount": "0"},
            {"order_id": second["id"], "cash_amount": "200", "check_amount": "0", "credit_amount": "0"},
        ],
    })
    assert manifest.status_code == 200, manifest.text
    failed = c.post(f"/api/distribution/dispatch/manifests/{manifest.json()['id']}/dispatch")
    assert failed.status_code == 409
    with db() as conn:
        assert conn.execute("SELECT stock FROM products WHERE tenant_id=1 AND id=1").fetchone()[0] == before_stock
        assert conn.execute("SELECT COUNT(*) FROM dist_deliveries WHERE tenant_id=1").fetchone()[0] == before_deliveries
        statuses = conn.execute("SELECT status FROM dist_sales WHERE tenant_id=1 ORDER BY id").fetchall()
        assert [x[0] for x in statuses] == ["POSTED", "POSTED"]
    assert c.get("/api/distribution/reports/trial-balance").json()["balanced"] is True
