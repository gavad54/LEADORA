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
