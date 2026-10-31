"""Commercial licensing, support desk, and auditable cross-module workflow queue."""
import json
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictInt

LICENSE_STATUSES = {"draft", "issued", "paid", "active", "expired", "cancelled"}
SUPPORT_STATUSES = {"open", "in_progress", "waiting_customer", "waiting_team", "resolved", "closed"}
SUPPORT_PRIORITIES = {"low", "normal", "high", "urgent"}
EVENT_ACTIONS = {
    "sales.order_created": [
        ("inventory.check", "بررسی موجودی و رزرو پیشنهادی", False),
        ("accounting.draft_sales_voucher", "تهیه پیش‌نویس سند فروش", False),
        ("dispatch.prepare", "تهیه پیش‌نویس آماده‌سازی و ارسال", True),
    ],
    "inventory.low_stock": [
        ("procurement.draft_replenishment", "تهیه پیش‌نویس درخواست تأمین", False),
        ("accounting.draft_purchase_voucher", "تهیه پیش‌نویس سند خرید", False),
    ],
    "dispatch.delivered": [
        ("accounting.draft_receivable", "تهیه پیش‌نویس حساب دریافتنی", False),
        ("sales.schedule_followup", "پیشنهاد پیگیری رضایت مشتری", True),
    ],
    "accounting.payment_due": [
        ("accounting.prepare_reminder", "تهیه پیش‌نویس یادآوری پرداخت", True),
    ],
    "payroll.period_ready": [
        ("accounting.draft_payroll_voucher", "تهیه پیش‌نویس سند حقوق", False),
        ("payroll.request_approval", "درخواست تأیید نهایی حقوق", True),
    ],
}

def create_router(db, user_from_header):
    router = APIRouter()

    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS commercial_license_sales(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          edition TEXT NOT NULL, term_months INTEGER NOT NULL CHECK(term_months BETWEEN 1 AND 120),
          amount NUMERIC NOT NULL CHECK(amount >= 0), currency TEXT NOT NULL DEFAULT 'IRR',
          status TEXT NOT NULL DEFAULT 'draft', invoice_ref TEXT NOT NULL DEFAULT '',
          support_until TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
          created_by INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_license_sales_tenant ON commercial_license_sales(tenant_id,id);
        CREATE TABLE IF NOT EXISTS support_tickets(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          subject TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'general',
          priority TEXT NOT NULL DEFAULT 'normal', status TEXT NOT NULL DEFAULT 'open',
          assigned_to TEXT NOT NULL DEFAULT '', resolution TEXT NOT NULL DEFAULT '',
          created_by INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_support_tickets_tenant ON support_tickets(tenant_id,status,priority,id);
        CREATE TABLE IF NOT EXISTS support_ticket_events(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, ticket_id INTEGER NOT NULL,
          actor_id INTEGER NOT NULL, event_type TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS commercial_workflow_runs(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          event_type TEXT NOT NULL, source_ref TEXT NOT NULL DEFAULT '', payload_json TEXT NOT NULL DEFAULT '{}',
          status TEXT NOT NULL DEFAULT 'proposed', created_by INTEGER NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS commercial_workflow_steps(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, run_id INTEGER NOT NULL,
          action_key TEXT NOT NULL, title TEXT NOT NULL, requires_approval INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'queued', decision_note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_commercial_workflows_tenant ON commercial_workflow_runs(tenant_id,id);
        """)

    def is_owner(user):
        import os
        ids = {x.strip() for x in os.getenv("LEADORA_OWNER_USER_IDS", "").split(",") if x.strip()}
        if str(user.get("id")) in ids:
            return True
        try:
            with db() as c:
                row = c.execute("SELECT user_id FROM finance_platform_owner WHERE singleton=1").fetchone()
            return bool(row and str(row["user_id"]) == str(user.get("id")))
        except Exception:
            return False

    class LicenseSaleIn(BaseModel):
        tenant_id: int = Field(gt=0)
        edition: str = Field(min_length=1, max_length=40)
        term_months: int = Field(ge=1, le=120)
        amount: StrictInt = Field(ge=0, le=1_000_000_000)
        currency: str = Field(default="IRR", pattern="^IRR$")
        invoice_ref: str = Field(default="", max_length=100)
        support_until: str = Field(default="", max_length=40)
        notes: str = Field(default="", max_length=2000)

    class LicenseSaleStatusIn(BaseModel):
        status: str
        note: str = Field(default="", max_length=1000)

    class TicketIn(BaseModel):
        subject: str = Field(min_length=3, max_length=200)
        description: str = Field(min_length=5, max_length=10000)
        category: str = Field(default="general", max_length=60)
        priority: str = "normal"

    class TicketUpdateIn(BaseModel):
        status: str
        assigned_to: str = Field(default="", max_length=160)
        resolution: str = Field(default="", max_length=5000)
        note: str = Field(default="", max_length=2000)

    class WorkflowEventIn(BaseModel):
        event_type: str = Field(min_length=3, max_length=100)
        source_ref: str = Field(default="", max_length=160)
        payload: dict = Field(default_factory=dict)

    class WorkflowDecisionIn(BaseModel):
        decision: str
        note: str = Field(default="", max_length=2000)

    @router.post("/api/platform/license-sales")
    def create_license_sale(body: LicenseSaleIn, user=Depends(user_from_header)):
        if os.getenv("LEADORA_ENFORCE_INSTANCE_CONFIG") == "1":
            raise HTTPException(404, "مدیریت فروش و صدور مجوز فقط در مرکز کنترل مالک انجام می‌شود.")
        if not is_owner(user):
            raise HTTPException(403, "ثبت فروش مجوز فقط برای مالک پلتفرم مجاز است.")
        if body.currency.upper() != "IRR":
            raise HTTPException(422, "واحد پول رسمی فقط ریال ایران (IRR) است.")
        with db() as c:
            if not c.execute("SELECT 1 FROM tenants WHERE id=?", (body.tenant_id,)).fetchone():
                raise HTTPException(404, "شرکت یافت نشد.")
            cur = c.execute("""INSERT INTO commercial_license_sales
              (tenant_id,edition,term_months,amount,currency,status,invoice_ref,support_until,notes,created_by)
              VALUES(?,?,?,?,?,'draft',?,?,?,?)""",
              (body.tenant_id,body.edition.strip(),body.term_months,body.amount,body.currency.upper(),
               body.invoice_ref.strip(),body.support_until.strip(),body.notes.strip(),user["id"]))
            sale_id = cur.lastrowid
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(body.tenant_id,"commercial.license_sale.created"))
            row = c.execute("SELECT * FROM commercial_license_sales WHERE id=?",(sale_id,)).fetchone()
        return dict(row)

    @router.get("/api/platform/license-sales")
    def list_license_sales(status: str = "all", user=Depends(user_from_header)):
        if os.getenv("LEADORA_ENFORCE_INSTANCE_CONFIG") == "1":
            raise HTTPException(404, "مدیریت فروش و صدور مجوز فقط در مرکز کنترل مالک انجام می‌شود.")
        if not is_owner(user):
            raise HTTPException(403, "فقط مالک پلتفرم مجاز است.")
        if status != "all" and status not in LICENSE_STATUSES:
            raise HTTPException(422, "وضعیت فروش مجوز نامعتبر است.")
        with db() as c:
            rows = c.execute("""SELECT s.*,t.name company_name FROM commercial_license_sales s
              JOIN tenants t ON t.id=s.tenant_id WHERE (?='all' OR s.status=?) ORDER BY s.id DESC LIMIT 500""",
              (status,status)).fetchall()
        return [dict(r) for r in rows]

    @router.patch("/api/platform/license-sales/{sale_id}")
    def update_license_sale(sale_id: int, body: LicenseSaleStatusIn, user=Depends(user_from_header)):
        if os.getenv("LEADORA_ENFORCE_INSTANCE_CONFIG") == "1":
            raise HTTPException(404, "مدیریت فروش و صدور مجوز فقط در مرکز کنترل مالک انجام می‌شود.")
        if not is_owner(user):
            raise HTTPException(403, "فقط مالک پلتفرم مجاز است.")
        if body.status not in LICENSE_STATUSES:
            raise HTTPException(422, "وضعیت نامعتبر است.")
        with db() as c:
            sale = c.execute("SELECT tenant_id,status FROM commercial_license_sales WHERE id=?",(sale_id,)).fetchone()
            if not sale:
                raise HTTPException(404, "فروش مجوز یافت نشد.")
            c.execute("UPDATE commercial_license_sales SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(body.status,sale_id))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(sale["tenant_id"],f"commercial.license_sale.status:{sale_id}:{body.status}"))
            row = c.execute("SELECT * FROM commercial_license_sales WHERE id=?",(sale_id,)).fetchone()
        return dict(row)

    @router.post("/api/support/tickets")
    def create_ticket(body: TicketIn, user=Depends(user_from_header)):
        if body.priority not in SUPPORT_PRIORITIES:
            raise HTTPException(422, "اولویت نامعتبر است.")
        with db() as c:
            cur = c.execute("""INSERT INTO support_tickets(tenant_id,subject,description,category,priority,created_by)
              VALUES(?,?,?,?,?,?)""",(user["tenant_id"],body.subject.strip(),body.description.strip(),body.category.strip(),body.priority,user["id"]))
            ticket_id=cur.lastrowid
            c.execute("INSERT INTO support_ticket_events(tenant_id,ticket_id,actor_id,event_type,note) VALUES(?,?,?,'created',?)",
                      (user["tenant_id"],ticket_id,user["id"],body.subject.strip()))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"support.ticket.created"))
            return dict(c.execute("SELECT * FROM support_tickets WHERE id=? AND tenant_id=?",(ticket_id,user["tenant_id"])).fetchone())

    @router.get("/api/support/tickets")
    def list_tickets(status: str = "all", user=Depends(user_from_header)):
        if status != "all" and status not in SUPPORT_STATUSES:
            raise HTTPException(422, "وضعیت درخواست نامعتبر است.")
        with db() as c:
            if is_owner(user):
                rows=c.execute("""SELECT s.*,t.name company_name FROM support_tickets s JOIN tenants t ON t.id=s.tenant_id
                  WHERE (?='all' OR s.status=?) ORDER BY CASE s.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,s.id DESC LIMIT 500""",(status,status)).fetchall()
            else:
                rows=c.execute("""SELECT * FROM support_tickets WHERE tenant_id=? AND (?='all' OR status=?)
                  ORDER BY id DESC LIMIT 200""",(user["tenant_id"],status,status)).fetchall()
        return [dict(r) for r in rows]

    @router.patch("/api/support/tickets/{ticket_id}")
    def update_ticket(ticket_id: int, body: TicketUpdateIn, user=Depends(user_from_header)):
        if body.status not in SUPPORT_STATUSES:
            raise HTTPException(422, "وضعیت نامعتبر است.")
        with db() as c:
            row=c.execute("SELECT tenant_id FROM support_tickets WHERE id=?",(ticket_id,)).fetchone() if is_owner(user) else c.execute("SELECT tenant_id FROM support_tickets WHERE id=? AND tenant_id=?",(ticket_id,user["tenant_id"])).fetchone()
            if not row:
                raise HTTPException(404, "درخواست پشتیبانی یافت نشد.")
            if not is_owner(user) and (body.assigned_to or body.status in {"resolved","closed"}):
                raise HTTPException(403, "تخصیص کار و بستن درخواست فقط برای پشتیبانی مجاز است.")
            c.execute("""UPDATE support_tickets SET status=?,assigned_to=CASE WHEN ? THEN ? ELSE assigned_to END,
              resolution=CASE WHEN ? THEN ? ELSE resolution END,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?""",
              (body.status,int(is_owner(user)),body.assigned_to.strip(),int(is_owner(user)),body.resolution.strip(),ticket_id,row["tenant_id"]))
            c.execute("INSERT INTO support_ticket_events(tenant_id,ticket_id,actor_id,event_type,note) VALUES(?,?,?,?,?)",
                      (row["tenant_id"],ticket_id,user["id"],"status_changed",body.note.strip()))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(row["tenant_id"],f"support.ticket.updated:{ticket_id}:{body.status}"))
            return dict(c.execute("SELECT * FROM support_tickets WHERE id=? AND tenant_id=?",(ticket_id,row["tenant_id"])).fetchone())

    @router.get("/api/support/tickets/{ticket_id}/events")
    def ticket_events(ticket_id: int, user=Depends(user_from_header)):
        with db() as c:
            ticket=c.execute("SELECT tenant_id FROM support_tickets WHERE id=?",(ticket_id,)).fetchone() if is_owner(user) else c.execute("SELECT tenant_id FROM support_tickets WHERE id=? AND tenant_id=?",(ticket_id,user["tenant_id"])).fetchone()
            if not ticket:
                raise HTTPException(404, "درخواست پشتیبانی یافت نشد.")
            rows=c.execute("SELECT * FROM support_ticket_events WHERE ticket_id=? AND tenant_id=? ORDER BY id",(ticket_id,ticket["tenant_id"])).fetchall()
        return [dict(r) for r in rows]

    @router.get("/api/automation/event-types")
    def automation_event_types(user=Depends(user_from_header)):
        return [{"event_type":k,"steps":[{"action":a,"title":t,"requires_approval":g} for a,t,g in v]} for k,v in EVENT_ACTIONS.items()]

    @router.post("/api/automation/events")
    def run_automation_event(body: WorkflowEventIn, user=Depends(user_from_header)):
        actions=EVENT_ACTIONS.get(body.event_type)
        if not actions:
            raise HTTPException(422, "برای این رویداد گردش خودکار تعریف نشده است.")
        if len(json.dumps(body.payload,ensure_ascii=False)) > 12000:
            raise HTTPException(413, "حجم اطلاعات رویداد بیش از حد مجاز است.")
        with db() as c:
            cur=c.execute("""INSERT INTO commercial_workflow_runs(tenant_id,event_type,source_ref,payload_json,created_by)
              VALUES(?,?,?,?,?)""",(user["tenant_id"],body.event_type,body.source_ref.strip(),json.dumps(body.payload,ensure_ascii=False),user["id"]))
            run_id=cur.lastrowid
            for action,title,gate in actions:
                c.execute("""INSERT INTO commercial_workflow_steps(tenant_id,run_id,action_key,title,requires_approval,status)
                  VALUES(?,?,?,?,?,?)""",(user["tenant_id"],run_id,action,title,int(gate),"pending_approval" if gate else "queued"))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],f"automation.event:{body.event_type}:{run_id}"))
            steps=c.execute("SELECT * FROM commercial_workflow_steps WHERE run_id=? AND tenant_id=? ORDER BY id",(run_id,user["tenant_id"])).fetchall()
        return {"run_id":run_id,"tenant_id":user["tenant_id"],"event_type":body.event_type,"status":"proposed",
                "message":"گام‌ها ثبت شدند؛ این موتور گام‌های قابل اجرا را صف‌بندی می‌کند و اجرای خارجی/مالی را بدون اتصال و تأیید انجام نمی‌دهد.",
                "steps":[dict(s) for s in steps]}

    @router.get("/api/automation/runs")
    def list_automation_runs(user=Depends(user_from_header)):
        with db() as c:
            runs=c.execute("SELECT * FROM commercial_workflow_runs WHERE tenant_id=? ORDER BY id DESC LIMIT 100",(user["tenant_id"],)).fetchall()
            out=[]
            for run in runs:
                item=dict(run)
                item["run_id"] = item.pop("id")
                item["steps"]=[dict(s) for s in c.execute("SELECT * FROM commercial_workflow_steps WHERE tenant_id=? AND run_id=? ORDER BY id",(user["tenant_id"],run["id"])).fetchall()]
                out.append(item)
        return out

    @router.post("/api/automation/steps/{step_id}/decision")
    def decide_automation_step(step_id: int, body: WorkflowDecisionIn, user=Depends(user_from_header)):
        if body.decision not in {"approve","reject"}:
            raise HTTPException(422, "تصمیم باید approve یا reject باشد.")
        with db() as c:
            step=c.execute("SELECT * FROM commercial_workflow_steps WHERE id=? AND tenant_id=?",(step_id,user["tenant_id"])).fetchone()
            if not step:
                raise HTTPException(404, "گام گردش کار یافت نشد.")
            if not step["requires_approval"]:
                raise HTTPException(409, "این گام نیازمند تأیید نیست.")
            if step["status"] != "pending_approval":
                raise HTTPException(409, "این گام قبلاً تعیین تکلیف شده است.")
            status="approved" if body.decision=="approve" else "rejected"
            c.execute("UPDATE commercial_workflow_steps SET status=?,decision_note=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=? AND status='pending_approval'",
                      (status,body.note.strip(),step_id,user["tenant_id"]))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],f"automation.step.{status}:{step_id}"))
            return dict(c.execute("SELECT * FROM commercial_workflow_steps WHERE id=? AND tenant_id=?",(step_id,user["tenant_id"])).fetchone())

    return router
