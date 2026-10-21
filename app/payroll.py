"""Tenant-scoped payroll calculations and configurable sales commissions.

This module calculates draft payroll only. It never pays wages or moves money.
"""
import re
import sqlite3
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

BASES = {"BOOKED_SALES", "COLLECTED_SALES", "RETURNS", "CREDIT_SALES"}

def minor(value):
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise HTTPException(422, "مبلغ نامعتبر است.") from exc
    if not amount.is_finite() or abs(amount) > Decimal("1000000000000"):
        raise HTTPException(422, "مبلغ خارج از محدوده مجاز است.")
    return int(amount * 100)

def money(value):
    return format(Decimal(int(value or 0)) / 100, ".2f")

def tenant(user):
    value = user.get("tenant_id") if isinstance(user, dict) else None
    if value is None:
        value = user.get("company_id") if isinstance(user, dict) else None
    if value is None:
        raise HTTPException(401, "شرکت کاربر مشخص نیست.")
    return int(value)

def audit(conn, tid, action):
    conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (tid, action))

class EmployeeIn(BaseModel):
    employee_no: str = Field(min_length=1, max_length=60)
    full_name: str = Field(min_length=1, max_length=160)
    fixed_salary: Decimal = Field(ge=0, le=Decimal("1000000000000"))
    active: bool = True

class CommissionRuleIn(BaseModel):
    basis: str = Field(pattern="^(BOOKED_SALES|COLLECTED_SALES|RETURNS|CREDIT_SALES)$")
    rate_percent: Decimal = Field(ge=0, le=100)

class SaleAssignmentIn(BaseModel):
    order_id: int = Field(gt=0)
    employee_id: int = Field(gt=0)

class PayrollRunIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

def create_router(db, user_dep):
    r = APIRouter(prefix="/api/payroll", tags=["payroll"])
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS payroll_employees(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, employee_no TEXT NOT NULL,
          full_name TEXT NOT NULL, fixed_salary_minor INTEGER NOT NULL CHECK(fixed_salary_minor>=0),
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tenant_id,employee_no)
        );
        CREATE TABLE IF NOT EXISTS payroll_commission_rules(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, employee_id INTEGER NOT NULL,
          basis TEXT NOT NULL CHECK(basis IN ('BOOKED_SALES','COLLECTED_SALES','RETURNS','CREDIT_SALES')),
          rate_bps INTEGER NOT NULL CHECK(rate_bps>=0 AND rate_bps<=10000),
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tenant_id,employee_id)
        );
        CREATE TABLE IF NOT EXISTS payroll_sale_assignments(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, order_id INTEGER NOT NULL,
          employee_id INTEGER NOT NULL, assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tenant_id,order_id)
        );
        CREATE TABLE IF NOT EXISTS payroll_runs(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, period TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','APPROVED')),
          created_by INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, approved_at TEXT,
          UNIQUE(tenant_id,period)
        );
        CREATE TABLE IF NOT EXISTS payroll_lines(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, run_id INTEGER NOT NULL REFERENCES payroll_runs(id),
          employee_id INTEGER NOT NULL, salary_minor INTEGER NOT NULL, basis TEXT NOT NULL,
          basis_amount_minor INTEGER NOT NULL, commission_minor INTEGER NOT NULL, total_minor INTEGER NOT NULL,
          UNIQUE(tenant_id,run_id,employee_id)
        );
        CREATE INDEX IF NOT EXISTS idx_payroll_assignments_employee ON payroll_sale_assignments(tenant_id,employee_id,order_id);
        """)

    @r.get("/employees")
    def employees(u=Depends(user_dep)):
        t = tenant(u)
        with db() as c:
            rows = c.execute("""SELECT e.*,r.basis,r.rate_bps FROM payroll_employees e
              LEFT JOIN payroll_commission_rules r ON r.tenant_id=e.tenant_id AND r.employee_id=e.id
              WHERE e.tenant_id=? ORDER BY e.employee_no""", (t,)).fetchall()
        return [{"id":x["id"],"employee_no":x["employee_no"],"full_name":x["full_name"],
          "fixed_salary":money(x["fixed_salary_minor"]),"active":bool(x["active"]),
          "commission_basis":x["basis"],"commission_rate_percent":money(x["rate_bps"] if x["rate_bps"] is not None else 0)} for x in rows]

    @r.post("/employees")
    def add_employee(b: EmployeeIn, u=Depends(user_dep)):
        t = tenant(u)
        number, name = b.employee_no.strip(), b.full_name.strip()
        if not number or not name:
            raise HTTPException(422, "شماره و نام کارمند الزامی است.")
        with db() as c:
            try:
                eid = c.execute("INSERT INTO payroll_employees(tenant_id,employee_no,full_name,fixed_salary_minor,active) VALUES(?,?,?,?,?)",
                    (t,number,name,minor(b.fixed_salary),int(b.active))).lastrowid
            except sqlite3.IntegrityError:
                raise HTTPException(409, "شماره کارمند تکراری است.")
            audit(c,t,"payroll.employee.created:"+number)
        return {"id":eid,"employee_no":number,"status":"created"}

    @r.post("/employees/{employee_id}/commission-rule")
    def set_rule(employee_id:int,b:CommissionRuleIn,u=Depends(user_dep)):
        t=tenant(u);rate=int((b.rate_percent*100).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
        with db() as c:
            if not c.execute("SELECT 1 FROM payroll_employees WHERE tenant_id=? AND id=?",(t,employee_id)).fetchone():
                raise HTTPException(404,"کارمند در شرکت شما یافت نشد.")
            c.execute("""INSERT INTO payroll_commission_rules(tenant_id,employee_id,basis,rate_bps,updated_at)
              VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(tenant_id,employee_id) DO UPDATE SET
              basis=excluded.basis,rate_bps=excluded.rate_bps,updated_at=CURRENT_TIMESTAMP""",(t,employee_id,b.basis,rate))
            audit(c,t,"payroll.commission_rule.updated:"+str(employee_id)+":"+b.basis)
        return {"employee_id":employee_id,"basis":b.basis,"rate_percent":str(b.rate_percent)}

    @r.post("/assignments")
    def assign_sale(b:SaleAssignmentIn,u=Depends(user_dep)):
        t=tenant(u)
        with db() as c:
            emp=c.execute("SELECT id FROM payroll_employees WHERE tenant_id=? AND id=? AND active=1",(t,b.employee_id)).fetchone()
            if not emp: raise HTTPException(404,"کارمند فعال در شرکت شما یافت نشد.")
            sale=c.execute("SELECT id,status FROM dist_sales WHERE tenant_id=? AND id=?",(t,b.order_id)).fetchone()
            if not sale: raise HTTPException(404,"فاکتور در شرکت شما یافت نشد.")
            if sale["status"] not in ("POSTED","DELIVERED"): raise HTTPException(409,"فقط فاکتور نهایی‌شده قابل انتساب است.")
            try:
                c.execute("INSERT INTO payroll_sale_assignments(tenant_id,order_id,employee_id) VALUES(?,?,?)",(t,b.order_id,b.employee_id))
            except sqlite3.IntegrityError:
                raise HTTPException(409,"این فاکتور قبلاً به یک کارمند منتسب شده است.")
            audit(c,t,"payroll.sale.assigned:"+str(b.order_id)+":"+str(b.employee_id))
        return {"order_id":b.order_id,"employee_id":b.employee_id,"status":"assigned"}

    @r.get("/assignments")
    def assignments(u=Depends(user_dep)):
        t=tenant(u)
        with db() as c:
            rows=c.execute("""SELECT a.order_id,s.order_no,s.order_date,s.total_minor,s.status,e.id employee_id,e.employee_no,e.full_name
              FROM payroll_sale_assignments a JOIN dist_sales s ON s.id=a.order_id AND s.tenant_id=a.tenant_id
              JOIN payroll_employees e ON e.id=a.employee_id AND e.tenant_id=a.tenant_id
              WHERE a.tenant_id=? ORDER BY a.id DESC LIMIT 500""",(t,)).fetchall()
        return [{"order_id":x["order_id"],"order_no":x["order_no"],"order_date":x["order_date"],
          "sales_total":money(x["total_minor"]),"status":x["status"],"employee_id":x["employee_id"],
          "employee_no":x["employee_no"],"employee_name":x["full_name"]} for x in rows]

    @r.get("/runs")
    def runs(u=Depends(user_dep)):
        t=tenant(u)
        with db() as c:
            rows=c.execute("""SELECT r.*,COUNT(l.id) employee_count,COALESCE(SUM(l.salary_minor),0) salary,
              COALESCE(SUM(l.commission_minor),0) commission,COALESCE(SUM(l.total_minor),0) total
              FROM payroll_runs r LEFT JOIN payroll_lines l ON l.run_id=r.id AND l.tenant_id=r.tenant_id
              WHERE r.tenant_id=? GROUP BY r.id ORDER BY r.period DESC""",(t,)).fetchall()
        return [{"id":x["id"],"period":x["period"],"status":x["status"],"employee_count":x["employee_count"],
          "salary_total":money(x["salary"]),"commission_total":money(x["commission"]),"payroll_total":money(x["total"])} for x in rows]

    @r.post("/runs")
    def create_run(b:PayrollRunIn,u=Depends(user_dep)):
        t=tenant(u);year,month=map(int,b.period.split("-"));first=date(year,month,1)
        next_month=date(year+1,1,1) if month==12 else date(year,month+1,1)
        start,end=first.isoformat(),next_month.isoformat()
        with db() as c:
            if c.execute("SELECT 1 FROM payroll_runs WHERE tenant_id=? AND period=?",(t,b.period)).fetchone():
                raise HTTPException(409,"برای این دوره حقوق قبلاً محاسبه شده است.")
            if c.execute("SELECT 1 FROM dist_period_locks WHERE tenant_id=? AND period=?",(t,b.period)).fetchone():
                raise HTTPException(409,"دوره مالی بسته است.")
            fy=c.execute("SELECT status FROM dist_fiscal_years WHERE tenant_id=? AND start_date<=? AND end_date>=?",(t,start,start)).fetchone()
            if fy and fy["status"]=="CLOSED": raise HTTPException(409,"سال مالی بسته شده است.")
            emps=c.execute("""SELECT e.*,r.basis,r.rate_bps FROM payroll_employees e
              LEFT JOIN payroll_commission_rules r ON r.tenant_id=e.tenant_id AND r.employee_id=e.id
              WHERE e.tenant_id=? AND e.active=1 ORDER BY e.id""",(t,)).fetchall()
            if not emps: raise HTTPException(409,"ابتدا حداقل یک کارمند فعال تعریف کنید.")
            run_id=c.execute("INSERT INTO payroll_runs(tenant_id,period,created_by) VALUES(?,?,?)",(t,b.period,u.get("id"))).lastrowid
            for emp in emps:
                basis=emp["basis"] or "BOOKED_SALES";rate=emp["rate_bps"] or 0
                sales=c.execute("""SELECT s.id,s.total_minor FROM payroll_sale_assignments a
                  JOIN dist_sales s ON s.id=a.order_id AND s.tenant_id=a.tenant_id
                  WHERE a.tenant_id=? AND a.employee_id=? AND s.status IN ('POSTED','DELIVERED')
                    AND s.order_date>=? AND s.order_date<?""",(t,emp["id"],start,end)).fetchall()
                order_ids=[x["id"] for x in sales]
                receipts_period=0;returns_period=0;returns_all=0;receipts_all_by_order={}
                outstanding_basis=0
                for sale in sales:
                    receipts_all=c.execute("SELECT COALESCE(SUM(amount_minor),0) FROM dist_customer_receipts WHERE tenant_id=? AND order_id=?",(t,sale["id"])).fetchone()[0]
                    returns_all_one=c.execute("""SELECT COALESCE(SUM(l.revenue_minor),0) FROM dist_sales_return_lines l
                      JOIN dist_sales_returns r ON r.id=l.return_id AND r.tenant_id=l.tenant_id
                      WHERE r.tenant_id=? AND r.order_id=? AND r.status='APPROVED'""",(t,sale["id"])).fetchone()[0]
                    receipts_all_by_order[sale["id"]]=(receipts_all,returns_all_one)
                    outstanding_basis+=max(0,sale["total_minor"]-receipts_all-returns_all_one)
                if order_ids:
                    marks=",".join("?" for _ in order_ids)
                    receipts_period=c.execute("SELECT COALESCE(SUM(amount_minor),0) FROM dist_customer_receipts WHERE tenant_id=? AND order_id IN ("+marks+") AND txn_date>=? AND txn_date<?",(t,*order_ids,start,end)).fetchone()[0]
                    returns_period=c.execute("""SELECT COALESCE(SUM(l.revenue_minor),0) FROM dist_sales_return_lines l
                      JOIN dist_sales_returns r ON r.id=l.return_id AND r.tenant_id=l.tenant_id
                      WHERE r.tenant_id=? AND r.order_id IN ("""+marks+""") AND r.status='APPROVED' AND r.return_date>=? AND r.return_date<?""",(t,*order_ids,start,end)).fetchone()[0]
                    returns_all=sum(v[1] for v in receipts_all_by_order.values())
                booked=sum(x["total_minor"] for x in sales)
                if basis=="BOOKED_SALES":amount=max(0,booked-returns_period)
                elif basis=="COLLECTED_SALES":amount=receipts_period
                elif basis=="RETURNS":amount=returns_period
                else:amount=outstanding_basis
                commission=int((Decimal(amount)*Decimal(rate)/Decimal(10000)).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
                if basis=="RETURNS": commission=-commission
                salary=emp["fixed_salary_minor"];total=salary+commission
                c.execute("""INSERT INTO payroll_lines(tenant_id,run_id,employee_id,salary_minor,basis,basis_amount_minor,commission_minor,total_minor)
                  VALUES(?,?,?,?,?,?,?,?)""",(t,run_id,emp["id"],salary,basis,amount,commission,total))
            audit(c,t,"payroll.run.draft:"+b.period)
            lines=c.execute("""SELECT l.*,e.employee_no,e.full_name FROM payroll_lines l JOIN payroll_employees e
              ON e.id=l.employee_id AND e.tenant_id=l.tenant_id WHERE l.tenant_id=? AND l.run_id=? ORDER BY e.employee_no""",(t,run_id)).fetchall()
        return {"id":run_id,"period":b.period,"status":"DRAFT","lines":[{"employee_id":x["employee_id"],
          "employee_no":x["employee_no"],"full_name":x["full_name"],"salary":money(x["salary_minor"]),
          "commission_basis":x["basis"],"basis_amount":money(x["basis_amount_minor"]),
          "commission":money(x["commission_minor"]),"total":money(x["total_minor"]),
          "requires_review":x["total_minor"]<0} for x in lines]}

    @r.get("/runs/{run_id}")
    def run_detail(run_id:int,u=Depends(user_dep)):
        t=tenant(u)
        with db() as c:
            run=c.execute("SELECT * FROM payroll_runs WHERE tenant_id=? AND id=?",(t,run_id)).fetchone()
            if not run: raise HTTPException(404,"دوره حقوق در شرکت شما یافت نشد.")
            rows=c.execute("""SELECT l.*,e.employee_no,e.full_name FROM payroll_lines l JOIN payroll_employees e
              ON e.id=l.employee_id AND e.tenant_id=l.tenant_id WHERE l.tenant_id=? AND l.run_id=? ORDER BY e.employee_no""",(t,run_id)).fetchall()
        return {"id":run["id"],"period":run["period"],"status":run["status"],"lines":[{"employee_id":x["employee_id"],
          "employee_no":x["employee_no"],"full_name":x["full_name"],"salary":money(x["salary_minor"]),
          "commission_basis":x["basis"],"basis_amount":money(x["basis_amount_minor"]),
          "commission":money(x["commission_minor"]),"total":money(x["total_minor"]),"requires_review":x["total_minor"]<0} for x in rows]}

    @r.post("/runs/{run_id}/approve")
    def approve_run(run_id:int,u=Depends(user_dep)):
        t=tenant(u)
        with db() as c:
            run=c.execute("SELECT * FROM payroll_runs WHERE tenant_id=? AND id=?",(t,run_id)).fetchone()
            if not run: raise HTTPException(404,"دوره حقوق در شرکت شما یافت نشد.")
            if run["status"]!="DRAFT": raise HTTPException(409,"فقط محاسبه پیش‌نویس قابل تأیید است.")
            if c.execute("SELECT 1 FROM payroll_lines WHERE tenant_id=? AND run_id=? AND total_minor<0",(t,run_id)).fetchone():
                raise HTTPException(409,"مبلغ منفی نیازمند بازبینی انسانی است؛ این محاسبه تأیید نمی‌شود.")
            c.execute("UPDATE payroll_runs SET status='APPROVED',approved_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND id=? AND status='DRAFT'",(t,run_id))
            audit(c,t,"payroll.run.approved:"+run["period"])
        return {"id":run_id,"period":run["period"],"status":"APPROVED","payment_status":"NOT_PAID","note":"این تأیید، محاسبه حقوق را نهایی می‌کند و انتقال وجه انجام نمی‌دهد."}

    return r
