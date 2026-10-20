"""Financial participation module for LEADORA.

Amounts are stored as decimal strings and calculated with Decimal. The router
uses the host application's tenant-scoped database and authenticated user.
"""
import csv
import io
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

CENT = Decimal("0.01")
PERIOD_RE = re.compile(r"^\\d{4}-(0[1-9]|1[0-2])$")
METHODS = {"manual", "csv", "integration"}


def money(value, field_name="مبلغ"):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(422, f"{field_name} باید عدد معتبر باشد.")
    if not result.is_finite():
        raise HTTPException(422, f"{field_name} باید عدد متناهی باشد.")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def decimal_text(value):
    return format(money(value), "f")


def period_start(value):
    if not PERIOD_RE.fullmatch(value or ""):
        raise HTTPException(422, "دوره باید به شکل YYYY-MM باشد.")
    return date.fromisoformat(value + "-01")


def owner_emails():
    return {x.strip().casefold() for x in os.getenv("LEADORA_OWNER_EMAILS", "").split(",") if x.strip()}


def create_router(db_factory, user_dependency):
    router = APIRouter(prefix="/api/finance", tags=["financial-participation"])

    with db_factory() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS finance_settings(
          tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id),
          methods_json TEXT NOT NULL DEFAULT '["manual","csv"]',
          integration_provider TEXT NOT NULL DEFAULT '',
          integration_status TEXT NOT NULL DEFAULT 'not_configured',
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS finance_contracts(
          id INTEGER PRIMARY KEY,
          tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          trial_start TEXT NOT NULL,
          trial_end TEXT NOT NULL,
          contract_start TEXT NOT NULL,
          contract_end TEXT NOT NULL DEFAULT '',
          goal_name TEXT NOT NULL,
          baseline TEXT NOT NULL DEFAULT '0.00',
          target TEXT NOT NULL DEFAULT '0.00',
          goal_achieved INTEGER NOT NULL DEFAULT 0 CHECK(goal_achieved IN (0,1)),
          achieved_at TEXT NOT NULL DEFAULT '',
          share_percent TEXT NOT NULL,
          direct_costs_json TEXT NOT NULL DEFAULT '["direct_costs"]',
          status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','pending','active','suspended','terminated')),
          notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS finance_contracts_tenant_idx ON finance_contracts(tenant_id,id DESC);
        CREATE TABLE IF NOT EXISTS finance_entries(
          id INTEGER PRIMARY KEY,
          tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          period TEXT NOT NULL,
          document_ref TEXT NOT NULL,
          source TEXT NOT NULL CHECK(source IN ('manual','csv','integration')),
          sales TEXT NOT NULL,
          discounts TEXT NOT NULL,
          returns TEXT NOT NULL,
          cogs TEXT NOT NULL,
          direct_costs TEXT NOT NULL,
          currency TEXT NOT NULL,
          source_key TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tenant_id,period,document_ref)
        );
        CREATE INDEX IF NOT EXISTS finance_entries_period_idx ON finance_entries(tenant_id,period);
        CREATE TABLE IF NOT EXISTS finance_reports(
          id INTEGER PRIMARY KEY,
          tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          period TEXT NOT NULL,
          currency TEXT NOT NULL,
          gross_sales TEXT NOT NULL,
          discounts TEXT NOT NULL,
          returns TEXT NOT NULL,
          net_sales TEXT NOT NULL,
          cogs TEXT NOT NULL,
          direct_costs TEXT NOT NULL,
          eligible_profit TEXT NOT NULL,
          share_percent TEXT NOT NULL,
          owner_share TEXT NOT NULL,
          contract_id INTEGER,
          status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','closed','disputed','adjusted')),
          settlement_status TEXT NOT NULL DEFAULT 'unsettled' CHECK(settlement_status IN ('unsettled','partial','paid','disputed')),
          settled_amount TEXT NOT NULL DEFAULT '0.00',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          approved_at TEXT NOT NULL DEFAULT '',
          UNIQUE(tenant_id,period)
        );
        CREATE INDEX IF NOT EXISTS finance_reports_period_idx ON finance_reports(period,status);
        CREATE TABLE IF NOT EXISTS finance_audit(
          id INTEGER PRIMARY KEY,
          tenant_id INTEGER NOT NULL,
          actor_email TEXT NOT NULL,
          action TEXT NOT NULL,
          details_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

    def audit(c, user, action, details):
        c.execute(
            "INSERT INTO finance_audit(tenant_id,actor_email,action,details_json) VALUES(?,?,?,?)",
            (user["tenant_id"], user.get("email", ""), action, json.dumps(details, ensure_ascii=False, default=str)),
        )

    def is_owner(user):
        return bool(user.get("email", "").casefold() in owner_emails())

    def require_owner(user):
        if not is_owner(user):
            raise HTTPException(403, "این عملیات فقط برای مالک سامانه مجاز است.")

    def tenant_contract(c, tid):
        row = c.execute("SELECT * FROM finance_contracts WHERE tenant_id=? ORDER BY id DESC LIMIT 1", (tid,)).fetchone()
        return dict(row) if row else None

    class SettingsIn(BaseModel):
        methods: list[str] = Field(min_length=1, max_length=3)
        integration_provider: str = Field(default="", max_length=120)

        @field_validator("methods")
        @classmethod
        def valid_methods(cls, value):
            if len(set(value)) != len(value) or not set(value).issubset(METHODS):
                raise ValueError("روش‌ها باید از manual، csv و integration انتخاب شوند و تکراری نباشند.")
            return value

    class ContractIn(BaseModel):
        tenant_id: int = Field(ge=1)
        trial_start: date
        trial_end: date
        contract_start: date
        contract_end: date | None = None
        goal_name: str = Field(min_length=3, max_length=300)
        baseline: Decimal = Field(ge=0)
        target: Decimal = Field(ge=0)
        share_percent: Decimal = Field(ge=0, le=100)
        direct_costs: list[str] = Field(default_factory=lambda: ["direct_costs"], max_length=10)
        notes: str = Field(default="", max_length=3000)

        @field_validator("direct_costs")
        @classmethod
        def valid_costs(cls, value):
            allowed = {"direct_costs"}
            if len(set(value)) != len(value) or not set(value).issubset(allowed):
                raise ValueError("مبنای هزینه فقط می‌تواند هزینه‌های مستقیم توافق‌شده باشد.")
            return value

    class EntryIn(BaseModel):
        period: str
        document_ref: str = Field(min_length=1, max_length=160)
        sales: Decimal = Field(ge=0)
        discounts: Decimal = Field(default=Decimal("0"), ge=0)
        returns: Decimal = Field(default=Decimal("0"), ge=0)
        cogs: Decimal = Field(ge=0)
        direct_costs: Decimal = Field(default=Decimal("0"), ge=0)
        currency: str = Field(default="IRT", pattern="^(IRT|IRR|USD|EUR)$")
        source_key: str = Field(default="", max_length=200)

        @field_validator("period")
        @classmethod
        def valid_period(cls, value):
            period_start(value)
            return value

        @field_validator("document_ref")
        @classmethod
        def clean_ref(cls, value):
            value = value.strip()
            if not value:
                raise ValueError("شناسه سند الزامی است.")
            return value

    class CsvIn(BaseModel):
        content: str = Field(min_length=1, max_length=2_000_000)

    class ObjectionIn(BaseModel):
        reason: str = Field(min_length=5, max_length=2000)

    class GoalDecisionIn(BaseModel):
        achieved: bool
        evidence: str = Field(min_length=5, max_length=2000)

    class SettlementIn(BaseModel):
        amount: Decimal = Field(gt=0)
        note: str = Field(default="", max_length=1000)

    @router.get("/settings")
    def get_settings(user=Depends(user_dependency)):
        with db_factory() as c:
            row = c.execute("SELECT methods_json,integration_provider,integration_status,updated_at FROM finance_settings WHERE tenant_id=?", (user["tenant_id"],)).fetchone()
            if not row:
                return {"methods": ["manual", "csv"], "integration_provider": "", "integration_status": "not_configured", "updated_at": None}
            return {"methods": json.loads(row["methods_json"]), "integration_provider": row["integration_provider"], "integration_status": row["integration_status"], "updated_at": row["updated_at"]}

    @router.put("/settings")
    def put_settings(body: SettingsIn, user=Depends(user_dependency)):
        provider = body.integration_provider.strip()
        if "integration" in body.methods and not provider:
            raise HTTPException(422, "برای روش اتصال خودکار، نام سامانه منبع را مشخص کنید.")
        with db_factory() as c:
            status = "not_configured" if "integration" in body.methods else "disabled"
            c.execute("""INSERT INTO finance_settings(tenant_id,methods_json,integration_provider,integration_status,updated_at)
              VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(tenant_id) DO UPDATE SET
              methods_json=excluded.methods_json,integration_provider=excluded.integration_provider,
              integration_status=excluded.integration_status,updated_at=CURRENT_TIMESTAMP""",
              (user["tenant_id"], json.dumps(body.methods), provider, status))
            audit(c, user, "finance.settings.updated", {"methods": body.methods, "integration_provider": provider, "integration_status": status})
        return {"ok": True, "methods": body.methods, "integration_status": status, "message": "تنظیمات ذخیره شد؛ اتصال خودکار تا زمان پیکربندی API مجاز فعال نیست."}

    @router.get("/contracts")
    def get_contracts(user=Depends(user_dependency)):
        with db_factory() as c:
            if is_owner(user):
                rows = c.execute("""SELECT fc.*,t.name AS company_name FROM finance_contracts fc
                  JOIN tenants t ON t.id=fc.tenant_id ORDER BY fc.id DESC LIMIT 500""").fetchall()
            else:
                rows = c.execute("SELECT * FROM finance_contracts WHERE tenant_id=? ORDER BY id DESC LIMIT 50", (user["tenant_id"],)).fetchall()
        return [dict(x) for x in rows]

    @router.post("/contracts")
    def create_contract(body: ContractIn, user=Depends(user_dependency)):
        require_owner(user)
        if body.trial_end < body.trial_start or body.contract_start < body.trial_start:
            raise HTTPException(422, "بازه دوره رایگان یا تاریخ شروع قرارداد معتبر نیست.")
        if body.contract_end and body.contract_end < body.contract_start:
            raise HTTPException(422, "تاریخ پایان قرارداد باید بعد از شروع آن باشد.")
        if body.target < body.baseline:
            raise HTTPException(422, "هدف قرارداد نباید کمتر از خط مبنا باشد.")
        with db_factory() as c:
            if not c.execute("SELECT id FROM tenants WHERE id=?", (body.tenant_id,)).fetchone():
                raise HTTPException(404, "شرکت انتخاب‌شده پیدا نشد.")
            cur = c.execute("""INSERT INTO finance_contracts
              (tenant_id,trial_start,trial_end,contract_start,contract_end,goal_name,baseline,target,share_percent,direct_costs_json,notes,status)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,'pending')""",
              (body.tenant_id, body.trial_start.isoformat(), body.trial_end.isoformat(), body.contract_start.isoformat(),
               body.contract_end.isoformat() if body.contract_end else "", body.goal_name.strip(), decimal_text(body.baseline),
               decimal_text(body.target), decimal_text(body.share_percent), json.dumps(body.direct_costs), body.notes.strip()))
            audit(c, user, "finance.contract.created", {"contract_id": cur.lastrowid, "tenant_id": body.tenant_id})
            return dict(c.execute("SELECT * FROM finance_contracts WHERE id=?", (cur.lastrowid,)).fetchone())

    @router.post("/contracts/{contract_id}/goal")
    def decide_goal(contract_id: int, body: GoalDecisionIn, user=Depends(user_dependency)):
        require_owner(user)
        with db_factory() as c:
            row = c.execute("SELECT * FROM finance_contracts WHERE id=?", (contract_id,)).fetchone()
            if not row:
                raise HTTPException(404, "قرارداد پیدا نشد.")
            c.execute("UPDATE finance_contracts SET goal_achieved=?,achieved_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                      (int(body.achieved), datetime.utcnow().isoformat(timespec="seconds") if body.achieved else "", contract_id))
            audit(c, user, "finance.contract.goal_decided", {"contract_id": contract_id, "achieved": body.achieved, "evidence": body.evidence})
        return {"ok": True, "goal_achieved": body.achieved, "message": "نتیجه هدف با ثبت مستندات ذخیره شد."}

    @router.post("/contracts/{contract_id}/activate")
    def activate_contract(contract_id: int, user=Depends(user_dependency)):
        require_owner(user)
        with db_factory() as c:
            row = c.execute("SELECT * FROM finance_contracts WHERE id=?", (contract_id,)).fetchone()
            if not row:
                raise HTTPException(404, "قرارداد پیدا نشد.")
            c.execute("UPDATE finance_contracts SET status='active',updated_at=CURRENT_TIMESTAMP WHERE id=?", (contract_id,))
            audit(c, user, "finance.contract.activated", {"contract_id": contract_id, "tenant_id": row["tenant_id"]})
        return {"ok": True, "status": "active"}

    def insert_entry(c, user, body, source):
        tid = user["tenant_id"]
        settings = c.execute("SELECT methods_json FROM finance_settings WHERE tenant_id=?", (tid,)).fetchone()
        enabled = json.loads(settings["methods_json"]) if settings else ["manual", "csv"]
        if source not in enabled:
            raise HTTPException(403, "این روش ورود اطلاعات برای شرکت فعال نیست.")
        values = [money(getattr(body, key), key) for key in ("sales", "discounts", "returns", "cogs", "direct_costs")]
        if values[1] > values[0]:
            raise HTTPException(422, "تخفیف نمی‌تواند از فروش ثبت‌شده بیشتر باشد.")
        if len({body.currency}) != 1:
            raise HTTPException(422, "واحد پول نامعتبر است.")
        try:
            c.execute("""INSERT INTO finance_entries(tenant_id,period,document_ref,source,sales,discounts,returns,cogs,direct_costs,currency,source_key)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (tid, body.period, body.document_ref.strip(), source, *[format(v, "f") for v in values], body.currency, body.source_key.strip()))
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(409, "این شناسه سند قبلاً برای همین شرکت و دوره ثبت شده است.")
            raise
        audit(c, user, "finance.entry.created", {"period": body.period, "document_ref": body.document_ref, "source": source})
        return {"ok": True, "message": "سند مالی ثبت شد."}

    @router.post("/entries")
    def create_entry(body: EntryIn, user=Depends(user_dependency)):
        period_start(body.period)
        with db_factory() as c:
            return insert_entry(c, user, body, "manual")

    @router.post("/import/csv")
    def import_csv(body: CsvIn, user=Depends(user_dependency)):
        reader = csv.DictReader(io.StringIO(body.content))
        required = {"period", "document_ref", "sales", "discounts", "returns", "cogs", "direct_costs", "currency"}
        if not reader.fieldnames or not required.issubset({x.strip() for x in reader.fieldnames}):
            raise HTTPException(422, "ستون‌های لازم: period,document_ref,sales,discounts,returns,cogs,direct_costs,currency")
        imported, rejected = 0, []
        with db_factory() as c:
            settings = c.execute("SELECT methods_json FROM finance_settings WHERE tenant_id=?", (user["tenant_id"],)).fetchone()
            enabled = json.loads(settings["methods_json"]) if settings else ["manual", "csv"]
            if "csv" not in enabled:
                raise HTTPException(403, "ورود CSV برای این شرکت فعال نیست.")
            for line, raw in enumerate(reader, start=2):
                try:
                    data = {str(k).strip(): (v or "").strip() for k, v in raw.items() if k is not None}
                    entry = EntryIn(**{
                        "period": data.get("period", ""),
                        "document_ref": data.get("document_ref", ""),
                        "sales": data.get("sales", ""),
                        "discounts": data.get("discounts", "0") or "0",
                        "returns": data.get("returns", "0") or "0",
                        "cogs": data.get("cogs", ""),
                        "direct_costs": data.get("direct_costs", "0") or "0",
                        "currency": data.get("currency", "IRT") or "IRT",
                        "source_key": data.get("source_key", ""),
                    })
                    insert_entry(c, user, entry, "csv")
                    imported += 1
                except HTTPException as exc:
                    rejected.append({"line": line, "reason": str(exc.detail)})
                except Exception:
                    rejected.append({"line": line, "reason": "قالب یا مقدار ردیف معتبر نیست."})
            audit(c, user, "finance.csv.imported", {"imported": imported, "rejected": len(rejected)})
        return {"received": imported + len(rejected), "imported": imported, "rejected": rejected}

    @router.get("/entries")
    def list_entries(period: str = "", user=Depends(user_dependency)):
        if period:
            period_start(period)
        with db_factory() as c:
            sql = "SELECT id,period,document_ref,source,sales,discounts,returns,cogs,direct_costs,currency,source_key,created_at FROM finance_entries WHERE tenant_id=?"
            args = [user["tenant_id"]]
            if period:
                sql += " AND period=?"; args.append(period)
            rows = c.execute(sql + " ORDER BY period DESC,id DESC LIMIT 1000", args).fetchall()
        return [dict(x) for x in rows]

    @router.post("/reports/calculate")
    def calculate_report(period: str, user=Depends(user_dependency)):
        period_start(period)
        with db_factory() as c:
            rows = c.execute("SELECT * FROM finance_entries WHERE tenant_id=? AND period=? ORDER BY id", (user["tenant_id"], period)).fetchall()
            if not rows:
                raise HTTPException(422, "برای این دوره هیچ سند مالی ثبت نشده است.")
            currencies = {r["currency"] for r in rows}
            if len(currencies) != 1:
                raise HTTPException(422, "واحد پول اسناد یکسان نیست؛ گزارش قابل محاسبه نیست.")
            totals = {k: sum((money(r[k]) for r in rows), Decimal("0")) for k in ("sales", "discounts", "returns", "cogs", "direct_costs")}
            net_sales = totals["sales"] - totals["discounts"] - totals["returns"]
            eligible = net_sales - totals["cogs"] - totals["direct_costs"]
            contract = tenant_contract(c, user["tenant_id"])
            share_percent = Decimal("0")
            contract_id = None
            owner_share = Decimal("0")
            month_start = period_start(period)
            month_end = date(month_start.year + (month_start.month == 12), 1 if month_start.month == 12 else month_start.month + 1, 1)
            if contract and contract["status"] == "active" and contract["goal_achieved"]:
                in_contract = month_start.isoformat() >= contract["contract_start"] and (not contract["contract_end"] or month_start.isoformat() <= contract["contract_end"])
                after_trial = month_start.isoformat() > contract["trial_end"]
                if in_contract and after_trial:
                    share_percent = money(contract["share_percent"])
                    owner_share = max(Decimal("0"), eligible) * share_percent / Decimal("100")
                    owner_share = owner_share.quantize(CENT, rounding=ROUND_HALF_UP)
                    contract_id = contract["id"]
            values = [format(x.quantize(CENT, rounding=ROUND_HALF_UP), "f") for x in (totals["sales"], totals["discounts"], totals["returns"], net_sales, totals["cogs"], totals["direct_costs"], eligible, share_percent, owner_share)]
            try:
                c.execute("""INSERT INTO finance_reports(tenant_id,period,currency,gross_sales,discounts,returns,net_sales,cogs,direct_costs,eligible_profit,share_percent,owner_share,contract_id,status)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""", (user["tenant_id"], period, next(iter(currencies)), *values[:7], values[7], values[8], contract_id))
            except Exception as exc:
                if "UNIQUE constraint failed" not in str(exc):
                    raise
                existing = c.execute("SELECT id,status FROM finance_reports WHERE tenant_id=? AND period=?", (user["tenant_id"], period)).fetchone()
                if existing["status"] in ("approved", "closed", "adjusted"):
                    raise HTTPException(409, "گزارش تأییدشده قابل بازنویسی نیست؛ اصلاحیه جداگانه لازم است.")
                c.execute("""UPDATE finance_reports SET currency=?,gross_sales=?,discounts=?,returns=?,net_sales=?,cogs=?,direct_costs=?,eligible_profit=?,share_percent=?,owner_share=?,contract_id=?,status='pending'
                  WHERE id=?""", (next(iter(currencies)), *values, contract_id, existing["id"])
            report = c.execute("SELECT * FROM finance_reports WHERE tenant_id=? AND period=?", (user["tenant_id"], period)).fetchone()
            audit(c, user, "finance.report.calculated", {"period": period, "report_id": report["id"], "eligible_profit": report["eligible_profit"]})
        return dict(report)

    @router.get("/reports")
    def list_reports(period: str = "", user=Depends(user_dependency)):
        if period:
            period_start(period)
        with db_factory() as c:
            if is_owner(user):
                sql = """SELECT fr.*,t.name AS company_name FROM finance_reports fr JOIN tenants t ON t.id=fr.tenant_id"""
                args = []
            else:
                sql = "SELECT * FROM finance_reports WHERE tenant_id=?"
                args = [user["tenant_id"]]
            if period:
                sql += " AND period=?" if is_owner(user) else " AND period=?"
                args.append(period)
            rows = c.execute(sql + " ORDER BY period DESC,id DESC LIMIT 1000", args).fetchall()
        return [dict(x) for x in rows]

    @router.post("/reports/{report_id}/approve")
    def approve_report(report_id: int, user=Depends(user_dependency)):
        require_owner(user)
        with db_factory() as c:
            row = c.execute("SELECT * FROM finance_reports WHERE id=?", (report_id,)).fetchone()
            if not row:
                raise HTTPException(404, "گزارش پیدا نشد.")
            if row["status"] not in ("pending", "disputed"):
                raise HTTPException(409, "فقط گزارش در انتظار تأیید یا مورد اختلاف قابل تأیید است.")
            c.execute("UPDATE finance_reports SET status='approved',approved_at=CURRENT_TIMESTAMP WHERE id=?", (report_id,))
            audit(c, user, "finance.report.approved", {"report_id": report_id, "tenant_id": row["tenant_id"]})
        return {"ok": True, "status": "approved"}

    @router.post("/reports/{report_id}/objection")
    def object_report(report_id: int, body: ObjectionIn, user=Depends(user_dependency)):
        with db_factory() as c:
            row = c.execute("SELECT * FROM finance_reports WHERE id=? AND tenant_id=?", (report_id, user["tenant_id"])).fetchone()
            if not row:
                raise HTTPException(404, "گزارش پیدا نشد.")
            if row["status"] not in ("pending", "approved"):
                raise HTTPException(409, "این گزارش در وضعیت فعلی قابل اعتراض نیست.")
            c.execute("UPDATE finance_reports SET status='disputed' WHERE id=?", (report_id,))
            audit(c, user, "finance.report.disputed", {"report_id": report_id, "reason": body.reason})
        return {"ok": True, "status": "disputed", "message": "اعتراض ثبت شد؛ گزارش برای بررسی مالک علامت‌گذاری شد."}

    @router.post("/reports/{report_id}/settlement")
    def settle_report(report_id: int, body: SettlementIn, user=Depends(user_dependency)):
        require_owner(user)
        amount = money(body.amount)
        with db_factory() as c:
            row = c.execute("SELECT * FROM finance_reports WHERE id=?", (report_id,)).fetchone()
            if not row:
                raise HTTPException(404, "گزارش پیدا نشد.")
            if row["status"] not in ("approved", "closed"):
                raise HTTPException(409, "تسویه فقط پس از تأیید گزارش مجاز است.")
            total = money(row["settled_amount"]) + amount
            due = money(row["owner_share"])
            if total > due:
                raise HTTPException(422, "مبلغ پرداختی از سهم مصوب بیشتر است.")
            status = "paid" if total == due else "partial"
            c.execute("UPDATE finance_reports SET settled_amount=?,settlement_status=? WHERE id=?", (format(total, "f"), status, report_id))
            if status == "paid":
                c.execute("UPDATE finance_reports SET status='closed' WHERE id=?", (report_id,))
            audit(c, user, "finance.settlement.recorded", {"report_id": report_id, "amount": str(amount), "note": body.note})
        return {"ok": True, "settled_amount": format(total, "f"), "settlement_status": status}

    @router.get("/owner/overview")
    def owner_overview(user=Depends(user_dependency)):
        require_owner(user)
        with db_factory() as c:
            counts = c.execute("""SELECT
              (SELECT COUNT(*) FROM finance_contracts) AS contracts,
              (SELECT COUNT(*) FROM finance_contracts WHERE status='pending') AS pending_contracts,
              (SELECT COUNT(*) FROM finance_reports WHERE status IN ('pending','disputed')) AS pending_reports,
              (SELECT COUNT(*) FROM finance_reports WHERE settlement_status IN ('unsettled','partial')) AS unsettled_reports,
              (SELECT COALESCE(SUM(CAST(owner_share AS REAL)),0) FROM finance_reports WHERE status IN ('approved','closed')) AS approved_share,
              (SELECT COALESCE(SUM(CAST(owner_share AS REAL)-CAST(settled_amount AS REAL)),0) FROM finance_reports WHERE status IN ('approved','closed')) AS unpaid_share""").fetchone()
            by_month = c.execute("""SELECT period,COUNT(*) AS reports,
              SUM(CAST(net_sales AS REAL)) AS net_sales,
              SUM(CAST(eligible_profit AS REAL)) AS eligible_profit,
              SUM(CAST(owner_share AS REAL)) AS owner_share
              FROM finance_reports GROUP BY period ORDER BY period DESC LIMIT 12""").fetchall()
            companies = c.execute("""SELECT t.id AS tenant_id,t.name AS company_name,fc.status AS contract_status,
              fc.share_percent,fc.goal_name,fc.goal_achieved,fs.integration_status,fs.updated_at AS source_updated_at
              FROM tenants t LEFT JOIN finance_contracts fc ON fc.id=(SELECT MAX(id) FROM finance_contracts WHERE tenant_id=t.id)
              LEFT JOIN finance_settings fs ON fs.tenant_id=t.id ORDER BY t.name LIMIT 500""").fetchall()
        return {"counts": dict(counts), "by_month": [dict(x) for x in by_month], "companies": [dict(x) for x in companies]}

    @router.get("/owner/audit")
    def owner_audit(limit: int = 100, user=Depends(user_dependency)):
        require_owner(user)
        with db_factory() as c:
            rows = c.execute("SELECT * FROM finance_audit ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        return [dict(x) for x in rows]

    return router
