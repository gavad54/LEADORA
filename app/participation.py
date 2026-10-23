"""Financial participation module for LEADORA.

Amounts are stored as decimal strings and calculated with Decimal. The router
uses the host application's tenant-scoped database and authenticated user.
"""
import csv
import hashlib
import secrets
import io
import json
import os
import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fastapi import APIRouter, Depends, Header, HTTPException
from hmac import compare_digest as secrets_compare
from pydantic import BaseModel, Field, field_validator

CENT = Decimal("0.01")
PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
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


def owner_user_ids():
    return {x.strip() for x in os.getenv("LEADORA_OWNER_USER_IDS", "").split(",") if x.strip()}


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
        CREATE TABLE IF NOT EXISTS finance_platform_owner(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          user_id TEXT NOT NULL UNIQUE,
          email TEXT NOT NULL DEFAULT '',
          claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS finance_integration_keys(
          tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id),
          key_hash TEXT NOT NULL,
          key_prefix TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          rotated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        CREATE TABLE IF NOT EXISTS finance_adjustments(
          id INTEGER PRIMARY KEY,
          tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          target_report_id INTEGER NOT NULL REFERENCES finance_reports(id),
          adjustment_period TEXT NOT NULL,
          currency TEXT NOT NULL,
          sales_adjustment TEXT NOT NULL DEFAULT '0.00',
          discounts_adjustment TEXT NOT NULL DEFAULT '0.00',
          returns_adjustment TEXT NOT NULL DEFAULT '0.00',
          cogs_adjustment TEXT NOT NULL DEFAULT '0.00',
          direct_costs_adjustment TEXT NOT NULL DEFAULT '0.00',
          reason TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
          reviewed_by TEXT NOT NULL DEFAULT '',
          reviewed_at TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS finance_adjustments_period_idx ON finance_adjustments(tenant_id,adjustment_period,status);
        """)

    def audit(c, user, action, details, tenant_id=None):
        target_tenant_id = user["tenant_id"] if tenant_id is None else tenant_id
        c.execute(
            "INSERT INTO finance_audit(tenant_id,actor_email,action,details_json) VALUES(?,?,?,?)",
            (target_tenant_id, user.get("email", ""), action, json.dumps(details, ensure_ascii=False, default=str)),
        )

    def is_owner(user):
        user_id = str(user.get("id", ""))
        if user_id and user_id in owner_user_ids():
            return True
        if not user_id:
            return False
        with db_factory() as owner_db:
            row = owner_db.execute("SELECT user_id FROM finance_platform_owner WHERE singleton=1").fetchone()
        return bool(row and str(row["user_id"]) == user_id)

    def require_owner(user):
        if not is_owner(user):
            raise HTTPException(403, "این عملیات فقط برای مالک سامانه مجاز است.")

    class SettingsIn(BaseModel):
        methods: list[str] = Field(min_length=1, max_length=3)
        integration_provider: str = Field(default="", max_length=120)

        @field_validator("methods")
        @classmethod
        def valid_methods(cls, value):
            if len(set(value)) != len(value) or not set(value).issubset(METHODS):
                raise ValueError("روش‌ها باید از manual، csv و integration انتخاب شوند و تکراری نباشند.")
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

    class IntegrationBatchIn(BaseModel):
        entries: list[EntryIn] = Field(min_length=1, max_length=100)

    class ObjectionIn(BaseModel):
        reason: str = Field(min_length=5, max_length=2000)

    class SettlementIn(BaseModel):
        amount: Decimal = Field(gt=0)
        note: str = Field(default="", max_length=1000)

    class AdjustmentIn(BaseModel):
        adjustment_period: str
        sales_adjustment: Decimal = Decimal("0")
        discounts_adjustment: Decimal = Decimal("0")
        returns_adjustment: Decimal = Decimal("0")
        cogs_adjustment: Decimal = Decimal("0")
        direct_costs_adjustment: Decimal = Decimal("0")
        currency: str = Field(pattern="^(IRT|IRR|USD|EUR)$")
        reason: str = Field(min_length=5, max_length=2000)

        @field_validator("adjustment_period")
        @classmethod
        def valid_adjustment_period(cls, value):
            period_start(value)
            return value

    @router.get("/identity")
    def identity(user=Depends(user_dependency)):
        return {"user_id": user["id"], "tenant_id": user["tenant_id"], "email": user.get("email", ""), "is_platform_owner": is_owner(user)}

    class OwnerClaimIn(BaseModel):
        token: str = Field(min_length=32, max_length=256)

    @router.post("/owner/claim")
    def claim_owner(body: OwnerClaimIn, user=Depends(user_dependency)):
        expected = os.getenv("LEADORA_OWNER_BOOTSTRAP_TOKEN", "")
        if not expected:
            raise HTTPException(503, "فرایند ثبت مالک از سمت سرور فعال نشده است.")
        if owner_user_ids():
            raise HTTPException(409, "مالک سامانه از طریق تنظیمات امن سرور تعیین شده است؛ ثبت مالک جدید مجاز نیست.")
        if not secrets_compare(body.token, expected):
            raise HTTPException(403, "رمز یک‌بارمصرف مالک معتبر نیست.")
        expected_email = os.getenv("LEADORA_OWNER_BOOTSTRAP_EMAIL", "").strip().casefold()
        account_email = str(user.get("email", "")).strip().casefold()
        if expected_email and account_email != expected_email:
            raise HTTPException(403, "این حساب با ایمیل مجاز مالک مطابقت ندارد.")
        user_id = str(user.get("id", ""))
        if not user_id:
            raise HTTPException(400, "شناسه حساب معتبر نیست.")
        with db_factory() as c:
            existing = c.execute("SELECT user_id FROM finance_platform_owner WHERE singleton=1").fetchone()
            if existing:
                if str(existing["user_id"]) == user_id:
                    return {"ok": True, "is_platform_owner": True, "message": "این حساب قبلاً به‌عنوان مالک ثبت شده است."}
                raise HTTPException(409, "مالک سامانه قبلاً ثبت شده است؛ ثبت مجدد مسدود است.")
            try:
                c.execute("INSERT INTO finance_platform_owner(singleton,user_id,email) VALUES(1,?,?)", (user_id, user.get("email", "")))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "ثبت مالک هم‌زمان انجام شده است؛ صفحه را تازه‌سازی کنید.")
            audit(c, user, "finance.owner.claimed", {"user_id": user_id})
        return {"ok": True, "is_platform_owner": True, "message": "مالک سامانه با موفقیت ثبت شد."}

    @router.post("/owner/recover")
    def recover_owner(body: OwnerClaimIn, user=Depends(user_dependency)):
        # Recovery is deliberately separate from initial claim and requires two
        # independent server-side controls: a dedicated token and exact email.
        expected = os.getenv("LEADORA_OWNER_RECOVERY_TOKEN", "").strip()
        expected_email = os.getenv("LEADORA_OWNER_RECOVERY_EMAIL", "").strip().casefold()
        bootstrap_token = os.getenv("LEADORA_OWNER_BOOTSTRAP_TOKEN", "").strip()
        if len(expected) < 32 or not expected_email or secrets_compare(expected, bootstrap_token):
            raise HTTPException(503, "بازیابی امن مالک در تنظیمات سرور فعال نشده است.")
        if owner_user_ids():
            raise HTTPException(409, "مالک از طریق تنظیمات امن شناسه کاربر تعیین شده است؛ بازیابی از پنل مجاز نیست.")
        if not secrets_compare(body.token, expected):
            raise HTTPException(403, "کلید بازیابی مالک معتبر نیست.")
        account_email = str(user.get("email", "")).strip().casefold()
        if account_email != expected_email:
            raise HTTPException(403, "ایمیل حساب با ایمیل مجاز بازیابی مالک مطابقت ندارد.")
        user_id = str(user.get("id", ""))
        if not user_id:
            raise HTTPException(400, "شناسه حساب معتبر نیست.")
        with db_factory() as c:
            existing = c.execute("SELECT user_id,email FROM finance_platform_owner WHERE singleton=1").fetchone()
            if not existing:
                raise HTTPException(409, "مالک ثبت‌شده‌ای برای بازیابی وجود ندارد؛ از فرایند ثبت اولیه مالک استفاده کنید.")
            previous_user_id = str(existing["user_id"])
            if previous_user_id == user_id:
                return {"ok": True, "is_platform_owner": True, "message": "این حساب از قبل مالک اصلی سامانه است."}
            c.execute(
                "UPDATE finance_platform_owner SET user_id=?,email=?,claimed_at=CURRENT_TIMESTAMP WHERE singleton=1",
                (user_id, account_email),
            )
            audit(c, user, "finance.owner.recovered", {
                "previous_user_id": previous_user_id,
                "previous_email": str(existing["email"]),
                "new_user_id": user_id,
                "new_email": account_email,
                "method": "server_configured_recovery",
            })
        return {"ok": True, "is_platform_owner": True, "message": "دسترسی مالک اصلی با تأیید امن بازیابی شد."}

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
            key_exists = c.execute("SELECT 1 FROM finance_integration_keys WHERE tenant_id=?", (user["tenant_id"],)).fetchone() is not None
            status = ("configured" if key_exists else "not_configured") if "integration" in body.methods else "disabled"
            c.execute("""INSERT INTO finance_settings(tenant_id,methods_json,integration_provider,integration_status,updated_at)
              VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(tenant_id) DO UPDATE SET
              methods_json=excluded.methods_json,integration_provider=excluded.integration_provider,
              integration_status=excluded.integration_status,updated_at=CURRENT_TIMESTAMP""",
              (user["tenant_id"], json.dumps(body.methods), provider, status))
            audit(c, user, "finance.settings.updated", {"methods": body.methods, "integration_provider": provider, "integration_status": status})
        return {"ok": True, "methods": body.methods, "integration_status": status, "message": "تنظیمات ذخیره شد؛ اتصال خودکار تا زمان پیکربندی API مجاز فعال نیست."}

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

    @router.post("/integration/key")
    def create_integration_key(user=Depends(user_dependency)):
        raw_key = "ldint_" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        with db_factory() as c:
            settings = c.execute("SELECT methods_json,integration_provider FROM finance_settings WHERE tenant_id=?", (user["tenant_id"],)).fetchone()
            enabled = json.loads(settings["methods_json"]) if settings else ["manual", "csv"]
            if "integration" not in enabled:
                raise HTTPException(403, "ابتدا روش اتصال سامانه موجود را در تنظیمات این شرکت فعال کنید.")
            if not settings or not settings["integration_provider"].strip():
                raise HTTPException(422, "نام سامانه منبع را در تنظیمات وارد کنید.")
            c.execute("""INSERT INTO finance_integration_keys(tenant_id,key_hash,key_prefix)
              VALUES(?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET key_hash=excluded.key_hash,key_prefix=excluded.key_prefix,rotated_at=CURRENT_TIMESTAMP""",
              (user["tenant_id"], key_hash, raw_key[:12]))
            c.execute("UPDATE finance_settings SET integration_status='configured',updated_at=CURRENT_TIMESTAMP WHERE tenant_id=?", (user["tenant_id"],))
            audit(c, user, "finance.integration_key.rotated", {"key_prefix": raw_key[:12], "provider": settings["integration_provider"]})
        return {"ok": True, "integration_key": raw_key, "key_prefix": raw_key[:12], "message": "کلید فقط همین یک بار نمایش داده می‌شود. آن را در سامانه منبع به‌صورت محرمانه ذخیره کنید."}

    @router.get("/integration/status")
    def integration_status(user=Depends(user_dependency)):
        with db_factory() as c:
            settings = c.execute("SELECT integration_provider,integration_status,methods_json FROM finance_settings WHERE tenant_id=?", (user["tenant_id"],)).fetchone()
            key = c.execute("SELECT key_prefix,created_at,rotated_at FROM finance_integration_keys WHERE tenant_id=?", (user["tenant_id"],)).fetchone()
        return {"provider": settings["integration_provider"] if settings else "", "status": settings["integration_status"] if settings else "not_configured", "enabled": bool(settings and "integration" in json.loads(settings["methods_json"])), "key_prefix": key["key_prefix"] if key else "", "created_at": key["created_at"] if key else None, "rotated_at": key["rotated_at"] if key else None}

    @router.post("/integration/ingest")
    def ingest_integration_batch(body: IntegrationBatchIn, x_leadora_integration_key: str = Header(default="", alias="X-LEADORA-Integration-Key")):
        if not x_leadora_integration_key:
            raise HTTPException(401, "کلید اتصال الزامی است.")
        supplied_hash = hashlib.sha256(x_leadora_integration_key.encode("utf-8")).hexdigest()
        with db_factory() as c:
            key_row = c.execute("SELECT tenant_id,key_hash FROM finance_integration_keys WHERE key_prefix=?", (x_leadora_integration_key[:12],)).fetchone()
            if not key_row or not secrets_compare(supplied_hash, key_row["key_hash"]):
                raise HTTPException(401, "کلید اتصال نامعتبر یا لغوشده است.")
            tid = key_row["tenant_id"]
            settings = c.execute("SELECT methods_json FROM finance_settings WHERE tenant_id=?", (tid,)).fetchone()
            if not settings or "integration" not in json.loads(settings["methods_json"]):
                raise HTTPException(403, "اتصال خودکار برای این شرکت فعال نیست.")
            integration_user = {"tenant_id": tid, "email": "integration:webhook", "id": "integration"}
            imported, rejected = 0, []
            for index, entry in enumerate(body.entries, start=1):
                try:
                    insert_entry(c, integration_user, entry, "integration")
                    imported += 1
                except HTTPException as exc:
                    rejected.append({"index": index, "document_ref": entry.document_ref, "status": exc.status_code, "reason": str(exc.detail)})
            audit(c, integration_user, "finance.integration.batch_received", {"imported": imported, "rejected": len(rejected)})
        return {"ok": True, "imported": imported, "rejected": rejected, "message": "همگام‌سازی دسته‌ای انجام شد؛ اسناد ردشده نیازمند بررسی هستند."}

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
            adjustments = c.execute("SELECT * FROM finance_adjustments WHERE tenant_id=? AND adjustment_period=? AND status='approved' ORDER BY id", (user["tenant_id"], period)).fetchall()
            if not rows and not adjustments:
                raise HTTPException(422, "برای این دوره هیچ سند مالی یا اصلاحیه تأییدشده ثبت نشده است.")
            currencies = {r["currency"] for r in rows} | {a["currency"] for a in adjustments}
            if len(currencies) != 1:
                raise HTTPException(422, "واحد پول اسناد و اصلاحیه‌ها یکسان نیست؛ گزارش قابل محاسبه نیست.")
            totals = {k: sum((money(r[k]) for r in rows), Decimal("0")) for k in ("sales", "discounts", "returns", "cogs", "direct_costs")}
            for adjustment in adjustments:
                for key in ("sales", "discounts", "returns", "cogs", "direct_costs"):
                    totals[key] += money(adjustment[key + "_adjustment"])
            net_sales = totals["sales"] - totals["discounts"] - totals["returns"]
            eligible = net_sales - totals["cogs"] - totals["direct_costs"]
            # Legacy participation-contract records are preserved for historical data,
            # but the removed contract feature no longer assigns an owner revenue share.
            share_percent = Decimal("0")
            contract_id = None
            owner_share = Decimal("0")
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
                  WHERE id=?""", (next(iter(currencies)), *values, contract_id, existing["id"]))
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
        # Participation-contract payouts are retired. Keep historical settlement
        # records intact, but prevent any new settlement against legacy owner_share.
        require_owner(user)
        raise HTTPException(410, "تسویه سهم قرارداد مشارکت غیرفعال است؛ سوابق تاریخی حفظ شده‌اند.")

    @router.post("/reports/{report_id}/adjustments")
    def request_adjustment(report_id: int, body: AdjustmentIn, user=Depends(user_dependency)):
        period_start(body.adjustment_period)
        with db_factory() as c:
            report = c.execute("SELECT * FROM finance_reports WHERE id=? AND tenant_id=?", (report_id, user["tenant_id"])).fetchone()
            if not report:
                raise HTTPException(404, "گزارش پیدا نشد.")
            if report["status"] not in ("approved", "closed", "disputed"):
                raise HTTPException(409, "درخواست اصلاحیه فقط برای گزارش تأییدشده یا مورد اختلاف ممکن است.")
            if period_start(body.adjustment_period) <= period_start(report["period"]):
                raise HTTPException(422, "اصلاحیه باید در یک دوره بعد از گزارش اصلی ثبت شود.")
            if body.currency != report["currency"]:
                raise HTTPException(422, "واحد پول اصلاحیه باید با گزارش اصلی یکسان باشد.")
            values = {key: money(getattr(body, key)) for key in ("sales_adjustment", "discounts_adjustment", "returns_adjustment", "cogs_adjustment", "direct_costs_adjustment")}
            if not any(values.values()):
                raise HTTPException(422, "حداقل یکی از مقادیر اصلاحیه باید غیرصفر باشد.")
            cur = c.execute("""INSERT INTO finance_adjustments
              (tenant_id,target_report_id,adjustment_period,currency,sales_adjustment,discounts_adjustment,returns_adjustment,cogs_adjustment,direct_costs_adjustment,reason)
              VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (user["tenant_id"], report_id, body.adjustment_period, body.currency, *[format(v, "f") for v in values.values()], body.reason.strip()))
            audit(c, user, "finance.adjustment.requested", {"adjustment_id": cur.lastrowid, "target_report_id": report_id, "adjustment_period": body.adjustment_period})
            return dict(c.execute("SELECT * FROM finance_adjustments WHERE id=?", (cur.lastrowid,)).fetchone())

    @router.get("/adjustments")
    def list_adjustments(user=Depends(user_dependency)):
        with db_factory() as c:
            if is_owner(user):
                rows = c.execute("""SELECT fa.*,t.name AS company_name FROM finance_adjustments fa
                  JOIN tenants t ON t.id=fa.tenant_id ORDER BY fa.id DESC LIMIT 500""").fetchall()
            else:
                rows = c.execute("SELECT * FROM finance_adjustments WHERE tenant_id=? ORDER BY id DESC LIMIT 100", (user["tenant_id"],)).fetchall()
        return [dict(x) for x in rows]

    @router.post("/adjustments/{adjustment_id}/review")
    def review_adjustment(adjustment_id: int, decision: str, user=Depends(user_dependency)):
        require_owner(user)
        if decision not in ("approve", "reject"):
            raise HTTPException(422, "تصمیم باید approve یا reject باشد.")
        with db_factory() as c:
            row = c.execute("SELECT * FROM finance_adjustments WHERE id=?", (adjustment_id,)).fetchone()
            if not row:
                raise HTTPException(404, "درخواست اصلاحیه پیدا نشد.")
            if row["status"] != "pending":
                raise HTTPException(409, "این اصلاحیه قبلاً بررسی شده است.")
            status_value = "approved" if decision == "approve" else "rejected"
            c.execute("UPDATE finance_adjustments SET status=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
                      (status_value, user.get("email", ""), adjustment_id))
            audit(c, user, "finance.adjustment." + status_value, {"adjustment_id": adjustment_id, "target_report_id": row["target_report_id"]}, tenant_id=row["tenant_id"])
        return {"ok": True, "status": status_value, "message": "تصمیم درباره اصلاحیه ثبت شد."}

    @router.get("/owner/overview")
    def owner_overview(user=Depends(user_dependency)):
        require_owner(user)
        with db_factory() as c:
            counts = c.execute("""SELECT
              0 AS contracts,
              0 AS pending_contracts,
              (SELECT COUNT(*) FROM finance_reports WHERE status IN ('pending','disputed')) AS pending_reports,
              0 AS unsettled_reports,
              0.0 AS approved_share,
              0.0 AS unpaid_share""").fetchone()
            by_month = c.execute("""SELECT period,COUNT(*) AS reports,
              SUM(CAST(net_sales AS REAL)) AS net_sales,
              SUM(CAST(eligible_profit AS REAL)) AS eligible_profit,
              0.0 AS owner_share
              FROM finance_reports GROUP BY period ORDER BY period DESC LIMIT 12""").fetchall()
            companies = c.execute("""SELECT t.id AS tenant_id,t.name AS company_name,
              NULL AS contract_status,NULL AS share_percent,NULL AS goal_name,NULL AS goal_achieved,
              fs.integration_status,fs.updated_at AS source_updated_at
              FROM tenants t LEFT JOIN finance_settings fs ON fs.tenant_id=t.id
              ORDER BY t.name LIMIT 500""").fetchall()
        return {"counts": dict(counts), "by_month": [dict(x) for x in by_month], "companies": [dict(x) for x in companies]}

    @router.get("/owner/audit")
    def owner_audit(limit: int = 100, user=Depends(user_dependency)):
        require_owner(user)
        with db_factory() as c:
            rows = c.execute("SELECT * FROM finance_audit ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)).fetchall()
        return [dict(x) for x in rows]

    return router
