import os, sqlite3, secrets, hashlib, hmac, time, re
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import FileResponse, StreamingResponse
import csv, io, json
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, AliasChoices

ROOT = Path(__file__).resolve().parent
DB_PATH = os.getenv("LEADORA_DB", str(ROOT.parent / "data" / "leadora.db"))
SECRET = os.getenv("LEADORA_SECRET", "development-only-change-me")
ENV = os.getenv("LEADORA_ENV", "development")
if ENV == "production" and (len(SECRET) < 32 or SECRET == "development-only-change-me"):
    raise RuntimeError("Set a random LEADORA_SECRET of at least 32 characters")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="LEADORA MVP", version="0.5.0", description="Persian-first business operations MVP")

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
    return response

def db():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS tenants(id INTEGER PRIMARY KEY, name TEXT NOT NULL, industry TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), email TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL, UNIQUE(tenant_id,email));
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), sku TEXT NOT NULL, name TEXT NOT NULL, price REAL NOT NULL DEFAULT 0 CHECK(price>=0), stock REAL NOT NULL DEFAULT 0 CHECK(stock>=0), UNIQUE(tenant_id,sku));
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id), name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, action TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS login_attempts(attempt_key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start INTEGER NOT NULL);
        """)
init_db()

# Additive licensing and tenant-owned bank-account metadata; never reset the persistent DB.
with db() as _conn:
    _conn.executescript("""
    CREATE TABLE IF NOT EXISTS tenant_licenses(
      tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id),
      status TEXT NOT NULL DEFAULT 'trial' CHECK(status IN ('trial','active','expired','suspended')),
      trial_started_at TEXT NOT NULL,
      trial_ends_at TEXT NOT NULL,
      edition TEXT NOT NULL DEFAULT 'standard',
      activated_at TEXT,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS activation_keys(
      id INTEGER PRIMARY KEY,
      tenant_id INTEGER NOT NULL REFERENCES tenants(id),
      key_hash TEXT NOT NULL UNIQUE,
      edition TEXT NOT NULL DEFAULT 'standard',
      created_by_user_id INTEGER NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      expires_at TEXT,
      redeemed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS tenant_bank_accounts(
      id INTEGER PRIMARY KEY,
      tenant_id INTEGER NOT NULL REFERENCES tenants(id),
      label TEXT NOT NULL,
      institution TEXT NOT NULL DEFAULT '',
      account_holder TEXT NOT NULL DEFAULT '',
      iban_masked TEXT NOT NULL DEFAULT '',
      currency TEXT NOT NULL DEFAULT 'EUR',
      is_default INTEGER NOT NULL DEFAULT 0,
      provider TEXT NOT NULL DEFAULT 'manual',
      connection_status TEXT NOT NULL DEFAULT 'not_configured',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_bank_accounts_tenant ON tenant_bank_accounts(tenant_id,id);
    """)
    # Preserve existing tenants and create a maximum 90-day trial for legacy accounts without a license row.
    _now = datetime.now(timezone.utc) if 'datetime' in globals() else __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    _start = _now.isoformat()
    _end = (_now + __import__('datetime').timedelta(days=90)).isoformat()
    _conn.execute("INSERT OR IGNORE INTO tenant_licenses(tenant_id,status,trial_started_at,trial_ends_at) SELECT id,'trial',?,? FROM tenants", (_start,_end))

def pw_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180000).hex()

def login_attempt_key(company_name, email):
    identity = f"{company_name.strip().casefold()}\\0{email.strip().lower()}"
    return hashlib.sha256((SECRET + identity).encode()).hexdigest()

def check_login_throttle(attempt_key):
    now = int(time.time())
    with db() as c:
        row = c.execute("SELECT attempts,window_start FROM login_attempts WHERE attempt_key=?", (attempt_key,)).fetchone()
        if row and now - row["window_start"] < 900 and row["attempts"] >= 5:
            raise HTTPException(429, "تعداد تلاش‌های ورود زیاد است؛ ۱۵ دقیقه دیگر دوباره تلاش کنید.")
        if row and now - row["window_start"] >= 900:
            c.execute("DELETE FROM login_attempts WHERE attempt_key=?", (attempt_key,))

def record_login_failure(attempt_key):
    now = int(time.time())
    with db() as c:
        row = c.execute("SELECT attempts,window_start FROM login_attempts WHERE attempt_key=?", (attempt_key,)).fetchone()
        if not row or now - row["window_start"] >= 900:
            c.execute("INSERT OR REPLACE INTO login_attempts(attempt_key,attempts,window_start) VALUES(?,?,?)", (attempt_key, 1, now))
        else:
            c.execute("UPDATE login_attempts SET attempts=attempts+1 WHERE attempt_key=?", (attempt_key,))

def clear_login_failures(attempt_key):
    with db() as c:
        c.execute("DELETE FROM login_attempts WHERE attempt_key=?", (attempt_key,))

def token(uid, tid):
    raw = f"{uid}:{tid}:{int(time.time())+43200}:{secrets.token_urlsafe(12)}"
    sig = hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return raw + "." + sig

def user_from_header(authorization: str | None = Header(default=None), request: Request = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "ابتدا وارد شوید.")
    try:
        raw, sig = authorization[7:].rsplit(".", 1)
        expected = hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected): raise ValueError()
        uid, tid, exp, _ = raw.split(":", 3)
        if int(exp) < int(time.time()): raise ValueError()
        with db() as c:
            u = c.execute("SELECT id,tenant_id,email FROM users WHERE id=? AND tenant_id=?", (int(uid),int(tid))).fetchone()
        if not u: raise ValueError()
        user = dict(u)
        # Enforce trial/license state server-side for all tenant business routes.
        allowed_owner_ids = {part.strip() for part in os.getenv("LEADORA_OWNER_USER_IDS", "").split(",") if part.strip()}
        allowed_paths = {"/api/account/license", "/api/account/license/activate", "/api/health"}
        if (request.url.path if request is not None else "") not in allowed_paths and str(user["id"]) not in allowed_owner_ids:
            license_row = _license_for_tenant(user["tenant_id"])
            if license_row["status"] in ("expired", "suspended"):
                raise HTTPException(402, "دوره آزمایشی پایان یافته یا مجوز غیرفعال است؛ کلید مجوز معتبر را فعال کنید.")
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "نشست نامعتبر یا منقضی است.")

class RegisterIn(BaseModel):
    company_name: str = Field(min_length=2,max_length=120)
    industry: str = Field(min_length=2,max_length=80)
    email: str = Field(min_length=5,max_length=180)
    password: str = Field(min_length=10,max_length=200)
class LoginIn(BaseModel):
    company_name: str = Field(min_length=2,max_length=120)
    email: str = Field(min_length=5,max_length=180)
    password: str = Field(min_length=1,max_length=200)
class ProductIn(BaseModel):
    sku: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=1,max_length=180)
    price: float = Field(default=0,ge=0)
    stock: float = Field(default=0,ge=0)
class CustomerIn(BaseModel):
    name: str = Field(min_length=1,max_length=180)
    phone: str = Field(default="",max_length=80)

@app.get("/")
def home(): return FileResponse(ROOT / "static" / "index.html")

@app.get("/bank-accounts")
def bank_accounts_page(): return FileResponse(ROOT / "static" / "bank-accounts.html")

@app.get("/manifest.webmanifest")
def pwa_manifest():
    return FileResponse(ROOT / "static" / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/service-worker.js")
def pwa_service_worker():
    return FileResponse(ROOT / "static" / "service-worker.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})

@app.get("/icon.svg")
def pwa_icon():
    return FileResponse(ROOT / "static" / "icon.svg", media_type="image/svg+xml")

@app.get("/favicon.ico")
def favicon():
    # Serve the existing vector icon to browsers that request the conventional favicon path.
    return FileResponse(ROOT / "static" / "icon.svg", media_type="image/svg+xml")

@app.get("/api/health")
def health():
    with db() as c: c.execute("SELECT 1")
    return {"status":"ok","database":"ok","product":"LEADORA","version":"0.5.0","mode":"mvp"}

@app.post("/api/register")
def register(body: RegisterIn):
    company_name = body.company_name.strip()
    industry = body.industry.strip()
    email = body.email.strip().lower()
    if not company_name or not industry:
        raise HTTPException(422, "نام شرکت و حوزه فعالیت نباید خالی باشد.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "قالب ایمیل معتبر نیست.")
    salt=secrets.token_hex(16)
    with db() as c:
        try:
            tid=c.execute("INSERT INTO tenants(name,industry) VALUES(?,?)",(company_name,industry)).lastrowid
            uid=c.execute("INSERT INTO users(tenant_id,email,salt,password_hash) VALUES(?,?,?,?)",(tid,email,salt,pw_hash(body.password,salt))).lastrowid
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"tenant.registered"))
            _trial_start = datetime.now(timezone.utc)
            c.execute("INSERT OR IGNORE INTO tenant_licenses(tenant_id,status,trial_started_at,trial_ends_at) VALUES(?,?,?,?)",
                      (tid,"trial",_trial_start.isoformat(),(_trial_start+timedelta(days=90)).isoformat()))
        except sqlite3.IntegrityError:
            raise HTTPException(409,"این ایمیل قبلاً برای این شرکت ثبت شده است.")
    return {"token":token(uid,tid),"tenant":{"id":tid,"name":company_name,"industry":industry},"user":{"id":uid,"email":email}}

@app.post("/api/login")
def login(body: LoginIn):
    email = body.email.strip().lower()
    company_name = body.company_name.strip().lower()
    attempt_key = login_attempt_key(company_name, email)
    check_login_throttle(attempt_key)
    with db() as c:
        rows=c.execute("SELECT u.id,u.tenant_id,u.email,u.salt,u.password_hash FROM users u JOIN tenants t ON t.id=u.tenant_id WHERE lower(u.email)=? AND lower(t.name)=? ORDER BY u.id",(email,company_name)).fetchall()
    # Check all matching accounts because company names and email addresses are not globally unique.
    row = next((candidate for candidate in rows if hmac.compare_digest(pw_hash(body.password,candidate["salt"]),candidate["password_hash"])), None)
    if not rows:
        # Keep nonexistent-account failures closer in cost to a real password check.
        pw_hash(body.password, "leadora-dummy-salt")
    if not row:
        record_login_failure(attempt_key)
        raise HTTPException(401,"اطلاعات ورود صحیح نیست.")
    clear_login_failures(attempt_key)
    return {"token":token(row["id"],row["tenant_id"]),"user":{"email":row["email"]}}

@app.get("/api/products")
def products(user=Depends(user_from_header)):
    with db() as c: rows=c.execute("SELECT id,sku,name,price,stock FROM products WHERE tenant_id=? ORDER BY id DESC",(user["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/products")
def add_product(body: ProductIn,user=Depends(user_from_header)):
    if not body.sku.strip() or not body.name.strip():
        raise HTTPException(422, "کد و نام کالا نباید خالی باشد.")
    with db() as c:
        try:
            cur=c.execute("INSERT INTO products(tenant_id,sku,name,price,stock) VALUES(?,?,?,?,?)",(user["tenant_id"],body.sku.strip(),body.name.strip(),body.price,body.stock))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"product.created"))
        except sqlite3.IntegrityError: raise HTTPException(409,"کد کالا تکراری است.")
    return {"id":cur.lastrowid,"message":"کالا ثبت شد."}



@app.put("/api/products/{product_id}")
def update_product(product_id: int, body: ProductIn, user=Depends(user_from_header)):
    sku, name = body.sku.strip(), body.name.strip()
    if not sku or not name:
        raise HTTPException(422, "کد و نام کالا نباید خالی باشد.")
    with db() as c:
        try:
            cur = c.execute(
                "UPDATE products SET sku=?,name=?,price=?,stock=? WHERE id=? AND tenant_id=?",
                (sku, name, body.price, body.stock, product_id, user["tenant_id"]),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "کد کالا تکراری است.")
        if cur.rowcount == 0:
            raise HTTPException(404, "کالا یافت نشد.")
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",
                  (user["tenant_id"], "product.updated"))
    return {"message": "اطلاعات کالا به‌روزرسانی شد."}


@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, user=Depends(user_from_header)):
    with db() as c:
        cur = c.execute("DELETE FROM products WHERE id=? AND tenant_id=?",
                        (product_id, user["tenant_id"]))
        if cur.rowcount == 0:
            raise HTTPException(404, "کالا یافت نشد.")
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",
                  (user["tenant_id"], "product.deleted"))
    return {"message": "کالا حذف شد."}

@app.get("/api/customers")
def customers(user=Depends(user_from_header)):
    with db() as c: rows=c.execute("SELECT id,name,phone FROM customers WHERE tenant_id=? ORDER BY id DESC",(user["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/customers")
def add_customer(body: CustomerIn,user=Depends(user_from_header)):
    if not body.name.strip():
        raise HTTPException(422, "نام مشتری نباید خالی باشد.")
    with db() as c:
        cur=c.execute("INSERT INTO customers(tenant_id,name,phone) VALUES(?,?,?)",(user["tenant_id"],body.name.strip(),body.phone.strip()))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"customer.created"))
    return {"id":cur.lastrowid,"message":"مشتری ثبت شد."}



@app.put("/api/customers/{customer_id}")
def update_customer(customer_id: int, body: CustomerIn, user=Depends(user_from_header)):
    name, phone = body.name.strip(), body.phone.strip()
    if not name:
        raise HTTPException(422, "نام مشتری نباید خالی باشد.")
    with db() as c:
        cur = c.execute(
            "UPDATE customers SET name=?,phone=? WHERE id=? AND tenant_id=?",
            (name, phone, customer_id, user["tenant_id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "مشتری یافت نشد.")
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",
                  (user["tenant_id"], "customer.updated"))
    return {"message": "اطلاعات مشتری به‌روزرسانی شد."}


@app.delete("/api/customers/{customer_id}")
def delete_customer(customer_id: int, user=Depends(user_from_header)):
    with db() as c:
        cur = c.execute("DELETE FROM customers WHERE id=? AND tenant_id=?",
                        (customer_id, user["tenant_id"]))
        if cur.rowcount == 0:
            raise HTTPException(404, "مشتری یافت نشد.")
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",
                  (user["tenant_id"], "customer.deleted"))
    return {"message": "مشتری حذف شد."}


@app.get("/api/audit-log")
def audit_log(limit: int = 100, user=Depends(user_from_header)):
    limit = max(1, min(limit, 500))
    with db() as c:
        rows = c.execute(
            "SELECT id,action,created_at FROM audit_log WHERE tenant_id=? ORDER BY id DESC LIMIT ?",
            (user["tenant_id"], limit),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/export/{dataset}.csv")
def export_csv(dataset: str, user=Depends(user_from_header)):
    queries = {
        "products": ("SELECT sku,name,price,stock FROM products WHERE tenant_id=? ORDER BY id", ["sku", "name", "price", "stock"]),
        "customers": ("SELECT name,phone FROM customers WHERE tenant_id=? ORDER BY id", ["name", "phone"]),
    }
    if dataset not in queries:
        raise HTTPException(404, "نوع خروجی پشتیبانی نمی‌شود.")
    query, columns = queries[dataset]
    with db() as c:
        rows = c.execute(query, (user["tenant_id"],)).fetchall()
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(columns)
    writer.writerows([[row[col] for col in columns] for row in rows])
    return StreamingResponse(
        iter(["\ufeff" + stream.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="leadora-{dataset}.csv"', "Cache-Control": "no-store"},
    )


@app.get("/api/backup.json")
def export_tenant_backup(user=Depends(user_from_header)):
    # Export tenant-owned business data while never exporting credentials or platform-wide secrets.
    sensitive_column = re.compile(r"(?:password|secret|token|salt|credential|api[_-]?key|private[_-]?key|key_hash)", re.I)
    excluded_tables = {
        "users", "login_attempts", "finance_platform_owner",
        "finance_integration_keys", "prospecting_worker_lease",
    }
    with db() as c:
        tenant = c.execute(
            "SELECT id,name,industry FROM tenants WHERE id=?", (user["tenant_id"],)
        ).fetchone()
        if tenant is None:
            raise HTTPException(404, "شرکت یافت نشد.")
        table_names = [
            row["name"] for row in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
        tenant_tables = {}
        for table_name in table_names:
            if table_name in excluded_tables or table_name == "tenants":
                continue
            quoted = '"' + table_name.replace('"', '""') + '"'
            columns = c.execute(f"PRAGMA table_info({quoted})").fetchall()
            column_names = [column["name"] for column in columns]
            if "tenant_id" not in column_names or any(sensitive_column.search(name) for name in column_names):
                continue
            order_by = " ORDER BY id" if "id" in column_names else ""
            rows = c.execute(
                f"SELECT * FROM {quoted} WHERE tenant_id=?{order_by}", (user["tenant_id"],)
            ).fetchall()
            if rows:
                tenant_tables[table_name] = [dict(row) for row in rows]

        # Keep the original top-level keys for existing clients while adding all non-sensitive
        # tenant-scoped tables from the business modules.
        products = tenant_tables.get("products", [])
        customers = tenant_tables.get("customers", [])
        audit = tenant_tables.get("audit_log", [])
    payload = json.dumps({
        "format": "leadora-tenant-backup-v2",
        "tenant": dict(tenant),
        "products": products,
        "customers": customers,
        "audit_log": audit,
        "tables": tenant_tables,
    }, ensure_ascii=False, indent=2, default=str)
    return StreamingResponse(
        iter([payload]),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="leadora-backup.json"', "Cache-Control": "no-store"},
    )


@app.get("/api/insights")
def insights(user=Depends(user_from_header)):
    with db() as c:
        low=c.execute("SELECT sku,name,stock FROM products WHERE tenant_id=? AND stock<=5 ORDER BY stock",(user["tenant_id"],)).fetchall()
    return {"mode":"rules_based_mvp","low_stock":[dict(r) for r in low],"message":"تحلیل قواعدمحور نمونه؛ نه خروجی مدل هوش مصنوعی."}



# LEADORA multi-industry business intelligence modules (rule-based first; no fabricated AI predictions).
def init_agent_tables():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS invoices(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          customer_id INTEGER, invoice_number TEXT NOT NULL, issue_date TEXT NOT NULL,
          due_date TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>0),
          note TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tenant_id,invoice_number));
        CREATE TABLE IF NOT EXISTS payments(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          invoice_id INTEGER NOT NULL, paid_at TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>0),
          method TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS expenses(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          title TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'عمومی', amount REAL NOT NULL CHECK(amount>0),
          due_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','paid')),
          created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS opportunities(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          title TEXT NOT NULL, customer_id INTEGER, source TEXT NOT NULL DEFAULT '',
          stage TEXT NOT NULL DEFAULT 'new', estimated_value REAL NOT NULL DEFAULT 0 CHECK(estimated_value>=0),
          expected_close_date TEXT NOT NULL DEFAULT '', last_contact_date TEXT NOT NULL DEFAULT '',
          lost_reason TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS interactions(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          customer_id INTEGER NOT NULL, interaction_type TEXT NOT NULL, occurred_at TEXT NOT NULL,
          notes TEXT NOT NULL DEFAULT '', next_followup_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS campaigns(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          name TEXT NOT NULL, channel TEXT NOT NULL DEFAULT '', spend REAL NOT NULL DEFAULT 0 CHECK(spend>=0),
          leads INTEGER NOT NULL DEFAULT 0 CHECK(leads>=0), conversions INTEGER NOT NULL DEFAULT 0 CHECK(conversions>=0),
          revenue REAL NOT NULL DEFAULT 0 CHECK(revenue>=0), start_date TEXT NOT NULL DEFAULT '', end_date TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS agent_actions(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          agent TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'medium',
          title TEXT NOT NULL, rationale TEXT NOT NULL, recommendation TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'suggested' CHECK(status IN ('suggested','approved','dismissed','done')),
          sensitive INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
init_agent_tables()

class InvoiceIn(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=100)
    customer_id: int | None = None
    issue_date: str = Field(min_length=10, max_length=10)
    due_date: str = Field(min_length=10, max_length=10)
    amount: float = Field(gt=0, le=1_000_000_000_000)
    note: str = Field(default="", max_length=1000)
class PaymentIn(BaseModel):
    invoice_id: int
    paid_at: str = Field(min_length=10, max_length=10)
    amount: float = Field(gt=0, le=1_000_000_000_000)
    method: str = Field(default="", max_length=80)
    reference: str = Field(default="", max_length=120)
class ExpenseIn(BaseModel):
    title: str = Field(min_length=1, max_length=180, validation_alias=AliasChoices("title", "description"))
    category: str = Field(default="عمومی", max_length=100)
    amount: float = Field(gt=0, le=1_000_000_000_000)
    due_date: str = Field(min_length=10, max_length=10)
    status: str = Field(default="pending", pattern="^(pending|paid|planned)$")
    vendor: str = Field(default="", max_length=180)
class OpportunityIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    customer_id: int | None = None
    source: str = Field(default="", max_length=100)
    stage: str = Field(default="new", max_length=60)
    estimated_value: float = Field(default=0, ge=0, le=1_000_000_000_000)
    expected_close_date: str = Field(default="", max_length=10)
    last_contact_date: str = Field(default="", max_length=10)
    lost_reason: str = Field(default="", max_length=500)
class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    channel: str = Field(default="", max_length=100)
    spend: float = Field(default=0, ge=0)
    leads: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    revenue: float = Field(default=0, ge=0)
    start_date: str = Field(default="", max_length=10)
    end_date: str = Field(default="", max_length=10)
class ImportRowsIn(BaseModel):
    dataset: str = Field(pattern="^(invoices|expenses|opportunities|campaigns)$")
    rows: list[dict] = Field(min_length=1, max_length=2000)

def _date_ok(value):
    try:
        from datetime import date
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False

def _insert_invoice(c, tid, x):
    if not _date_ok(x.issue_date) or not _date_ok(x.due_date) or x.due_date < x.issue_date:
        raise HTTPException(422, "تاریخ صدور و سررسید باید معتبر باشند و سررسید قبل از صدور نباشد.")
    if x.customer_id is not None and not c.execute("SELECT 1 FROM customers WHERE id=? AND tenant_id=?", (x.customer_id,tid)).fetchone():
        raise HTTPException(422, "مشتری متعلق به این شرکت نیست.")
    cur=c.execute("INSERT INTO invoices(tenant_id,customer_id,invoice_number,issue_date,due_date,amount,note) VALUES(?,?,?,?,?,?,?)",
      (tid,x.customer_id,x.invoice_number.strip(),x.issue_date,x.due_date,x.amount,x.note.strip()))
    return cur.lastrowid

@app.get("/agents")
def agents_page():
    return FileResponse(ROOT / "static" / "agents.html")

@app.post("/api/invoices")
def create_invoice(body: InvoiceIn, user=Depends(user_from_header)):
    if not body.invoice_number.strip(): raise HTTPException(422, "شماره فاکتور الزامی است.")
    with db() as c:
        try: ident=_insert_invoice(c,user["tenant_id"],body)
        except sqlite3.IntegrityError: raise HTTPException(409,"شماره فاکتور تکراری است.")
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"invoice.created"))
    return {"id":ident,"message":"فاکتور ثبت شد."}

@app.get("/api/invoices")
def list_invoices(user=Depends(user_from_header)):
    with db() as c:
        rows=c.execute("""SELECT i.id,i.invoice_number,i.customer_id,COALESCE(cu.name,'بدون مشتری') customer_name,
          i.issue_date,i.due_date,i.amount,COALESCE(SUM(p.amount),0) paid,
          MAX(i.amount-COALESCE((SELECT SUM(p2.amount) FROM payments p2 WHERE p2.invoice_id=i.id AND p2.tenant_id=i.tenant_id),0),0) outstanding
          FROM invoices i LEFT JOIN customers cu ON cu.id=i.customer_id AND cu.tenant_id=i.tenant_id
          LEFT JOIN payments p ON p.invoice_id=i.id AND p.tenant_id=i.tenant_id
          WHERE i.tenant_id=? GROUP BY i.id ORDER BY i.due_date""",(user["tenant_id"],)).fetchall()
    return [dict(x) for x in rows]

@app.post("/api/payments")
def create_payment(body: PaymentIn, user=Depends(user_from_header)):
    if not _date_ok(body.paid_at): raise HTTPException(422,"تاریخ پرداخت معتبر نیست.")
    with db() as c:
        inv=c.execute("SELECT amount FROM invoices WHERE id=? AND tenant_id=?",(body.invoice_id,user["tenant_id"])).fetchone()
        if not inv: raise HTTPException(404,"فاکتور یافت نشد.")
        paid=c.execute("SELECT COALESCE(SUM(amount),0) n FROM payments WHERE invoice_id=? AND tenant_id=?",(body.invoice_id,user["tenant_id"])).fetchone()["n"]
        if body.amount > inv["amount"]-paid+0.000001: raise HTTPException(422,"مبلغ پرداخت از مانده فاکتور بیشتر است.")
        cur=c.execute("INSERT INTO payments(tenant_id,invoice_id,paid_at,amount,method,reference) VALUES(?,?,?,?,?,?)",
          (user["tenant_id"],body.invoice_id,body.paid_at,body.amount,body.method.strip(),body.reference.strip()))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"payment.recorded"))
    return {"id":cur.lastrowid,"message":"پرداخت ثبت شد."}

@app.post("/api/expenses")
def create_expense(body: ExpenseIn, user=Depends(user_from_header)):
    if not body.title.strip() or not _date_ok(body.due_date): raise HTTPException(422,"عنوان و تاریخ معتبر الزامی است.")
    # Legacy API clients may send "planned"; the persistent SQLite schema stores it as pending.
    stored_status = "pending" if body.status == "planned" else body.status
    with db() as c:
        cur=c.execute("INSERT INTO expenses(tenant_id,title,category,amount,due_date,status) VALUES(?,?,?,?,?,?)",
          (user["tenant_id"],body.title.strip(),body.category.strip(),body.amount,body.due_date,stored_status))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"expense.created"))
    return {"id":cur.lastrowid,"message":"هزینه ثبت شد."}

@app.get("/api/expenses")
def list_expenses(user=Depends(user_from_header)):
    with db() as c:
        rows=c.execute("SELECT id,title,category,amount,due_date,status FROM expenses WHERE tenant_id=? ORDER BY due_date",(user["tenant_id"],)).fetchall()
    return [dict(x) for x in rows]

@app.post("/api/opportunities")
def create_opportunity(body: OpportunityIn, user=Depends(user_from_header)):
    if not body.title.strip(): raise HTTPException(422,"عنوان فرصت فروش الزامی است.")
    if body.customer_id is not None:
        with db() as c:
            if not c.execute("SELECT 1 FROM customers WHERE id=? AND tenant_id=?",(body.customer_id,user["tenant_id"])).fetchone():
                raise HTTPException(422,"مشتری متعلق به این شرکت نیست.")
    with db() as c:
        cur=c.execute("INSERT INTO opportunities(tenant_id,title,customer_id,source,stage,estimated_value,expected_close_date,last_contact_date,lost_reason) VALUES(?,?,?,?,?,?,?,?,?)",
          (user["tenant_id"],body.title.strip(),body.customer_id,body.source.strip(),body.stage.strip(),body.estimated_value,body.expected_close_date,body.last_contact_date,body.lost_reason.strip()))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"opportunity.created"))
    return {"id":cur.lastrowid,"message":"فرصت فروش ثبت شد."}

@app.get("/api/opportunities")
def list_opportunities(user=Depends(user_from_header)):
    with db() as c:
        rows=c.execute("SELECT id,title,customer_id,source,stage,estimated_value,expected_close_date,last_contact_date,lost_reason FROM opportunities WHERE tenant_id=? ORDER BY id DESC",(user["tenant_id"],)).fetchall()
    return [dict(x) for x in rows]

@app.post("/api/campaigns")
def create_campaign(body: CampaignIn, user=Depends(user_from_header)):
    if not body.name.strip(): raise HTTPException(422,"نام کمپین الزامی است.")
    with db() as c:
        cur=c.execute("INSERT INTO campaigns(tenant_id,name,channel,spend,leads,conversions,revenue,start_date,end_date) VALUES(?,?,?,?,?,?,?,?,?)",
          (user["tenant_id"],body.name.strip(),body.channel.strip(),body.spend,body.leads,body.conversions,body.revenue,body.start_date,body.end_date))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"campaign.created"))
    return {"id":cur.lastrowid,"message":"کمپین ثبت شد."}

@app.get("/api/campaigns")
def list_campaigns(user=Depends(user_from_header)):
    with db() as c: rows=c.execute("SELECT id,name,channel,spend,leads,conversions,revenue,start_date,end_date FROM campaigns WHERE tenant_id=? ORDER BY id DESC",(user["tenant_id"],)).fetchall()
    return [dict(x) for x in rows]

@app.get("/api/agents/overview")
def agents_overview(user=Depends(user_from_header)):
    from datetime import date, timedelta
    today=date.today().isoformat()
    tid=user["tenant_id"]
    with db() as c:
        invoices=c.execute("""SELECT i.id,i.invoice_number,COALESCE(cu.name,'بدون مشتری') customer_name,i.due_date,i.amount,
          MAX(i.amount-COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.invoice_id=i.id AND p.tenant_id=i.tenant_id),0),0) outstanding
          FROM invoices i LEFT JOIN customers cu ON cu.id=i.customer_id AND cu.tenant_id=i.tenant_id WHERE i.tenant_id=?""",(tid,)).fetchall()
        expenses=c.execute("SELECT * FROM expenses WHERE tenant_id=? AND status='pending'",(tid,)).fetchall()
        opps=c.execute("SELECT * FROM opportunities WHERE tenant_id=?",(tid,)).fetchall()
        campaigns=c.execute("SELECT * FROM campaigns WHERE tenant_id=?",(tid,)).fetchall()
        customers=c.execute("SELECT id,name FROM customers WHERE tenant_id=?",(tid,)).fetchall()
        interactions=c.execute("SELECT * FROM interactions WHERE tenant_id=?",(tid,)).fetchall()
        actions=c.execute("SELECT id,agent,severity,title,rationale,recommendation,status,sensitive,created_at FROM agent_actions WHERE tenant_id=? ORDER BY id DESC LIMIT 100",(tid,)).fetchall()
    aging={"not_due":0,"1_30":0,"31_60":0,"61_90":0,"90_plus":0}
    overdue=[]
    for inv in invoices:
        amount=max(0,float(inv["outstanding"] or 0))
        if amount<=0: continue
        days=(date.fromisoformat(today)-date.fromisoformat(inv["due_date"])).days
        if days<=0: aging["not_due"]+=amount
        else:
            bucket="1_30" if days<=30 else "31_60" if days<=60 else "61_90" if days<=90 else "90_plus"
            aging[bucket]+=amount
            overdue.append({"invoice_number":inv["invoice_number"],"customer":inv["customer_name"],"due_date":inv["due_date"],"days_overdue":days,"outstanding":round(amount,2)})
    overdue.sort(key=lambda x:(-x["days_overdue"],-x["outstanding"]))
    cash=[]
    for offset in range(0,31,7):
        day=(date.today()+timedelta(days=offset)).isoformat()
        inflow=sum(float(i["outstanding"]) for i in invoices if day<=i["due_date"]<=(date.today()+timedelta(days=offset+6)).isoformat())
        outflow=sum(float(e["amount"]) for e in expenses if day<=e["due_date"]<=(date.today()+timedelta(days=offset+6)).isoformat())
        cash.append({"period_start":day,"expected_inflow":round(inflow,2),"expected_outflow":round(outflow,2),"net":round(inflow-outflow,2)})
    stages={}
    for o in opps: stages[o["stage"]]=stages.get(o["stage"],0)+1
    campaign_summary=[{"name":x["name"],"channel":x["channel"],"spend":x["spend"],"leads":x["leads"],"conversions":x["conversions"],"revenue":x["revenue"],"roi":round((x["revenue"]-x["spend"])/x["spend"],3) if x["spend"] else None} for x in campaigns]
    insights=[]
    for inv in overdue:
        insights.append({"agent":"receivables","severity":"high" if inv["days_overdue"]>30 else "medium","title":"مطالبات سررسیدگذشته: "+inv["invoice_number"],"rationale":f'مانده {inv["outstanding"]}؛ تأخیر {inv["days_overdue"]} روز؛ مشتری {inv["customer"]}.',"recommendation":"بررسی وضعیت فاکتور و آماده‌سازی یادآوری محترمانه؛ ارسال پیام نیازمند تأیید.","sensitive":1})
    for e in expenses:
        if e["due_date"]<= (date.today()+timedelta(days=7)).isoformat():
            insights.append({"agent":"cashflow","severity":"medium","title":"هزینه نزدیک به سررسید: "+e["title"],"rationale":f'مبلغ {e["amount"]} با سررسید {e["due_date"]}.',"recommendation":"بررسی مانده نقدی و برنامه پرداخت؛ ثبت یا اجرای پرداخت بدون تأیید انجام نمی‌شود.","sensitive":1})
    for o in opps:
        if o["stage"].lower() not in ("won","closed-won","lost","closed-lost") and o["last_contact_date"] and _date_ok(o["last_contact_date"]) and (date.today()-date.fromisoformat(o["last_contact_date"])).days>=14:
            insights.append({"agent":"retention_sales","severity":"medium","title":"فرصت فروش بدون پیگیری اخیر: "+o["title"],"rationale":f'آخرین تماس {o["last_contact_date"]}.',"recommendation":"بازبینی وضعیت فرصت و تهیه پیش‌نویس پیگیری؛ تماس بیرونی نیازمند تأیید است.","sensitive":1})
    if not invoices: insights.append({"agent":"receivables","severity":"low","title":"داده مطالبات موجود نیست","rationale":"هنوز فاکتوری ثبت نشده است.","recommendation":"فاکتورها را دستی ثبت کنید یا از فایل CSV وارد کنید.","sensitive":0})
    if not opps: insights.append({"agent":"sales_analytics","severity":"low","title":"داده قیف فروش موجود نیست","rationale":"برای محاسبه نرخ تبدیل، فرصت‌های فروش ثبت نشده‌اند.","recommendation":"فرصت‌ها را با مرحله فروش و ارزش تخمینی وارد کنید.","sensitive":0})
    return {"mode":"rules_based","forecast_note":"پیش‌بینی نقدینگی بر پایه سررسیدهای ثبت‌شده است و مانده واقعی بانک/نقد را شامل نمی‌شود.","receivables":{"aging":aging,"overdue":overdue,"outstanding_total":round(sum(float(i["outstanding"]) for i in invoices),2)},"cashflow":{"weekly":cash,"pending_expenses":len(expenses)},"sales":{"opportunities":len(opps),"stages":stages,"pipeline_value":round(sum(float(o["estimated_value"]) for o in opps if o["stage"].lower() not in ("won","closed-won","lost","closed-lost")),2)},"marketing":{"campaigns":campaign_summary,"campaign_count":len(campaigns)},"retention":{"customers":len(customers),"interaction_records":len(interactions),"risk_model":"insufficient_history_rule_based"},"insights":insights,"actions":[dict(x) for x in actions]}

@app.post("/api/agents/actions")
def create_agent_action(body: dict, user=Depends(user_from_header)):
    required=("agent","title","rationale","recommendation")
    if any(not isinstance(body.get(k),str) or not body[k].strip() for k in required):
        raise HTTPException(422,"فیلدهای عامل، عنوان، دلیل و پیشنهاد الزامی‌اند.")
    sensitive=bool(body.get("sensitive",True))
    status="suggested" if sensitive else "approved"
    with db() as c:
        cur=c.execute("INSERT INTO agent_actions(tenant_id,agent,severity,title,rationale,recommendation,status,sensitive) VALUES(?,?,?,?,?,?,?,?)",
          (user["tenant_id"],body["agent"][:80],body.get("severity","medium")[:20],body["title"][:200],body["rationale"][:2000],body["recommendation"][:2000],status,int(sensitive)))
    return {"id":cur.lastrowid,"status":status,"message":"اقدام ثبت شد؛ اقدام حساس برای تأیید باقی می‌ماند." if sensitive else "اقدام کم‌ریسک ثبت شد."}

@app.post("/api/agents/actions/{action_id}/decision")
def decide_agent_action(action_id: int, body: dict, user=Depends(user_from_header)):
    decision=body.get("decision")
    if decision not in ("approved","dismissed","done"): raise HTTPException(422,"تصمیم نامعتبر است.")
    with db() as c:
        cur=c.execute("UPDATE agent_actions SET status=? WHERE id=? AND tenant_id=? AND status='suggested'",(decision,action_id,user["tenant_id"]))
        if cur.rowcount==0: raise HTTPException(404,"اقدام پیشنهادی یافت نشد یا قبلاً تعیین تکلیف شده است.")
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"agent_action."+decision))
    return {"status":decision,"message":"وضعیت اقدام به‌روزرسانی شد."}

@app.post("/api/import/rows")
def import_rows(body: ImportRowsIn, user=Depends(user_from_header)):
    tid=user["tenant_id"]; count=0; errors=[]
    # Import is row-by-row and tenant-scoped. A malformed row is reported without exposing server internals.
    for idx,row in enumerate(body.rows, start=2):
        try:
            if body.dataset=="invoices":
                x=InvoiceIn(**row)
                with db() as c: _insert_invoice(c,tid,x)
            elif body.dataset=="expenses":
                # Keep legacy CSV import tolerant of title/description and planned/pending aliases.
                title=str(row.get("title") or row.get("description") or "").strip()
                category=str(row.get("category") or "عمومی").strip()[:100]
                amount=float(row.get("amount"))
                due_date=str(row.get("due_date") or "").strip()
                status=str(row.get("status") or "pending").strip()
                if not title or len(title)>180: raise ValueError("عنوان هزینه الزامی است.")
                if amount<=0 or amount>1_000_000_000_000: raise ValueError("مبلغ هزینه نامعتبر است.")
                if not _date_ok(due_date): raise ValueError("تاریخ سررسید نامعتبر است.")
                if status not in ("pending","paid","planned"): raise ValueError("وضعیت هزینه نامعتبر است.")
                with db() as c: c.execute("INSERT INTO expenses(tenant_id,title,category,amount,due_date,status) VALUES(?,?,?,?,?,?)",(tid,title,category,amount,due_date,"pending" if status=="planned" else status))
            elif body.dataset=="opportunities":
                x=OpportunityIn(**row)
                if x.customer_id is not None:
                    with db() as c:
                        if not c.execute("SELECT 1 FROM customers WHERE id=? AND tenant_id=?",(x.customer_id,tid)).fetchone():
                            raise HTTPException(422,"مشتری متعلق به این شرکت نیست.")
                if x.expected_close_date and not _date_ok(x.expected_close_date):
                    raise HTTPException(422,"تاریخ بستن فرصت معتبر نیست.")
                if x.last_contact_date and not _date_ok(x.last_contact_date):
                    raise HTTPException(422,"تاریخ آخرین تماس معتبر نیست.")
                with db() as c: c.execute("INSERT INTO opportunities(tenant_id,title,customer_id,source,stage,estimated_value,expected_close_date,last_contact_date,lost_reason) VALUES(?,?,?,?,?,?,?,?,?)",(tid,x.title.strip(),x.customer_id,x.source,x.stage,x.estimated_value,x.expected_close_date,x.last_contact_date,x.lost_reason))
            else:
                x=CampaignIn(**row)
                if (x.start_date and not _date_ok(x.start_date)) or (x.end_date and not _date_ok(x.end_date)):
                    raise HTTPException(422,"تاریخ شروع یا پایان کمپین معتبر نیست.")
                if x.start_date and x.end_date and x.end_date < x.start_date:
                    raise HTTPException(422,"تاریخ پایان کمپین نباید قبل از شروع باشد.")
                with db() as c: c.execute("INSERT INTO campaigns(tenant_id,name,channel,spend,leads,conversions,revenue,start_date,end_date) VALUES(?,?,?,?,?,?,?,?,?)",(tid,x.name.strip(),x.channel,x.spend,x.leads,x.conversions,x.revenue,x.start_date,x.end_date))
            count+=1
        except Exception as exc:
            detail=exc.detail if isinstance(exc,HTTPException) else (str(exc) if isinstance(exc,ValueError) else "مقادیر یا ساختار ردیف معتبر نیست.")
            errors.append({"row":idx,"error":str(detail)[:240]})
    with db() as c: c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,f"data.import.{body.dataset}:{count}/{len(body.rows)}"))
    return {"dataset":body.dataset,"imported":count,"rejected":len(errors),"errors":errors[:100],"message":f"{count} ردیف وارد شد؛ {len(errors)} ردیف نیازمند اصلاح است."}


app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")


# LEADORA multi-business intelligence foundation (v0.5.0)
# Rule-based, tenant-scoped operations; no sensitive external actions are executed automatically.
with db() as c:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS invoices(
      id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
      customer_id INTEGER, invoice_number TEXT NOT NULL, issue_date TEXT NOT NULL,
      due_date TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>0),
      status TEXT NOT NULL DEFAULT 'open', note TEXT NOT NULL DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(tenant_id,invoice_number));
    CREATE TABLE IF NOT EXISTS payments(
      id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
      invoice_id INTEGER NOT NULL, amount REAL NOT NULL CHECK(amount>0),
      paid_at TEXT NOT NULL, method TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS expenses(
      id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
      category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
      amount REAL NOT NULL CHECK(amount>0), due_date TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'planned', vendor TEXT NOT NULL DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS opportunities(
      id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
      customer_id INTEGER, title TEXT NOT NULL, source TEXT NOT NULL DEFAULT '',
      stage TEXT NOT NULL DEFAULT 'lead', estimated_value REAL NOT NULL DEFAULT 0 CHECK(estimated_value>=0),
      expected_close_date TEXT NOT NULL DEFAULT '', last_contact_at TEXT NOT NULL DEFAULT '',
      lost_reason TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS agent_actions(
      id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
      agent TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'info', title TEXT NOT NULL,
      explanation TEXT NOT NULL, recommendation TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'open', approval_required INTEGER NOT NULL DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT);
    CREATE INDEX IF NOT EXISTS idx_invoices_tenant_due ON invoices(tenant_id,due_date);
    CREATE INDEX IF NOT EXISTS idx_expenses_tenant_due ON expenses(tenant_id,due_date);
    CREATE INDEX IF NOT EXISTS idx_opportunities_tenant_stage ON opportunities(tenant_id,stage);
    """)

class InvoiceIn(BaseModel):
    customer_id: int | None = None
    invoice_number: str = Field(min_length=1,max_length=80)
    issue_date: str = Field(min_length=10,max_length=10)
    due_date: str = Field(min_length=10,max_length=10)
    amount: float = Field(gt=0,le=1_000_000_000_000)
    note: str = Field(default="",max_length=1000)

class PaymentIn(BaseModel):
    amount: float = Field(gt=0,le=1_000_000_000_000)
    paid_at: str = Field(min_length=10,max_length=10)
    method: str = Field(default="",max_length=80)
    reference: str = Field(default="",max_length=120)

class ExpenseIn(BaseModel):
    category: str = Field(min_length=1,max_length=100)
    description: str = Field(default="",max_length=300)
    amount: float = Field(gt=0,le=1_000_000_000_000)
    due_date: str = Field(min_length=10,max_length=10)
    status: str = Field(default="planned",pattern="^(planned|paid|cancelled)$")
    vendor: str = Field(default="",max_length=180)

class OpportunityIn(BaseModel):
    customer_id: int | None = None
    title: str = Field(min_length=1,max_length=180)
    source: str = Field(default="",max_length=100)
    stage: str = Field(default="lead",pattern="^(lead|qualified|proposal|negotiation|won|lost)$")
    estimated_value: float = Field(default=0,ge=0,le=1_000_000_000_000)
    expected_close_date: str = Field(default="",max_length=10)
    last_contact_at: str = Field(default="",max_length=10)
    lost_reason: str = Field(default="",max_length=500)

def _date_ok(value):
    try:
        from datetime import date
        date.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False

def _paid_by_invoice(c, tenant_id):
    return {r["invoice_id"]: r["paid"] for r in c.execute(
        "SELECT invoice_id,COALESCE(SUM(amount),0) AS paid FROM payments WHERE tenant_id=? GROUP BY invoice_id",
        (tenant_id,)).fetchall()}

@app.post("/api/invoices/{invoice_id}/payments")
def add_payment(invoice_id: int, body: PaymentIn, user=Depends(user_from_header)):
    if not _date_ok(body.paid_at): raise HTTPException(422,"تاریخ پرداخت معتبر نیست.")
    tid=user["tenant_id"]
    with db() as c:
        inv=c.execute("SELECT amount FROM invoices WHERE id=? AND tenant_id=?",(invoice_id,tid)).fetchone()
        if not inv: raise HTTPException(404,"فاکتور یافت نشد.")
        paid=c.execute("SELECT COALESCE(SUM(amount),0) AS total FROM payments WHERE invoice_id=? AND tenant_id=?",(invoice_id,tid)).fetchone()["total"]
        if body.amount > inv["amount"]-paid+0.000001: raise HTTPException(422,"مبلغ پرداخت از مانده فاکتور بیشتر است.")
        cur=c.execute("INSERT INTO payments(tenant_id,invoice_id,amount,paid_at,method,reference) VALUES(?,?,?,?,?,?)",
          (tid,invoice_id,body.amount,body.paid_at,body.method.strip(),body.reference.strip()))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"invoice.payment_recorded"))
    return {"id":cur.lastrowid,"message":"پرداخت ثبت شد."}

@app.get("/api/agents/actions")
def list_agent_actions(user=Depends(user_from_header)):
    with db() as c:
        rows=c.execute("SELECT id,agent,severity,title,rationale,recommendation,status,sensitive,created_at FROM agent_actions WHERE tenant_id=? ORDER BY id DESC LIMIT 200",(user["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/agents/actions/{action_id}/resolve")
def resolve_agent_action(action_id: int, user=Depends(user_from_header)):
    tid=user["tenant_id"]
    with db() as c:
        cur=c.execute("UPDATE agent_actions SET status='done' WHERE id=? AND tenant_id=? AND status='approved'",(action_id,tid))
        if not cur.rowcount: raise HTTPException(409,"فقط اقدام تأییدشده و متعلق به این شرکت قابل تکمیل است.")
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"agent_action.done"))
    return {"message":"اقدام تأییدشده تکمیل شد."}

@app.get("/api/import/template/{dataset}.csv")
def import_template(dataset: str, user=Depends(user_from_header)):
    templates={
      "invoices":["invoice_number","customer_id","issue_date","due_date","amount","note"],
      "expenses":["title","category","amount","due_date","status"],
      "opportunities":["title","customer_id","source","stage","estimated_value","expected_close_date","last_contact_date","lost_reason"],
      "campaigns":["name","channel","spend","leads","conversions","revenue","start_date","end_date"]
    }
    if dataset not in templates: raise HTTPException(404,"قالب برای این نوع داده وجود ندارد.")
    stream=io.StringIO(newline=""); csv.writer(stream).writerow(templates[dataset])
    return StreamingResponse(iter(["\\ufeff"+stream.getvalue()]),media_type="text/csv; charset=utf-8",
      headers={"Content-Disposition":f'attachment; filename="leadora-{dataset}-template.csv"',"Cache-Control":"no-store"})


# Location-aware customer discovery and durable storage/backup services.
import urllib.request
import urllib.error
from datetime import datetime, timezone

PROSPECTING_TABLES = """
CREATE TABLE IF NOT EXISTS prospecting_runs(
 id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
 latitude REAL NOT NULL, longitude REAL NOT NULL, radius_m INTEGER NOT NULL,
 category TEXT NOT NULL DEFAULT 'all', result_count INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL, error_message TEXT NOT NULL DEFAULT '',
 created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS prospect_leads(
 id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
 osm_type TEXT NOT NULL, osm_id TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
 category TEXT NOT NULL DEFAULT 'other', subcategory TEXT NOT NULL DEFAULT '',
 phone TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '',
 street TEXT NOT NULL DEFAULT '', neighbourhood TEXT NOT NULL DEFAULT '',
 suburb TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
 region TEXT NOT NULL DEFAULT '', postcode TEXT NOT NULL DEFAULT '',
 latitude REAL NOT NULL, longitude REAL NOT NULL, address TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL DEFAULT 'OpenStreetMap', source_url TEXT NOT NULL DEFAULT '',
 tags_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'new',
 first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP, last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(tenant_id,osm_type,osm_id)
);
CREATE INDEX IF NOT EXISTS idx_prospect_leads_geo ON prospect_leads(tenant_id,city,neighbourhood,category);
CREATE INDEX IF NOT EXISTS idx_prospect_leads_status ON prospect_leads(tenant_id,status);
"""
with db() as c:
    c.executescript(PROSPECTING_TABLES)

class ProspectSearchIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=1000, ge=100, le=25000)
    category: str = Field(default="all", pattern="^(all|shop|office|food|health|service|tourism|craft)$")
    limit: int = Field(default=100, ge=1, le=500)

class ProspectStatusIn(BaseModel):
    status: str = Field(pattern="^(new|contacted|qualified|not_a_fit|customer)$")

def _prospect_category(tags):
    if tags.get("shop"): return ("shop", tags["shop"])
    if tags.get("office"): return ("office", tags["office"])
    if tags.get("amenity") in ("restaurant","cafe","fast_food","bar","pub"): return ("food", tags["amenity"])
    if tags.get("amenity") in ("doctors","clinic","dentist","pharmacy","hospital","veterinary"): return ("health", tags["amenity"])
    if tags.get("tourism"): return ("tourism", tags["tourism"])
    if tags.get("craft"): return ("craft", tags["craft"])
    return ("service", tags.get("amenity") or tags.get("building") or tags.get("industrial") or "business")

def _overpass_query(lat, lon, radius, category):
    filters = {
      "shop": ['["shop"]'], "office": ['["office"]'],
      "food": ['["amenity"~"restaurant|cafe|fast_food|bar|pub"]'],
      "health": ['["amenity"~"doctors|clinic|dentist|pharmacy|hospital|veterinary"]'],
      "service": ['["craft"]'], "tourism": ['["tourism"]'], "craft": ['["craft"]'],
      "all": ['["shop"]','["office"]','["craft"]','["tourism"]','["amenity"~"restaurant|cafe|fast_food|bar|pub|doctors|clinic|dentist|pharmacy|hospital|veterinary|bank|car_repair|fuel|post_office|school|university"]']
    }
    statements = []
    for f in filters[category]:
        statements.extend([f"node{f}(around:{radius},{lat},{lon});",
                           f"way{f}(around:{radius},{lat},{lon});",
                           f"relation{f}(around:{radius},{lat},{lon});"])
    return "[out:json][timeout:20];(" + "".join(statements) + ");out center tags;"

def _tag_text(tags, *keys):
    return next((str(tags.get(k,"")).strip() for k in keys if str(tags.get(k,"")).strip()), "")

def _normalize_osm_element(element):
    tags=element.get("tags") or {}
    center=element.get("center") or {}
    lat=element.get("lat",center.get("lat")); lon=element.get("lon",center.get("lon"))
    if lat is None or lon is None: return None
    name=_tag_text(tags,"name","brand","operator")
    if not name: return None
    category,subcat=_prospect_category(tags)
    street=" ".join(x for x in (_tag_text(tags,"addr:street"),_tag_text(tags,"addr:housenumber")) if x)
    parts=[street,_tag_text(tags,"addr:neighbourhood"),_tag_text(tags,"addr:suburb"),_tag_text(tags,"addr:city","addr:town","addr:village"),_tag_text(tags,"addr:state")]
    address=", ".join(x for x in (street,_tag_text(tags,"addr:neighbourhood"),_tag_text(tags,"addr:suburb"),_tag_text(tags,"addr:city","addr:town","addr:village"),_tag_text(tags,"addr:state")) if x)
    typ=str(element.get("type","")); oid=str(element.get("id",""))
    return {"osm_type":typ,"osm_id":oid,"name":name[:180],"category":category,"subcategory":str(subcat)[:100],
      "phone":_tag_text(tags,"contact:phone","phone","contact:mobile")[:100],
      "website":_tag_text(tags,"contact:website","website")[:500],
      "street":street[:180],"neighbourhood":_tag_text(tags,"addr:neighbourhood")[:180],
      "suburb":_tag_text(tags,"addr:suburb","addr:district")[:180],
      "city":_tag_text(tags,"addr:city","addr:town","addr:village","addr:municipality")[:180],
      "region":_tag_text(tags,"addr:state","is_in:state")[:180],"postcode":_tag_text(tags,"addr:postcode")[:30],
      "latitude":float(lat),"longitude":float(lon),"address":address[:500],
      "source_url":f"https://www.openstreetmap.org/{typ}/{oid}" if typ and oid else "",
      "tags_json":json.dumps(tags,ensure_ascii=False)[:8000]}

@app.post("/api/prospecting/search")
def prospecting_search(body: ProspectSearchIn, user=Depends(user_from_header)):
    # This external search is explicit and location is obtained only after the browser asks the user for permission.
    query=_overpass_query(body.latitude,body.longitude,body.radius_m,body.category)
    req=urllib.request.Request("https://overpass-api.de/api/interpreter",data=query.encode("utf-8"),
        headers={"Content-Type":"text/plain; charset=utf-8","User-Agent":"LEADORA/0.6 (location-based business discovery)"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            payload=json.loads(response.read(8_000_000).decode("utf-8"))
        elements=payload.get("elements",[])[:body.limit]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        with db() as conn:
            conn.execute("INSERT INTO prospecting_runs(tenant_id,latitude,longitude,radius_m,category,status,error_message) VALUES(?,?,?,?,?,?,?)",
              (user["tenant_id"],body.latitude,body.longitude,body.radius_m,body.category,"failed",str(exc)[:240]))
        raise HTTPException(502,"منبع نقشه در دسترس نیست. اطلاعات قبلی حفظ شده؛ کمی بعد دوباره تلاش کنید.")
    tid=user["tenant_id"]; saved=0; results=[]
    with db() as conn:
        for element in elements:
            item=_normalize_osm_element(element)
            if not item: continue
            conn.execute("""INSERT INTO prospect_leads(tenant_id,osm_type,osm_id,name,category,subcategory,phone,website,street,neighbourhood,suburb,city,region,postcode,latitude,longitude,address,source,source_url,tags_json,status,last_seen_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'OpenStreetMap',?,?, 'new',CURRENT_TIMESTAMP)
              ON CONFLICT(tenant_id,osm_type,osm_id) DO UPDATE SET name=excluded.name,category=excluded.category,subcategory=excluded.subcategory,
              phone=CASE WHEN excluded.phone<>'' THEN excluded.phone ELSE prospect_leads.phone END,
              website=CASE WHEN excluded.website<>'' THEN excluded.website ELSE prospect_leads.website END,
              street=CASE WHEN excluded.street<>'' THEN excluded.street ELSE prospect_leads.street END,
              neighbourhood=CASE WHEN excluded.neighbourhood<>'' THEN excluded.neighbourhood ELSE prospect_leads.neighbourhood END,
              suburb=CASE WHEN excluded.suburb<>'' THEN excluded.suburb ELSE prospect_leads.suburb END,
              city=CASE WHEN excluded.city<>'' THEN excluded.city ELSE prospect_leads.city END,
              region=CASE WHEN excluded.region<>'' THEN excluded.region ELSE prospect_leads.region END,
              postcode=CASE WHEN excluded.postcode<>'' THEN excluded.postcode ELSE prospect_leads.postcode END,
              latitude=excluded.latitude,longitude=excluded.longitude,address=CASE WHEN excluded.address<>'' THEN excluded.address ELSE prospect_leads.address END,
              tags_json=excluded.tags_json,last_seen_at=CURRENT_TIMESTAMP""",
              (tid,item["osm_type"],item["osm_id"],item["name"],item["category"],item["subcategory"],item["phone"],item["website"],item["street"],item["neighbourhood"],item["suburb"],item["city"],item["region"],item["postcode"],item["latitude"],item["longitude"],item["address"],item["source_url"],item["tags_json"]))
            # Keep manual map searches and scheduled discovery in the same unified lead registry.
            source_record_id=f'{item["osm_type"]}/{item["osm_id"]}'
            fingerprint=_lead_fingerprint(item["name"],item["phone"],item["website"],item["city"],item["address"])
            conn.execute("""INSERT INTO business_leads
              (tenant_id,source,source_record_id,name,category,phone,website,address,city,region,latitude,longitude,source_url,fingerprint)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(tenant_id,fingerprint) DO UPDATE SET source=excluded.source,
                source_record_id=excluded.source_record_id,
                category=excluded.category,
                phone=CASE WHEN excluded.phone!='' THEN excluded.phone ELSE business_leads.phone END,
                website=CASE WHEN excluded.website!='' THEN excluded.website ELSE business_leads.website END,
                address=CASE WHEN excluded.address!='' THEN excluded.address ELSE business_leads.address END,
                city=CASE WHEN excluded.city!='' THEN excluded.city ELSE business_leads.city END,
                region=CASE WHEN excluded.region!='' THEN excluded.region ELSE business_leads.region END,
                latitude=COALESCE(excluded.latitude,business_leads.latitude),
                longitude=COALESCE(excluded.longitude,business_leads.longitude),
                source_url=excluded.source_url,last_seen_at=CURRENT_TIMESTAMP""",
              (tid,"OpenStreetMap",source_record_id,item["name"],item["category"],item["phone"],item["website"],item["address"],item["city"],item["region"],item["latitude"],item["longitude"],item["source_url"],fingerprint))
            saved+=1
            results.append(item)
        conn.execute("INSERT INTO prospecting_runs(tenant_id,latitude,longitude,radius_m,category,result_count,status) VALUES(?,?,?,?,?,?,?)",
          (tid,body.latitude,body.longitude,body.radius_m,body.category,saved,"success"))
        conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,f"prospecting.search:{body.radius_m}m:{saved}"))
    return {"status":"ok","source":"OpenStreetMap","radius_m":body.radius_m,"found":saved,
      "saved":saved,"coverage":"نتایج موجود در داده‌های نقشه عمومی؛ کامل بودن اطلاعات تضمین نیست.",
      "results":[{"name":x["name"],"category":x["category"],"subcategory":x["subcategory"],"phone":x["phone"],"website":x["website"],"street":x["street"],"neighbourhood":x["neighbourhood"],"suburb":x["suburb"],"city":x["city"],"region":x["region"],"address":x["address"],"latitude":x["latitude"],"longitude":x["longitude"],"source_url":x["source_url"]} for x in results]}

@app.get("/api/prospecting/leads")
def prospecting_leads(category: str = "all", area: str = "", status: str = "all", limit: int = 200, user=Depends(user_from_header)):
    if category not in ("all","shop","office","food","health","service","tourism","craft"): raise HTTPException(422,"دسته‌بندی نامعتبر است.")
    if status not in ("all","new","contacted","qualified","not_a_fit","customer"): raise HTTPException(422,"وضعیت نامعتبر است.")
    limit=max(1,min(limit,500))
    sql="SELECT id,name,category,subcategory,phone,website,street,neighbourhood,suburb,city,region,postcode,latitude,longitude,address,source,source_url,status,first_seen_at,last_seen_at FROM prospect_leads WHERE tenant_id=?"
    args=[user["tenant_id"]]
    if category!="all": sql+=" AND category=?"; args.append(category)
    if status!="all": sql+=" AND status=?"; args.append(status)
    if area.strip():
        sql+=" AND (street LIKE ? OR neighbourhood LIKE ? OR suburb LIKE ? OR city LIKE ? OR region LIKE ? OR address LIKE ?)"
        args.extend(["%"+area.strip()+"%"]*6)
    sql+=" ORDER BY city,neighbourhood,street,name LIMIT ?"; args.append(limit)
    with db() as conn: rows=conn.execute(sql,args).fetchall()
    return [dict(row) for row in rows]

@app.patch("/api/prospecting/leads/{lead_id}")
def update_prospect_status(lead_id:int, body:ProspectStatusIn, user=Depends(user_from_header)):
    with db() as conn:
        cur=conn.execute("UPDATE prospect_leads SET status=? WHERE id=? AND tenant_id=?",(body.status,lead_id,user["tenant_id"]))
        if cur.rowcount==0: raise HTTPException(404,"سرنخ مشتری یافت نشد.")
        conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],f"prospect.status:{body.status}"))
    return {"message":"وضعیت سرنخ ذخیره شد.","status":body.status}

@app.get("/api/prospecting/summary")
def prospecting_summary(user=Depends(user_from_header)):
    with db() as conn:
        total=conn.execute("SELECT COUNT(*) n FROM prospect_leads WHERE tenant_id=?",(user["tenant_id"],)).fetchone()["n"]
        cats=conn.execute("SELECT category,COUNT(*) count FROM prospect_leads WHERE tenant_id=? GROUP BY category ORDER BY count DESC",(user["tenant_id"],)).fetchall()
        areas=conn.execute("""SELECT COALESCE(NULLIF(neighbourhood,''),NULLIF(suburb,''),NULLIF(city,''),NULLIF(region,''),'محدوده نامشخص') area,COUNT(*) count FROM prospect_leads WHERE tenant_id=? GROUP BY area ORDER BY count DESC LIMIT 100""",(user["tenant_id"],)).fetchall()
        latest=conn.execute("SELECT created_at,status,radius_m,result_count FROM prospecting_runs WHERE tenant_id=? ORDER BY id DESC LIMIT 1",(user["tenant_id"],)).fetchone()
    return {"total":total,"categories":[dict(x) for x in cats],"areas":[dict(x) for x in areas],"last_run":dict(latest) if latest else None}

def _tenant_backup_payload(tenant_id):
    # Snapshot all tenant business data; never include user password hashes or auth tokens.
    table_columns={
      "products":"id,sku,name,price,stock","customers":"id,name,phone",
      "invoices":"id,customer_id,invoice_number,issue_date,due_date,amount,note,created_at",
      "payments":"id,invoice_id,paid_at,amount,method,reference",
      "expenses":"id,title,category,amount,due_date,status,created_at",
      "opportunities":"id,title,customer_id,source,stage,estimated_value,expected_close_date,last_contact_date,lost_reason,created_at",
      "campaigns":"id,name,channel,spend,leads,conversions,revenue,start_date,end_date",
      "agent_actions":"id,agent,severity,title,rationale,recommendation,status,sensitive,created_at",
      "prospect_leads":"id,osm_type,osm_id,name,category,subcategory,phone,website,street,neighbourhood,suburb,city,region,postcode,latitude,longitude,address,source,source_url,tags_json,status,first_seen_at,last_seen_at",
      "prospecting_runs":"id,latitude,longitude,radius_m,category,result_count,status,error_message,created_at",
      "audit_log":"id,action,created_at"
    }
    payload={"format":"leadora-tenant-backup-v2","created_at":datetime.now(timezone.utc).isoformat(),"tables":{}}
    with db() as conn:
        tenant=conn.execute("SELECT id,name,industry FROM tenants WHERE id=?",(tenant_id,)).fetchone()
        payload["tenant"]=dict(tenant) if tenant else None
        for table,cols in table_columns.items():
            try:
                rows=conn.execute(f"SELECT {cols} FROM {table} WHERE tenant_id=? ORDER BY id",(tenant_id,)).fetchall()
                payload["tables"][table]=[dict(x) for x in rows]
            except sqlite3.OperationalError:
                payload["tables"][table]=[]
    return payload

@app.get("/api/backup/full.json")
def full_tenant_backup(user=Depends(user_from_header)):
    payload=json.dumps(_tenant_backup_payload(user["tenant_id"]),ensure_ascii=False,indent=2)
    return StreamingResponse(iter([payload]),media_type="application/json; charset=utf-8",
      headers={"Content-Disposition":'attachment; filename="leadora-full-backup.json"',"Cache-Control":"no-store"})

@app.post("/api/backup/snapshot")
def create_backup_snapshot(user=Depends(user_from_header)):
    backup_dir=Path(os.getenv("LEADORA_BACKUP_DIR",str(ROOT.parent/"backups")))
    try:
        backup_dir.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target=backup_dir/f"leadora-tenant-{user['tenant_id']}-{stamp}.json"
        raw=json.dumps(_tenant_backup_payload(user["tenant_id"]),ensure_ascii=False,indent=2).encode("utf-8")
        # Exclusive creation avoids overwriting a previous backup if two requests arrive in the same second.
        with target.open("xb") as handle: handle.write(raw)
        with db() as conn: conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"backup.snapshot.created"))
        return {"status":"created","filename":target.name,"bytes":len(raw),"message":"نسخه پشتیبان روی دیسک سرور ذخیره شد."}
    except OSError:
        raise HTTPException(500,"ذخیره نسخه پشتیبان روی دیسک سرور ناموفق بود؛ فضای دیسک و مجوز پوشه را بررسی کنید.")

@app.get("/api/storage/status")
def storage_status(user=Depends(user_from_header)):
    p=Path(DB_PATH)
    try:
        with db() as conn:
            integrity=conn.execute("PRAGMA quick_check").fetchone()[0]
            counts={}
            for table in ("products","customers","invoices","payments","expenses","opportunities","campaigns","agent_actions","prospect_leads"):
                try: counts[table]=conn.execute(f"SELECT COUNT(*) n FROM {table} WHERE tenant_id=?",(user["tenant_id"],)).fetchone()["n"]
                except sqlite3.OperationalError: counts[table]=0
        return {"database":"sqlite","persistent_path_configured":bool(os.getenv("LEADORA_DB")),"database_bytes":p.stat().st_size if p.exists() else 0,
          "integrity":integrity,"records_by_table":counts,"backup_directory_configured":bool(os.getenv("LEADORA_BACKUP_DIR")),
          "backup_directory":os.getenv("LEADORA_BACKUP_DIR",str(ROOT.parent/"backups")),
          "note":"برای پایداری پس از راه‌اندازی مجدد، مسیر data و backups باید روی volume پایدار سرور نگاشت شوند؛ این endpoint وجود مسیر را تضمین نمی‌کند."}
    except sqlite3.Error:
        raise HTTPException(500,"بررسی وضعیت پایگاه داده ناموفق بود.")

# Unified order/invoice tracking with tenant-scoped status history.
from datetime import date, timedelta
with db() as conn:
 conn.executescript("""
 CREATE TABLE IF NOT EXISTS workflow_documents(
 id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),
 document_type TEXT NOT NULL CHECK(document_type IN ('order','invoice','purchase_order','sales_order')),
 document_number TEXT NOT NULL,title TEXT NOT NULL,
 party_role TEXT NOT NULL CHECK(party_role IN ('customer','supplier','vendor','our_company','other')),
 party_name TEXT NOT NULL,party_contact TEXT NOT NULL DEFAULT '',
 direction TEXT NOT NULL DEFAULT 'outgoing' CHECK(direction IN ('incoming','outgoing')),
 amount REAL NOT NULL DEFAULT 0 CHECK(amount>=0),currency TEXT NOT NULL DEFAULT 'IRR',
 issue_date TEXT NOT NULL DEFAULT '',due_date TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'registered',notes TEXT NOT NULL DEFAULT '',
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(tenant_id,document_type,document_number));
 CREATE INDEX IF NOT EXISTS idx_workflow_docs_status ON workflow_documents(tenant_id,status,due_date);
 CREATE TABLE IF NOT EXISTS workflow_events(
 id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),document_id INTEGER NOT NULL REFERENCES workflow_documents(id),
 old_status TEXT NOT NULL DEFAULT '',new_status TEXT NOT NULL,event_type TEXT NOT NULL DEFAULT 'status_change',
 note TEXT NOT NULL DEFAULT '',actor TEXT NOT NULL DEFAULT 'user',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE INDEX IF NOT EXISTS idx_workflow_events_doc ON workflow_events(tenant_id,document_id,id);
 """)
WORKFLOW_STATUSES={"registered":"ثبت اولیه","review":"در حال بررسی","approved":"تأیید شده","in_progress":"در حال انجام","sent":"ارسال شده","received":"دریافت شده","awaiting_customer":"در انتظار مشتری","awaiting_supplier":"در انتظار تأمین‌کننده","awaiting_payment":"در انتظار پرداخت","partially_paid":"پرداخت جزئی","paid":"تسویه شده","fulfilled":"تحویل/اجرا شده","completed":"بسته شده","on_hold":"متوقف موقت","cancelled":"لغو شده","overdue":"معوق"}
class WorkflowDocumentIn(BaseModel):
 document_type:str=Field(pattern="^(order|invoice|purchase_order|sales_order)$")
 document_number:str=Field(min_length=1,max_length=100)
 title:str=Field(min_length=1,max_length=200)
 party_role:str=Field(pattern="^(customer|supplier|vendor|our_company|other)$")
 party_name:str=Field(min_length=1,max_length=200)
 party_contact:str=Field(default="",max_length=200)
 direction:str=Field(default="outgoing",pattern="^(incoming|outgoing)$")
 amount:float=Field(default=0,ge=0,le=1000000000000)
 currency:str=Field(default="IRR",min_length=3,max_length=8)
 issue_date:str=Field(default="",max_length=10)
 due_date:str=Field(default="",max_length=10)
 status:str=Field(default="registered",pattern="^(registered|review|approved|in_progress|sent|received|awaiting_customer|awaiting_supplier|awaiting_payment|partially_paid|paid|fulfilled|completed|on_hold|cancelled|overdue)$")
 notes:str=Field(default="",max_length=2000)
class WorkflowStatusIn(BaseModel):
 status:str=Field(pattern="^(registered|review|approved|in_progress|sent|received|awaiting_customer|awaiting_supplier|awaiting_payment|partially_paid|paid|fulfilled|completed|on_hold|cancelled|overdue)$")
 note:str=Field(default="",max_length=2000)
class WorkflowEventIn(BaseModel):
 event_type:str=Field(default="note",pattern="^(note|call|email|meeting|payment|shipment|status_change|reminder)$")
 note:str=Field(min_length=1,max_length=2000)
def _workflow_doc(row):
 x=dict(row);x["status_label"]=WORKFLOW_STATUSES.get(x["status"],x["status"]);return x
@app.get("/api/workflow/statuses")
def workflow_statuses(user=Depends(user_from_header)): return [{"code":k,"label":v} for k,v in WORKFLOW_STATUSES.items()]
@app.post("/api/workflow/documents")
def create_workflow_document(body:WorkflowDocumentIn,user=Depends(user_from_header)):
 if not body.document_number.strip() or not body.party_name.strip(): raise HTTPException(422,"شماره سند و نام طرف معامله الزامی است.")
 if body.issue_date and not _date_ok(body.issue_date): raise HTTPException(422,"تاریخ صدور معتبر نیست.")
 if body.due_date and not _date_ok(body.due_date): raise HTTPException(422,"تاریخ سررسید معتبر نیست.")
 if body.issue_date and body.due_date and body.due_date<body.issue_date: raise HTTPException(422,"سررسید قبل از تاریخ صدور است.")
 with db() as conn:
  try:
   cur=conn.execute("INSERT INTO workflow_documents(tenant_id,document_type,document_number,title,party_role,party_name,party_contact,direction,amount,currency,issue_date,due_date,status,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(user["tenant_id"],body.document_type,body.document_number.strip(),body.title.strip(),body.party_role,body.party_name.strip(),body.party_contact.strip(),body.direction,body.amount,body.currency.upper(),body.issue_date,body.due_date,body.status,body.notes.strip()))
  except sqlite3.IntegrityError: raise HTTPException(409,"این شماره سند برای این نوع سند قبلاً ثبت شده است.")
  ident=cur.lastrowid
  conn.execute("INSERT INTO workflow_events(tenant_id,document_id,old_status,new_status,event_type,note) VALUES(?,?,?,?,?,?)",(user["tenant_id"],ident,"",body.status,"status_change","ثبت سند"))
  conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"workflow.document.created"))
  row=conn.execute("SELECT * FROM workflow_documents WHERE id=? AND tenant_id=?",(ident,user["tenant_id"])).fetchone()
 return _workflow_doc(row)
@app.get("/api/workflow/documents")
def list_workflow_documents(document_type:str="all",status:str="all",party_role:str="all",q:str="",limit:int=200,user=Depends(user_from_header)):
 if document_type not in ("all","order","invoice","purchase_order","sales_order"): raise HTTPException(422,"نوع سند نامعتبر است.")
 if status!="all" and status not in WORKFLOW_STATUSES: raise HTTPException(422,"وضعیت نامعتبر است.")
 if party_role not in ("all","customer","supplier","vendor","our_company","other"): raise HTTPException(422,"طرف معامله نامعتبر است.")
 sql="SELECT * FROM workflow_documents WHERE tenant_id=?";args=[user["tenant_id"]]
 for col,val in (("document_type",document_type),("status",status),("party_role",party_role)):
  if val!="all": sql+=f" AND {col}=?";args.append(val)
 if q.strip(): sql+=" AND (document_number LIKE ? OR title LIKE ? OR party_name LIKE ?)";args.extend(["%"+q.strip()+"%"]*3)
 sql+=" ORDER BY CASE WHEN due_date='' THEN '9999-12-31' ELSE due_date END,id DESC LIMIT ?";args.append(max(1,min(limit,500)))
 with db() as conn: rows=conn.execute(sql,args).fetchall()
 return [_workflow_doc(x) for x in rows]
@app.get("/api/workflow/documents/{document_id}")
def get_workflow_document(document_id:int,user=Depends(user_from_header)):
 with db() as conn:
  row=conn.execute("SELECT * FROM workflow_documents WHERE id=? AND tenant_id=?",(document_id,user["tenant_id"])).fetchone()
  if not row: raise HTTPException(404,"سند پیدا نشد.")
  events=conn.execute("SELECT id,old_status,new_status,event_type,note,actor,created_at FROM workflow_events WHERE document_id=? AND tenant_id=? ORDER BY id",(document_id,user["tenant_id"])).fetchall()
 return {"document":_workflow_doc(row),"timeline":[dict(x) for x in events]}
@app.patch("/api/workflow/documents/{document_id}/status")
def change_workflow_status(document_id:int,body:WorkflowStatusIn,user=Depends(user_from_header)):
 with db() as conn:
  row=conn.execute("SELECT status FROM workflow_documents WHERE id=? AND tenant_id=?",(document_id,user["tenant_id"])).fetchone()
  if not row: raise HTTPException(404,"سند پیدا نشد.")
  old=row["status"]
  conn.execute("UPDATE workflow_documents SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",(body.status,document_id,user["tenant_id"]))
  conn.execute("INSERT INTO workflow_events(tenant_id,document_id,old_status,new_status,event_type,note) VALUES(?,?,?,?,?,?)",(user["tenant_id"],document_id,old,body.status,"status_change",body.note.strip()))
  conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],f"workflow.status:{document_id}:{body.status}"))
  row=conn.execute("SELECT * FROM workflow_documents WHERE id=? AND tenant_id=?",(document_id,user["tenant_id"])).fetchone()
 return _workflow_doc(row)
@app.post("/api/workflow/documents/{document_id}/events")
def add_workflow_event(document_id:int,body:WorkflowEventIn,user=Depends(user_from_header)):
 with db() as conn:
  row=conn.execute("SELECT status FROM workflow_documents WHERE id=? AND tenant_id=?",(document_id,user["tenant_id"])).fetchone()
  if not row: raise HTTPException(404,"سند پیدا نشد.")
  conn.execute("INSERT INTO workflow_events(tenant_id,document_id,old_status,new_status,event_type,note) VALUES(?,?,?,?,?,?)",(user["tenant_id"],document_id,row["status"],row["status"],body.event_type,body.note.strip()))
  conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],f"workflow.event:{body.event_type}"))
 return {"message":"رویداد پیگیری ثبت شد.","document_id":document_id}
@app.get("/api/workflow/followups")
def workflow_followups(days:int=7,user=Depends(user_from_header)):
 days=max(0,min(days,365));today=date.today().isoformat();cutoff=(date.today()+timedelta(days=days)).isoformat()
 with db() as conn: rows=conn.execute("SELECT * FROM workflow_documents WHERE tenant_id=? AND status NOT IN ('completed','cancelled','paid','fulfilled') AND due_date<>'' AND due_date<=? ORDER BY due_date LIMIT 500",(user["tenant_id"],cutoff)).fetchall()
 items=[]
 for row in rows:
  x=_workflow_doc(row);x["overdue_days"]=max(0,(date.today()-date.fromisoformat(x["due_date"])).days);items.append(x)
 return {"count":len(items),"items":items,"as_of":today}


# LEADORA multi-source business lead registry.
# Source adapters may only be enabled for official/public/licensed data feeds.
def init_business_lead_registry():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS business_leads(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          source TEXT NOT NULL, source_record_id TEXT NOT NULL DEFAULT '',
          name TEXT NOT NULL, category TEXT NOT NULL DEFAULT '',
          phone TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '',
          address TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
          region TEXT NOT NULL DEFAULT '', latitude REAL, longitude REAL,
          source_url TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
          fingerprint TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new',
          first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tenant_id, fingerprint)
        );
        CREATE INDEX IF NOT EXISTS idx_business_leads_tenant_category
          ON business_leads(tenant_id, category, city, status);
        CREATE TABLE IF NOT EXISTS business_source_runs(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          source TEXT NOT NULL, status TEXT NOT NULL,
          imported INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL DEFAULT 0,
          rejected INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
init_business_lead_registry()

class BusinessLeadImportIn(BaseModel):
    source: str = Field(min_length=2, max_length=100)
    records: list[dict] = Field(min_length=1, max_length=2000)

def _lead_fingerprint(name, phone, website, city, address):
    # Normalize only business identifiers; do not treat name alone as globally unique.
    import unicodedata
    def norm(v):
        return " ".join(unicodedata.normalize("NFKC", str(v or "")).casefold().split())
    import hashlib
    identity = "|".join((norm(name), norm(phone), norm(website), norm(city), norm(address)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()

@app.get("/api/prospecting/sources")
def prospecting_sources(user=Depends(user_from_header)):
    # Availability means adapter status, not a claim of a live partnership or API connection.
    return {
      "sources": [
        {"id":"openstreetmap","name":"OpenStreetMap / Overpass","mode":"available_in_app","data":"Publicly mapped businesses and locations","limits":"Shared public service; suitable only for modest, rate-limited queries"},
        {"id":"balad","name":"بلد","mode":"requires_official_access","data":"Potential business listings where the provider permits use","limits":"Official API, commercial permission, or an authorized export required"},
        {"id":"neshan","name":"نشان","mode":"requires_official_access","data":"Potential business listings where the provider permits use","limits":"Official API, commercial permission, or an authorized export required"},
        {"id":"snapp","name":"اسنپ","mode":"requires_official_access","data":"Only public business information explicitly available for this purpose","limits":"No access to private customer, driver, merchant, or internal datasets"},
        {"id":"licensed_directory","name":"Licensed directories / association lists","mode":"manual_or_api_import","data":"Company and trade-directory records covered by the applicable license","limits":"Record source and permitted purpose must be retained"}
      ],
      "note":"No source is represented as connected unless an authorized connector is configured and verified."
    }

@app.post("/api/prospecting/import")
def import_business_leads(body: BusinessLeadImportIn, user=Depends(user_from_header)):
    tid = user["tenant_id"]
    source = body.source.strip()[:100]
    imported = updated = rejected = 0
    with db() as c:
        for row in body.records:
            try:
                name = str(row.get("name") or row.get("company") or row.get("business_name") or "").strip()[:180]
                if not name:
                    rejected += 1
                    continue
                phone = str(row.get("phone") or row.get("telephone") or row.get("contact_phone") or "").strip()[:100]
                website = str(row.get("website") or row.get("url") or "").strip()[:500]
                if website and not re.match(r"^https?://", website, re.I):
                    rejected += 1
                    continue
                address = str(row.get("address") or row.get("street_address") or "").strip()[:500]
                city = str(row.get("city") or row.get("town") or "").strip()[:180]
                region = str(row.get("region") or row.get("state") or "").strip()[:180]
                category = str(row.get("category") or row.get("industry") or row.get("type") or "").strip()[:100]
                source_record_id = str(row.get("source_record_id") or row.get("external_id") or row.get("id") or "").strip()[:180]
                source_url = str(row.get("source_url") or row.get("profile_url") or "").strip()[:1000]
                if source_url and not re.match(r"^https?://", source_url, re.I):
                    rejected += 1
                    continue
                lat = row.get("latitude", row.get("lat"))
                lon = row.get("longitude", row.get("lon", row.get("lng")))
                try:
                    lat = float(lat) if lat not in (None, "") else None
                    lon = float(lon) if lon not in (None, "") else None
                    if lat is not None and not -90 <= lat <= 90: raise ValueError()
                    if lon is not None and not -180 <= lon <= 180: raise ValueError()
                    if (lat is None) != (lon is None): raise ValueError()
                except (TypeError, ValueError):
                    rejected += 1
                    continue
                fingerprint = _lead_fingerprint(name, phone, website, city, address)
                existing = c.execute("SELECT id FROM business_leads WHERE tenant_id=? AND fingerprint=?", (tid, fingerprint)).fetchone()
                c.execute("""INSERT INTO business_leads
                  (tenant_id,source,source_record_id,name,category,phone,website,address,city,region,latitude,longitude,source_url,fingerprint)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(tenant_id,fingerprint) DO UPDATE SET
                    source=excluded.source,
                    source_record_id=CASE WHEN excluded.source_record_id!='' THEN excluded.source_record_id ELSE business_leads.source_record_id END,
                    category=CASE WHEN excluded.category!='' THEN excluded.category ELSE business_leads.category END,
                    phone=CASE WHEN excluded.phone!='' THEN excluded.phone ELSE business_leads.phone END,
                    website=CASE WHEN excluded.website!='' THEN excluded.website ELSE business_leads.website END,
                    address=CASE WHEN excluded.address!='' THEN excluded.address ELSE business_leads.address END,
                    city=CASE WHEN excluded.city!='' THEN excluded.city ELSE business_leads.city END,
                    region=CASE WHEN excluded.region!='' THEN excluded.region ELSE business_leads.region END,
                    latitude=COALESCE(excluded.latitude,business_leads.latitude),
                    longitude=COALESCE(excluded.longitude,business_leads.longitude),
                    source_url=CASE WHEN excluded.source_url!='' THEN excluded.source_url ELSE business_leads.source_url END,
                    last_seen_at=CURRENT_TIMESTAMP""",
                  (tid,source,source_record_id,name,category,phone,website,address,city,region,lat,lon,source_url,fingerprint))
                if existing: updated += 1
                else: imported += 1
            except (sqlite3.Error, TypeError, ValueError):
                rejected += 1
        c.execute("INSERT INTO business_source_runs(tenant_id,source,status,imported,updated,rejected,message) VALUES(?,?,?,?,?,?,?)",
          (tid,source,"completed" if rejected == 0 else "completed_with_rejections",imported,updated,rejected,
           "Rows deduplicated by normalized business identifiers; source provenance retained."))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"business_leads.imported"))
    return {"source":source,"imported":imported,"updated":updated,"rejected":rejected,
            "received":len(body.records),"message":"داده‌های مجاز پردازش شد؛ رکوردهای تکراری به‌روزرسانی شدند."}

@app.get("/api/prospecting/business-leads")
def list_business_leads(q: str = "", category: str = "", city: str = "", status: str = "new",
                        limit: int = 100, offset: int = 0, user=Depends(user_from_header)):
    limit = max(1, min(limit, 500)); offset = max(0, offset)
    tid = user["tenant_id"]
    clauses = ["tenant_id=?"]; args = [tid]
    if q.strip():
        clauses.append("(name LIKE ? OR phone LIKE ? OR website LIKE ? OR address LIKE ?)")
        term = "%" + q.strip()[:100] + "%"
        args.extend([term,term,term,term])
    if category.strip(): clauses.append("category=?"); args.append(category.strip()[:100])
    if city.strip(): clauses.append("city LIKE ?"); args.append("%" + city.strip()[:100] + "%")
    if status in ("new","contacted","qualified","converted","discarded"):
        clauses.append("status=?"); args.append(status)
    where = " AND ".join(clauses)
    with db() as c:
        total = c.execute("SELECT COUNT(*) n FROM business_leads WHERE " + where, args).fetchone()["n"]
        rows = c.execute("SELECT id,source,source_record_id,name,category,phone,website,address,city,region,latitude,longitude,source_url,status,first_seen_at,last_seen_at FROM business_leads WHERE " + where + " ORDER BY last_seen_at DESC LIMIT ? OFFSET ?", args + [limit,offset]).fetchall()
    return {"total":total,"limit":limit,"offset":offset,"items":[dict(r) for r in rows]}

@app.get("/api/prospecting/source-runs")
def list_business_source_runs(limit: int = 100, user=Depends(user_from_header)):
    limit = max(1, min(limit, 500))
    with db() as c:
        rows = c.execute("SELECT id,source,status,imported,updated,rejected,message,created_at FROM business_source_runs WHERE tenant_id=? ORDER BY id DESC LIMIT ?",(user["tenant_id"],limit)).fetchall()
    return [dict(r) for r in rows]


# Persistent, tenant-scoped settings for scheduled business discovery.
def init_scheduled_prospecting():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS prospecting_settings(
          tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id),
          latitude REAL NOT NULL, longitude REAL NOT NULL,
          radius_m INTEGER NOT NULL DEFAULT 1000,
          category TEXT NOT NULL DEFAULT 'all',
          enabled INTEGER NOT NULL DEFAULT 0,
          interval_seconds INTEGER NOT NULL DEFAULT 3600,
          next_run_at REAL NOT NULL DEFAULT 0,
          last_attempt_at TEXT NOT NULL DEFAULT '',
          last_success_at TEXT NOT NULL DEFAULT '',
          last_error TEXT NOT NULL DEFAULT '',
          consecutive_failures INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS prospecting_worker_events(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
          event_type TEXT NOT NULL, message TEXT NOT NULL DEFAULT '',
          found INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_prospecting_settings_due
          ON prospecting_settings(enabled,next_run_at);
        CREATE TABLE IF NOT EXISTS prospecting_worker_lease(
          id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT NOT NULL DEFAULT '',
          lease_until REAL NOT NULL DEFAULT 0, last_external_request_at REAL NOT NULL DEFAULT 0,
          heartbeat_at REAL NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO prospecting_worker_lease(id,owner,lease_until,last_external_request_at,heartbeat_at) VALUES(1,'',0,0,0);
        """)
init_scheduled_prospecting()

class ProspectingSettingsIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=1000, ge=100, le=25000)
    category: str = Field(default="all", pattern="^(all|shop|office|food|health|service|tourism|craft)$")
    enabled: bool = False
    interval_seconds: int = Field(default=3600, ge=900, le=86400)

@app.get("/api/prospecting/settings")
def get_prospecting_settings(user=Depends(user_from_header)):
    with db() as c:
        row=c.execute("SELECT latitude,longitude,radius_m,category,enabled,interval_seconds,last_attempt_at,last_success_at,last_error,consecutive_failures,next_run_at,updated_at FROM prospecting_settings WHERE tenant_id=?",(user["tenant_id"],)).fetchone()
    return dict(row) if row else {"configured":False,"enabled":False,"message":"ابتدا محدوده مشتری‌یابی را تنظیم کنید."}

@app.put("/api/prospecting/settings")
def put_prospecting_settings(body: ProspectingSettingsIn, user=Depends(user_from_header)):
    with db() as c:
        c.execute("""INSERT INTO prospecting_settings
          (tenant_id,latitude,longitude,radius_m,category,enabled,interval_seconds,next_run_at,last_error,consecutive_failures,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
          ON CONFLICT(tenant_id) DO UPDATE SET latitude=excluded.latitude,longitude=excluded.longitude,
          radius_m=excluded.radius_m,category=excluded.category,enabled=excluded.enabled,
          interval_seconds=excluded.interval_seconds,next_run_at=CASE WHEN excluded.enabled=1 THEN 0 ELSE excluded.next_run_at END,
          last_error='',consecutive_failures=0,updated_at=CURRENT_TIMESTAMP""",
          (user["tenant_id"],body.latitude,body.longitude,body.radius_m,body.category,int(body.enabled),body.interval_seconds,0,"",0))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"prospecting.settings.updated"))
        row=c.execute("SELECT latitude,longitude,radius_m,category,enabled,interval_seconds,next_run_at,updated_at FROM prospecting_settings WHERE tenant_id=?",(user["tenant_id"],)).fetchone()
    return {"configured":True,**dict(row),"message":"تنظیمات ذخیره شد؛ اجرای زمان‌بندی‌شده فقط روی سروری فعال است که worker آن اجرا شده باشد."}

@app.get("/api/prospecting/worker/status")
def prospecting_worker_status(user=Depends(user_from_header)):
    with db() as c:
        settings=c.execute("SELECT enabled,last_attempt_at,last_success_at,last_error,consecutive_failures,next_run_at,interval_seconds FROM prospecting_settings WHERE tenant_id=?",(user["tenant_id"],)).fetchone()
        events=c.execute("SELECT event_type,message,found,created_at FROM prospecting_worker_events WHERE tenant_id=? ORDER BY id DESC LIMIT 20",(user["tenant_id"],)).fetchall()
        lease=c.execute("SELECT heartbeat_at,owner FROM prospecting_worker_lease WHERE id=1").fetchone()
    import time as _time
    heartbeat=float(lease["heartbeat_at"] or 0) if lease else 0
    alive=bool(heartbeat and _time.time()-heartbeat < 90)
    return {"configured":settings is not None,"settings":dict(settings) if settings else None,"recent_events":[dict(x) for x in events],
            "worker_process":{"alive":alive,"last_heartbeat_epoch":heartbeat,"owner":lease["owner"] if lease else ""},
            "note":"Heartbeat confirms recent worker activity only; it does not guarantee upstream data-source availability."}

@app.get("/api/prospecting/business-leads/export.csv")
def export_business_leads(user=Depends(user_from_header)):
    with db() as c:
        rows=c.execute("SELECT source,source_record_id,name,category,phone,website,address,city,region,latitude,longitude,source_url,status,first_seen_at,last_seen_at FROM business_leads WHERE tenant_id=? ORDER BY name",(user["tenant_id"],)).fetchall()
    output=io.StringIO(newline="")
    fields=["source","source_record_id","name","category","phone","website","address","city","region","latitude","longitude","source_url","status","first_seen_at","last_seen_at"]
    writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader()
    for row in rows: writer.writerow(dict(row))
    return StreamingResponse(iter([output.getvalue()]),media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":"attachment; filename=leadora-business-leads.csv"})


# Financial participation API and responsive browser/PWA page.
from app.participation import create_router
app.include_router(create_router(db, user_from_header))
from app.distribution_erp import create_router as create_distribution_router
app.include_router(create_distribution_router(db, user_from_header))
from app.pricing_modules import create_router as create_pricing_router
app.include_router(create_pricing_router(db, user_from_header))
from app.ai_command_center import create_router as create_ai_command_center_router
app.include_router(create_ai_command_center_router(db, user_from_header))

@app.get("/distribution")
def distribution_page():
    return FileResponse(ROOT / "static" / "distribution.html")

@app.get("/finance")
def finance_page():
    return FileResponse(ROOT / "static" / "finance.html")

@app.get("/owner/pricing")
def owner_pricing_page():
    return FileResponse(ROOT / "static" / "owner-pricing.html")

@app.get("/plans")
def plans_page():
    return FileResponse(ROOT / "static" / "plans.html")

@app.get("/ai-command-center")
def ai_command_center_page():
    return FileResponse(ROOT / "static" / "ai-command-center.html")


# --- Product licensing and company-owned bank accounts ---
# Trial duration is server-controlled. No bank login credentials are accepted or stored.
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field

def _platform_owner(user):
    allowed = {part.strip() for part in os.getenv("LEADORA_OWNER_USER_IDS", "").split(",") if part.strip()}
    if str(user.get("id")) in allowed:
        return True
    # Reuse the existing, separately secured platform-owner claim instead of requiring a second owner setup.
    try:
        with db() as conn:
            row = conn.execute("SELECT user_id FROM finance_platform_owner WHERE singleton=1").fetchone()
        if row and str(row["user_id"]) == str(user.get("id")):
            return True
    except sqlite3.OperationalError:
        pass
    raise HTTPException(403, "این عملیات فقط برای مالک پلتفرم مجاز است.")

def _license_for_tenant(tenant_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM tenant_licenses WHERE tenant_id=?", (tenant_id,)).fetchone()
        if row is None:
            now = datetime.now(timezone.utc)
            conn.execute("INSERT OR IGNORE INTO tenant_licenses(tenant_id,status,trial_started_at,trial_ends_at) VALUES(?,?,?,?)",
                         (tenant_id,"trial",now.isoformat(),(now+timedelta(days=90)).isoformat()))
            row = conn.execute("SELECT * FROM tenant_licenses WHERE tenant_id=?", (tenant_id,)).fetchone()
        result = dict(row)
        if result["status"] == "trial":
            try:
                end = datetime.fromisoformat(result["trial_ends_at"])
                if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= end:
                    conn.execute("UPDATE tenant_licenses SET status='expired',updated_at=CURRENT_TIMESTAMP WHERE tenant_id=?", (tenant_id,))
                    result["status"] = "expired"
            except (TypeError, ValueError):
                result["status"] = "expired"
                conn.execute("UPDATE tenant_licenses SET status='expired',updated_at=CURRENT_TIMESTAMP WHERE tenant_id=?", (tenant_id,))
        return result

class LicenseIssueIn(BaseModel):
    tenant_id: int = Field(gt=0)
    edition: str = Field(default="standard", min_length=1, max_length=40)
    expires_at: str | None = Field(default=None, max_length=40)

class LicenseActivateIn(BaseModel):
    activation_key: str = Field(min_length=12, max_length=160)

class BankAccountIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    institution: str = Field(default="", max_length=120)
    account_holder: str = Field(default="", max_length=120)
    iban_masked: str = Field(default="", max_length=40)
    currency: str = Field(default="EUR", min_length=3, max_length=8)
    is_default: bool = False
    provider: str = Field(default="manual", max_length=40)

@app.get("/api/account/license")
def account_license(user=Depends(user_from_header)):
    lic = _license_for_tenant(user["tenant_id"])
    return {k: lic[k] for k in ("tenant_id","status","trial_started_at","trial_ends_at","edition","activated_at","updated_at")}

@app.post("/api/account/license/activate")
def activate_license(body: LicenseActivateIn, user=Depends(user_from_header)):
    key_hash = hashlib.sha256(body.activation_key.strip().encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        key = conn.execute("SELECT id,tenant_id,edition,expires_at,redeemed_at FROM activation_keys WHERE key_hash=?", (key_hash,)).fetchone()
        if not key or key["tenant_id"] != user["tenant_id"] or key["redeemed_at"]:
            raise HTTPException(400, "کلید فعال‌سازی معتبر نیست یا قبلاً استفاده شده است.")
        if key["expires_at"]:
            try:
                expiry = datetime.fromisoformat(key["expires_at"])
                if expiry.tzinfo is None: expiry = expiry.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= expiry:
                    raise HTTPException(400, "مهلت استفاده از کلید فعال‌سازی تمام شده است.")
            except ValueError:
                raise HTTPException(400, "تاریخ انقضای کلید معتبر نیست.")
        redeemed = conn.execute("UPDATE activation_keys SET redeemed_at=? WHERE id=? AND redeemed_at IS NULL", (now,key["id"]))
        if redeemed.rowcount != 1:
            raise HTTPException(409, "این کلید هم‌زمان در درخواست دیگری مصرف شده است.")
        conn.execute("UPDATE tenant_licenses SET status='active',edition=?,activated_at=?,updated_at=CURRENT_TIMESTAMP WHERE tenant_id=?",
                     (key["edition"],now,user["tenant_id"]))
        conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (user["tenant_id"],"license.activated"))
    return {"status":"active","edition":key["edition"],"activated_at":now,"message":"مجوز نرم‌افزار فعال شد."}

@app.post("/api/platform/licenses")
def issue_activation_key(body: LicenseIssueIn, user=Depends(user_from_header)):
    _platform_owner(user)
    with db() as conn:
        if not conn.execute("SELECT 1 FROM tenants WHERE id=?", (body.tenant_id,)).fetchone():
            raise HTTPException(404, "شرکت موردنظر یافت نشد.")
        raw_key = "LDR-" + secrets.token_urlsafe(27)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn.execute("INSERT INTO activation_keys(tenant_id,key_hash,edition,created_by_user_id,expires_at) VALUES(?,?,?,?,?)",
                     (body.tenant_id,key_hash,body.edition, user["id"], body.expires_at))
        conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (body.tenant_id,"license.key_issued"))
    # Plaintext key is returned once only; only its hash is stored.
    return {"activation_key":raw_key,"tenant_id":body.tenant_id,"edition":body.edition,"expires_at":body.expires_at,
            "warning":"این کلید فقط اکنون نمایش داده می‌شود؛ آن را امن به شرکت تحویل دهید."}

@app.get("/api/platform/licenses")
def list_platform_licenses(user=Depends(user_from_header)):
    _platform_owner(user)
    with db() as conn:
        rows = conn.execute("""SELECT t.id tenant_id,t.name company_name,l.status,l.trial_started_at,l.trial_ends_at,l.edition,l.activated_at
          FROM tenants t LEFT JOIN tenant_licenses l ON l.tenant_id=t.id ORDER BY t.id DESC LIMIT 500""").fetchall()
    return [dict(row) for row in rows]

@app.get("/api/bank-accounts")
def list_bank_accounts(user=Depends(user_from_header)):
    with db() as conn:
        rows = conn.execute("""SELECT id,label,institution,account_holder,iban_masked,currency,is_default,provider,connection_status,created_at
          FROM tenant_bank_accounts WHERE tenant_id=? ORDER BY is_default DESC,id DESC""", (user["tenant_id"],)).fetchall()
    return [dict(row) for row in rows]

@app.post("/api/bank-accounts")
def add_bank_account(body: BankAccountIn, user=Depends(user_from_header)):
    label, institution, holder, iban = body.label.strip(), body.institution.strip(), body.account_holder.strip(), body.iban_masked.strip()
    # Persist only a masked account reference, never a full IBAN/account number.
    if iban and not any(marker in iban for marker in ("•", "*", "x", "X")):
        compact_iban = re.sub(r"\s+", "", iban)
        iban = ("••••" + compact_iban[-4:]) if len(compact_iban) > 4 else compact_iban
    if not label: raise HTTPException(422, "عنوان حساب بانکی الزامی است.")
    if body.provider != "manual":
        raise HTTPException(501, "اتصال مستقیم این ارائه‌دهنده هنوز پیاده‌سازی و تأیید نشده است؛ حساب دستی فقط اطلاعات نمایشی را ذخیره می‌کند.")
    with db() as conn:
        if body.is_default:
            conn.execute("UPDATE tenant_bank_accounts SET is_default=0 WHERE tenant_id=?", (user["tenant_id"],))
        cur = conn.execute("""INSERT INTO tenant_bank_accounts(tenant_id,label,institution,account_holder,iban_masked,currency,is_default,provider,connection_status)
          VALUES(?,?,?,?,?,?,?,?,?)""", (user["tenant_id"],label,institution,holder,iban,body.currency.upper(),int(body.is_default),"manual","not_configured"))
        conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (user["tenant_id"],"bank_account.created"))
        account_id = cur.lastrowid
    return {"id":account_id,"message":"اطلاعات حساب ثبت شد؛ انتقال وجه بانکی از این ثبت دستی انجام نمی‌شود."}

@app.delete("/api/bank-accounts/{account_id}")
def delete_bank_account(account_id: int, user=Depends(user_from_header)):
    with db() as conn:
        cur = conn.execute("DELETE FROM tenant_bank_accounts WHERE id=? AND tenant_id=?", (account_id,user["tenant_id"]))
        if cur.rowcount == 0: raise HTTPException(404, "حساب بانکی یافت نشد.")
        conn.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (user["tenant_id"],"bank_account.deleted"))
    return {"message":"حساب بانکی حذف شد."}

@app.get("/api/bank-accounts/status")
def bank_accounts_status(user=Depends(user_from_header)):
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) n FROM tenant_bank_accounts WHERE tenant_id=?", (user["tenant_id"],)).fetchone()["n"]
    return {"accounts":count,"provider_integration":"not_configured","real_transfers_enabled":False,
            "message":"ثبت حساب و مشخصات آن فعال است؛ انتقال واقعی تا زمان اتصال درگاه بانکی معتبر و تأیید تراکنش فعال نیست."}
