import os, sqlite3, secrets, hashlib, hmac, time, re
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse, StreamingResponse
import csv, io, json
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DB_PATH = os.getenv("LEADORA_DB", str(ROOT.parent / "data" / "leadora.db"))
SECRET = os.getenv("LEADORA_SECRET", "development-only-change-me")
ENV = os.getenv("LEADORA_ENV", "development")
if ENV == "production" and (len(SECRET) < 32 or SECRET == "development-only-change-me"):
    raise RuntimeError("Set a random LEADORA_SECRET of at least 32 characters")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="LEADORA MVP", version="0.4.0", description="Persian-first business operations MVP")

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
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

def user_from_header(authorization: str | None = Header(default=None)):
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
        return dict(u)
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

@app.get("/manifest.webmanifest")
def pwa_manifest():
    return FileResponse(ROOT / "static" / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/service-worker.js")
def pwa_service_worker():
    return FileResponse(ROOT / "static" / "service-worker.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})

@app.get("/icon.svg")
def pwa_icon():
    return FileResponse(ROOT / "static" / "icon.svg", media_type="image/svg+xml")

@app.get("/api/health")
def health():
    with db() as c: c.execute("SELECT 1")
    return {"status":"ok","database":"ok","product":"LEADORA","version":"0.4.0","mode":"mvp"}

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
        except sqlite3.IntegrityError:
            raise HTTPException(409,"این ایمیل قبلاً برای این شرکت ثبت شده است.")
    return {"token":token(uid,tid),"tenant":{"id":tid,"name":company_name,"industry":industry},"user":{"email":email}}

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
    # Business-data backup only: credentials and password hashes are deliberately excluded.
    with db() as c:
        tenant = c.execute("SELECT id,name,industry FROM tenants WHERE id=?", (user["tenant_id"],)).fetchone()
        products = c.execute("SELECT id,sku,name,price,stock FROM products WHERE tenant_id=? ORDER BY id", (user["tenant_id"],)).fetchall()
        customers = c.execute("SELECT id,name,phone FROM customers WHERE tenant_id=? ORDER BY id", (user["tenant_id"],)).fetchall()
        audit = c.execute("SELECT action,created_at FROM audit_log WHERE tenant_id=? ORDER BY id", (user["tenant_id"],)).fetchall()
    payload = json.dumps({
        "format": "leadora-tenant-backup-v1",
        "tenant": dict(tenant),
        "products": [dict(row) for row in products],
        "customers": [dict(row) for row in customers],
        "audit_log": [dict(row) for row in audit],
    }, ensure_ascii=False, indent=2)
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

@app.post("/api/invoices")
def create_invoice(body: InvoiceIn, user=Depends(user_from_header)):
    if not _date_ok(body.issue_date) or not _date_ok(body.due_date) or body.due_date < body.issue_date:
        raise HTTPException(422, "تاریخ صدور و سررسید باید معتبر باشند و سررسید قبل از صدور نباشد.")
    tid = user["tenant_id"]
    with db() as c:
        if body.customer_id is not None and not c.execute("SELECT 1 FROM customers WHERE id=? AND tenant_id=?", (body.customer_id,tid)).fetchone():
            raise HTTPException(404, "مشتری در این شرکت یافت نشد.")
        try:
            cur = c.execute("INSERT INTO invoices(tenant_id,customer_id,invoice_number,issue_date,due_date,amount,note) VALUES(?,?,?,?,?,?,?)",
                (tid,body.customer_id,body.invoice_number.strip(),body.issue_date,body.due_date,body.amount,body.note.strip()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "شماره فاکتور تکراری است.")
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"invoice.created"))
    return {"id":cur.lastrowid,"message":"فاکتور ثبت شد."}

@app.get("/api/invoices")
def list_invoices(user=Depends(user_from_header)):
    from datetime import date
    tid=user["tenant_id"]; today=date.today().isoformat()
    with db() as c:
        rows=c.execute("""SELECT i.id,i.customer_id,i.invoice_number,i.issue_date,i.due_date,i.amount,i.note,
          COALESCE(SUM(p.amount),0) AS paid, MAX(0,i.amount-COALESCE(SUM(p.amount),0)) AS outstanding,
          CASE WHEN i.amount<=COALESCE(SUM(p.amount),0) THEN 'paid'
               WHEN i.due_date<? THEN 'overdue' ELSE 'open' END AS computed_status
          FROM invoices i LEFT JOIN payments p ON p.invoice_id=i.id AND p.tenant_id=i.tenant_id
          WHERE i.tenant_id=? GROUP BY i.id ORDER BY i.due_date""",(today,tid)).fetchall()
    return [dict(r) for r in rows]

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

@app.post("/api/expenses")
def create_expense(body: ExpenseIn, user=Depends(user_from_header)):
    if not _date_ok(body.due_date): raise HTTPException(422,"تاریخ هزینه معتبر نیست.")
    tid=user["tenant_id"]
    with db() as c:
        cur=c.execute("INSERT INTO expenses(tenant_id,category,description,amount,due_date,status,vendor) VALUES(?,?,?,?,?,?,?)",
          (tid,body.category.strip(),body.description.strip(),body.amount,body.due_date,body.status,body.vendor.strip()))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"expense.created"))
    return {"id":cur.lastrowid,"message":"هزینه ثبت شد."}

@app.get("/api/expenses")
def list_expenses(user=Depends(user_from_header)):
    with db() as c:
        rows=c.execute("SELECT id,category,description,amount,due_date,status,vendor FROM expenses WHERE tenant_id=? ORDER BY due_date",(user["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/opportunities")
def create_opportunity(body: OpportunityIn, user=Depends(user_from_header)):
    tid=user["tenant_id"]
    if body.expected_close_date and not _date_ok(body.expected_close_date): raise HTTPException(422,"تاریخ بستن فرصت معتبر نیست.")
    if body.last_contact_at and not _date_ok(body.last_contact_at): raise HTTPException(422,"تاریخ آخرین تماس معتبر نیست.")
    with db() as c:
        if body.customer_id is not None and not c.execute("SELECT 1 FROM customers WHERE id=? AND tenant_id=?",(body.customer_id,tid)).fetchone():
            raise HTTPException(404,"مشتری در این شرکت یافت نشد.")
        cur=c.execute("""INSERT INTO opportunities(tenant_id,customer_id,title,source,stage,estimated_value,expected_close_date,last_contact_at,lost_reason)
          VALUES(?,?,?,?,?,?,?,?,?)""",(tid,body.customer_id,body.title.strip(),body.source.strip(),body.stage,body.estimated_value,body.expected_close_date,body.last_contact_at,body.lost_reason.strip()))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"opportunity.created"))
    return {"id":cur.lastrowid,"message":"فرصت فروش ثبت شد."}

@app.get("/api/opportunities")
def list_opportunities(user=Depends(user_from_header)):
    with db() as c:
        rows=c.execute("SELECT id,customer_id,title,source,stage,estimated_value,expected_close_date,last_contact_at,lost_reason FROM opportunities WHERE tenant_id=? ORDER BY id DESC",(user["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]

@app.get("/api/agents/overview")
def agents_overview(user=Depends(user_from_header)):
    from datetime import date, timedelta
    tid=user["tenant_id"]; today=date.today(); today_s=today.isoformat()
    with db() as c:
        inv=c.execute("""SELECT i.id,i.invoice_number,i.due_date,i.amount,COALESCE(SUM(p.amount),0) paid
          FROM invoices i LEFT JOIN payments p ON p.invoice_id=i.id AND p.tenant_id=i.tenant_id
          WHERE i.tenant_id=? GROUP BY i.id""",(tid,)).fetchall()
        expenses=c.execute("SELECT amount,due_date,status,category,description FROM expenses WHERE tenant_id=?",(tid,)).fetchall()
        opps=c.execute("SELECT stage,estimated_value,last_contact_at,expected_close_date FROM opportunities WHERE tenant_id=?",(tid,)).fetchall()
        customers=c.execute("SELECT id,name FROM customers WHERE tenant_id=?",(tid,)).fetchall()
    aging={"not_due":0.0,"1_30":0.0,"31_60":0.0,"61_90":0.0,"90_plus":0.0}
    overdue=[]; receivable=0.0; due_in_7=0.0
    for r in inv:
        outstanding=max(0.0,float(r["amount"])-float(r["paid"]))
        if outstanding<=0: continue
        receivable+=outstanding
        days=(today-date.fromisoformat(r["due_date"])).days
        if days<=0:
            aging["not_due"]+=outstanding
            if (date.fromisoformat(r["due_date"])-today).days<=7: due_in_7+=outstanding
        else:
            key="1_30" if days<=30 else "31_60" if days<=60 else "61_90" if days<=90 else "90_plus"
            aging[key]+=outstanding
            overdue.append({"invoice_number":r["invoice_number"],"days_overdue":days,"outstanding":round(outstanding,2),"severity":"high" if days>30 else "medium"})
    overdue.sort(key=lambda x:(x["days_overdue"],x["outstanding"]),reverse=True)
    due_expenses=[dict(r) for r in expenses if r["status"]=="planned" and r["due_date"]<= (today+timedelta(days=30)).isoformat()]
    expected_outflow=sum(float(r["amount"]) for r in due_expenses)
    stages={}
    for r in opps: stages[r["stage"]]=stages.get(r["stage"],0)+1
    stale=[]
    for r in customers:
        # No churn claim without customer activity/purchase history; use explicit evidence status.
        pass
    actions=[]
    if overdue: actions.append({"agent":"receivables","severity":"high" if any(x["days_overdue"]>30 for x in overdue) else "medium","title":"پیگیری مطالبات سررسیدگذشته","explanation":f"{len(overdue)} فاکتور دارای مانده سررسیدگذشته است.","recommendation":"فاکتورها را بر اساس مبلغ و روزهای تأخیر اولویت‌بندی و پیش‌نویس پیگیری تهیه کنید.","approval_required":True})
    if expected_outflow: actions.append({"agent":"cash_flow","severity":"medium","title":"بررسی خروجی نقدی ۳۰ روز آینده","explanation":f"هزینه‌های برنامه‌ریزی‌شده نزدیک به سررسید: {expected_outflow:.2f}.","recommendation":"ورودی‌های نقدی مورد انتظار را با هزینه‌ها مقایسه و پرداخت‌ها را اولویت‌بندی کنید.","approval_required":True})
    if not inv: actions.append({"agent":"receivables","severity":"info","title":"داده مطالبات کافی نیست","explanation":"هنوز فاکتوری ثبت نشده است.","recommendation":"فاکتورها را دستی ثبت کنید یا در مرحله بعد فایل استاندارد را وارد کنید.","approval_required":False})
    if not opps: actions.append({"agent":"sales_analytics","severity":"info","title":"داده قیف فروش کافی نیست","explanation":"برای محاسبه نرخ تبدیل، فرصت‌های فروش ثبت نشده‌اند.","recommendation":"فرصت‌ها را همراه با مرحله فروش، ارزش تقریبی و منبع ثبت کنید.","approval_required":False})
    return {"mode":"rules_based","as_of":today_s,"agents":[
      {"id":"business_manager","name":"دستیار مدیریت کسب‌وکار","status":"rules_based"},
      {"id":"receivables","name":"مدیریت مطالبات","status":"active"},
      {"id":"sales_analytics","name":"تحلیل فروش و قیف","status":"active"},
      {"id":"retention","name":"حفظ مشتری","status":"insufficient_data" if not opps else "limited_data"},
      {"id":"cash_flow","name":"مدیریت نقدینگی","status":"active"},
      {"id":"marketing_sales","name":"بازاریابی و فروش هوشمند","status":"limited_data"}],
      "metrics":{"outstanding_receivables":round(receivable,2),"due_in_7_days":round(due_in_7,2),"aging":{k:round(v,2) for k,v in aging.items()},"planned_outflow_30_days":round(expected_outflow,2),"pipeline_count":len(opps),"pipeline_value":round(sum(float(r["estimated_value"]) for r in opps if r["stage"] not in ("won","lost")),2),"pipeline_by_stage":stages,"customer_count":len(customers)},
      "overdue_invoices":overdue[:100],"actions":actions,
      "limitations":["پیش‌بینی ریزش مشتری تا ثبت تاریخچه تعامل یا خرید، قابل اتکا نیست.","بازده کمپین تا ثبت هزینه و نتیجه کمپین محاسبه نمی‌شود.","پیش‌بینی نقدینگی فعلاً قواعدمحور است و موجودی بانکی زنده را نشان نمی‌دهد."]}

@app.get("/api/agents/actions")
def list_agent_actions(user=Depends(user_from_header)):
    with db() as c:
        rows=c.execute("SELECT id,agent,severity,title,explanation,recommendation,status,approval_required,created_at FROM agent_actions WHERE tenant_id=? ORDER BY id DESC LIMIT 200",(user["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/agents/actions/{action_id}/resolve")
def resolve_agent_action(action_id: int, user=Depends(user_from_header)):
    tid=user["tenant_id"]
    with db() as c:
        cur=c.execute("UPDATE agent_actions SET status='resolved',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=? AND status='open'",(action_id,tid))
        if not cur.rowcount: raise HTTPException(404,"اقدام باز یافت نشد.")
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"agent_action.resolved"))
    return {"message":"اقدام علامت‌گذاری شد."}

@app.get("/api/import/template/{dataset}.csv")
def import_template(dataset: str, user=Depends(user_from_header)):
    templates={
      "invoices":["invoice_number","customer_id","issue_date(YYYY-MM-DD)","due_date(YYYY-MM-DD)","amount","note"],
      "expenses":["category","description","amount","due_date(YYYY-MM-DD)","status(planned/paid/cancelled)","vendor"],
      "opportunities":["title","source","stage(lead/qualified/proposal/negotiation/won/lost)","estimated_value","expected_close_date(YYYY-MM-DD)","last_contact_at(YYYY-MM-DD)","lost_reason"]
    }
    if dataset not in templates: raise HTTPException(404,"قالب برای این نوع داده وجود ندارد.")
    stream=io.StringIO(newline=""); csv.writer(stream).writerow(templates[dataset])
    return StreamingResponse(iter(["\\ufeff"+stream.getvalue()]),media_type="text/csv; charset=utf-8",
      headers={"Content-Disposition":f'attachment; filename="leadora-{dataset}-template.csv"',"Cache-Control":"no-store"})
