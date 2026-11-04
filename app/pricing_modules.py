"""Owner-managed modular pricing and tenant module requests for LEADORA."""
import hmac
import os
import sqlite3
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, StrictInt

MODULES = {
    "crm_sales": "مشتری‌یابی و فروش",
    "distribution": "انبار و پخش",
    "accounting": "حسابداری و خزانه‌داری",
    "ai_agents": "دستیارهای هوشمند",
}
CURRENCY_DEFAULT = "IRR"

class PriceUpdate(BaseModel):
    modules: dict[str, StrictInt] = Field(description="Monthly price per module in the configured currency; 0 means free")
    active_modules: list[str] = Field(default_factory=lambda: list(MODULES))
    currency: str = Field(pattern="^IRR$")
    currency_label: str = Field(pattern="^ریال$")
    unit_review_confirmed: bool = False
    base_monthly_price: StrictInt = Field(ge=0)
    pricing_note: str = Field(default="", max_length=500)

def create_router(db, user_from_header):
    router = APIRouter()
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS leadora_module_prices(
            module_key TEXT PRIMARY KEY, module_name TEXT NOT NULL,
            monthly_price INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS leadora_pricing_settings(
            id INTEGER PRIMARY KEY CHECK(id=1), currency TEXT NOT NULL DEFAULT 'IRR',
            currency_label TEXT NOT NULL DEFAULT 'ریال', base_monthly_price INTEGER NOT NULL DEFAULT 0,
            pricing_note TEXT NOT NULL DEFAULT ''
        );
        INSERT OR IGNORE INTO leadora_pricing_settings(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS tenant_module_requests(
            tenant_id INTEGER NOT NULL, module_key TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'off',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(tenant_id,module_key)
        );
        """)
        for key, name in MODULES.items():
            c.execute("INSERT OR IGNORE INTO leadora_module_prices(module_key,module_name,monthly_price,active) VALUES(?,?,0,1)", (key,name))

    def require_owner(
        x_leadora_owner_key: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        # Keep the legacy secret-key path for existing integrations, but prefer the
        # same per-user owner authorization used by the financial participation module.
        expected = os.getenv("LEADORA_OWNER_KEY", "")
        if len(expected) >= 24 and x_leadora_owner_key and hmac.compare_digest(expected, x_leadora_owner_key):
            return True

        if authorization:
            try:
                user = user_from_header(authorization)
            except HTTPException:
                user = None
            if user:
                user_id = str(user.get("id", ""))
                allowlist = {
                    value.strip()
                    for value in os.getenv("LEADORA_OWNER_USER_IDS", "").split(",")
                    if value.strip()
                }
                if user_id and user_id in allowlist:
                    return True
                # The finance router initializes this table before the pricing router.
                # Fail closed if it is unavailable for any reason.
                try:
                    with db() as c:
                        owner = c.execute(
                            "SELECT user_id FROM finance_platform_owner WHERE singleton=1"
                        ).fetchone()
                    if owner and str(owner["user_id"]) == user_id:
                        return True
                except sqlite3.OperationalError:
                    pass

        raise HTTPException(403, "این عملیات فقط برای مالک سامانه مجاز است.")

    @router.get("/api/plans")
    def public_plans():
        with db() as c:
            settings = dict(c.execute("SELECT currency,currency_label,base_monthly_price,pricing_note FROM leadora_pricing_settings WHERE id=1").fetchone())
            prices = c.execute("SELECT module_key,module_name,monthly_price,active FROM leadora_module_prices ORDER BY module_key").fetchall()
        return {"product":"LEADORA","separate_from_ARIANA":True,"settings":settings,
                "modules":[dict(r) for r in prices if r["active"]], "billing_enabled":False,
                "notice":"قیمت‌ها توسط مالک تعیین می‌شوند؛ دریافت وجه آنلاین تا اتصال درگاه پرداخت فعال نیست."}

    @router.get("/api/owner/pricing")
    def get_owner_pricing(_=Depends(require_owner)):
        with db() as c:
            settings = dict(c.execute("SELECT currency,currency_label,base_monthly_price,pricing_note FROM leadora_pricing_settings WHERE id=1").fetchone())
            modules = [dict(r) for r in c.execute("SELECT module_key,module_name,monthly_price,active FROM leadora_module_prices ORDER BY module_key")]
        return {"settings":settings,"modules":modules}

    @router.put("/api/owner/pricing")
    def set_owner_pricing(body: PriceUpdate, _=Depends(require_owner)):
        unknown = (set(body.modules) | set(body.active_modules)) - set(MODULES)
        if unknown:
            raise HTTPException(422, "شناسه ماژول نامعتبر است.")
        if any(type(v) is not int or v < 0 for v in body.modules.values()):
            raise HTTPException(422, "قیمت هر ماژول باید عدد صحیح و غیرمنفی باشد.")
        with db() as c:
            current = c.execute("SELECT currency,currency_label FROM leadora_pricing_settings WHERE id=1").fetchone()
            if (current["currency"] != "IRR" or current["currency_label"] != "ریال") and not body.unit_review_confirmed:
                raise HTTPException(409, "قیمت‌های قبلی واحد تأییدشده ندارند؛ مبالغ پایه و ماژول‌ها را بررسی کنید و تأیید بازبینی واحد ریال را فعال کنید.")
            c.execute("UPDATE leadora_pricing_settings SET currency=?,currency_label=?,base_monthly_price=?,pricing_note=? WHERE id=1",
                      (body.currency.upper(),body.currency_label,body.base_monthly_price,body.pricing_note))
            for key, price in body.modules.items():
                c.execute("UPDATE leadora_module_prices SET monthly_price=? WHERE module_key=?", (price,key))
            for key in MODULES:
                c.execute("UPDATE leadora_module_prices SET active=? WHERE module_key=?", (1 if key in body.active_modules else 0,key))
        return {"saved":True,"message":"تنظیمات قیمت ذخیره شد."}

    @router.get("/api/modules")
    def tenant_modules(user=Depends(user_from_header)):
        with db() as c:
            rows = c.execute("""SELECT p.module_key,p.module_name,p.monthly_price,p.active,
                COALESCE(r.status,'off') AS status FROM leadora_module_prices p
                LEFT JOIN tenant_module_requests r ON r.module_key=p.module_key AND r.tenant_id=?
                ORDER BY p.module_key""",(user["tenant_id"],)).fetchall()
            settings = dict(c.execute("SELECT currency,currency_label,base_monthly_price FROM leadora_pricing_settings WHERE id=1").fetchone())
        return {"settings":settings,"modules":[dict(r) for r in rows]}

    @router.put("/api/modules/{module_key}/request")
    def request_module(module_key: str, user=Depends(user_from_header)):
        if module_key not in MODULES:
            raise HTTPException(404, "ماژول یافت نشد.")
        with db() as c:
            row = c.execute("SELECT active FROM leadora_module_prices WHERE module_key=?",(module_key,)).fetchone()
            if not row or not row["active"]:
                raise HTTPException(409, "این ماژول فعلاً ارائه نمی‌شود.")
            c.execute("""INSERT INTO tenant_module_requests(tenant_id,module_key,status,updated_at)
                VALUES(?,?,'requested',CURRENT_TIMESTAMP)
                ON CONFLICT(tenant_id,module_key) DO UPDATE SET status='requested',updated_at=CURRENT_TIMESTAMP""",
                (user["tenant_id"],module_key))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"module.requested:"+module_key))
        return {"status":"requested","message":"درخواست ثبت شد؛ فعال‌سازی نهایی با مالک است."}

    @router.put("/api/owner/modules/{tenant_id}/{module_key}")
    def set_tenant_module(tenant_id: int, module_key: str, body: dict, _=Depends(require_owner)):
        status = body.get("status")
        if module_key not in MODULES or status not in ("off","requested","active","suspended"):
            raise HTTPException(422, "ماژول یا وضعیت نامعتبر است.")
        with db() as c:
            if not c.execute("SELECT id FROM tenants WHERE id=?",(tenant_id,)).fetchone():
                raise HTTPException(404, "شرکت یافت نشد.")
            c.execute("""INSERT INTO tenant_module_requests(tenant_id,module_key,status,updated_at)
                VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(tenant_id,module_key)
                DO UPDATE SET status=excluded.status,updated_at=CURRENT_TIMESTAMP""",(tenant_id,module_key,status))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tenant_id,"module.status:"+module_key+":"+status))
        return {"saved":True,"tenant_id":tenant_id,"module":module_key,"status":status}

    return router
