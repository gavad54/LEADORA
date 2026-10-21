from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.distribution_erp import create_router as create_distribution_router
from app.payroll import create_router as create_payroll_router


import sqlite3\n
def factory(path):
    def db():
        c = sqlite3.connect(path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c
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

def payroll_client(db, tid):
    app = FastAPI()
    user = lambda: {"tenant_id": tid, "id": tid}
    app.include_router(create_distribution_router(db, user))
    app.include_router(create_payroll_router(db, user))
    return TestClient(app)


def test_payroll_commission_run_is_tenant_scoped_and_does_not_pay(tmp_path):
    db = factory(tmp_path / "payroll.sqlite")
    c = payroll_client(db, 1)
    sale = c.post("/api/distribution/sales", json={
        "order_no": "SO-PAY-1", "customer_id": 1, "order_date": "2026-10-20",
        "lines": [{"product_id": 1, "quantity": 2, "unit_price": "50.00"}],
    })
    assert sale.status_code == 200, sale.text
    order_id = sale.json()["id"]
    assert c.post(f"/api/distribution/sales/{order_id}/post").status_code == 200

    employee = c.post("/api/payroll/employees", json={
        "employee_no": "EMP-1", "full_name": "Sales Person", "fixed_salary": "1000.00",
    })
    assert employee.status_code == 200, employee.text
    employee_id = employee.json()["id"]
    rule = c.post(f"/api/payroll/employees/{employee_id}/commission-rule", json={
        "basis": "BOOKED_SALES", "rate_percent": "10",
    })
    assert rule.status_code == 200, rule.text
    assert c.post("/api/payroll/assignments", json={
        "order_id": order_id, "employee_id": employee_id,
    }).status_code == 200

    run = c.post("/api/payroll/runs", json={"period": "2026-10"})
    assert run.status_code == 200, run.text
    line = run.json()["lines"][0]
    assert line["salary"] == "1000.00"
    assert line["basis_amount"] == "100.00"
    assert line["commission"] == "10.00"
    assert line["total"] == "1010.00"
    approved = c.post(f"/api/payroll/runs/{run.json()['id']}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["payment_status"] == "NOT_PAID"
    assert c.post(f"/api/payroll/runs/{run.json()['id']}/approve").status_code == 409
    assert c.post("/api/payroll/runs", json={"period": "2026-10"}).status_code == 409

    other = payroll_client(db, 2)
    assert other.get(f"/api/payroll/runs/{run.json()['id']}").status_code == 404
    assert other.post(f"/api/payroll/employees/{employee_id}/commission-rule", json={
        "basis": "BOOKED_SALES", "rate_percent": "10",
    }).status_code == 404


def test_payroll_rejects_invalid_period_and_duplicate_invoice_assignment(tmp_path):
    db = factory(tmp_path / "payroll-validation.sqlite")
    c = payroll_client(db, 1)
    sale = c.post("/api/distribution/sales", json={
        "order_no": "SO-PAY-2", "customer_id": 1, "order_date": "2026-10-20",
        "lines": [{"product_id": 1, "quantity": 1, "unit_price": "25.00"}],
    }).json()
    assert c.post(f"/api/distribution/sales/{sale['id']}/post").status_code == 200
    e1 = c.post("/api/payroll/employees", json={"employee_no":"EMP-2","full_name":"A","fixed_salary":"0"}).json()
    e2 = c.post("/api/payroll/employees", json={"employee_no":"EMP-3","full_name":"B","fixed_salary":"0"}).json()
    payload = {"order_id": sale["id"], "employee_id": e1["id"]}
    assert c.post("/api/payroll/assignments", json=payload).status_code == 200
    assert c.post("/api/payroll/assignments", json={**payload, "employee_id": e2["id"]}).status_code == 409
    assert c.post("/api/payroll/runs", json={"period": "2026-13"}).status_code == 422
