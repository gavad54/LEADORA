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

def test_sale_rejects_insufficient_stock_without_posting(tmp_path):
    db=factory(tmp_path/'db.sqlite');c=client(db,1)
    order=c.post('/api/distribution/sales',json={'order_no':'SO-2','customer_id':1,'order_date':'2026-10-20','lines':[{'product_id':1,'quantity':200,'unit_price':'1'}]}).json()
    r=c.post(f"/api/distribution/sales/{order['id']}/post")
    assert r.status_code==409
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
