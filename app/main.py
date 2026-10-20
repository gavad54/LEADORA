import os, sqlite3, secrets, hashlib, hmac, time, re
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DB_PATH = os.getenv("LEADORA_DB", str(ROOT.parent / "data" / "leadora.db"))
SECRET = os.getenv("LEADORA_SECRET", "development-only-change-me")
ENV = os.getenv("LEADORA_ENV", "development")
if ENV == "production" and (len(SECRET) < 32 or SECRET == "development-only-change-me"):
    raise RuntimeError("Set a random LEADORA_SECRET of at least 32 characters")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="LEADORA MVP", version="0.3.1", description="Persian-first business operations MVP")

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
        """)
init_db()

def pw_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180000).hex()

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
    return {"status":"ok","database":"ok","product":"LEADORA","version":"0.3.0","mode":"mvp"}

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
    with db() as c:
        rows=c.execute("SELECT u.id,u.tenant_id,u.email,u.salt,u.password_hash FROM users u JOIN tenants t ON t.id=u.tenant_id WHERE lower(u.email)=? AND lower(t.name)=? ORDER BY u.id",(email,company_name)).fetchall()
    # Check all matching accounts because company names and email addresses are not globally unique.
    row = next((candidate for candidate in rows if hmac.compare_digest(pw_hash(body.password,candidate["salt"]),candidate["password_hash"])), None)
    if not row:
        raise HTTPException(401,"اطلاعات ورود صحیح نیست.")
    return {"token":token(row["id"],row["tenant_id"]),"user":{"email":row["email"]}}

@app.get("/api/products")
def products(user=Depends(user_from_header)):
    with db() as c: rows=c.execute("SELECT id,sku,name,price,stock FROM products WHERE tenant_id=? ORDER BY id DESC",(user["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/products")
def add_product(body: ProductIn,user=Depends(user_from_header)):
    with db() as c:
        try:
            cur=c.execute("INSERT INTO products(tenant_id,sku,name,price,stock) VALUES(?,?,?,?,?)",(user["tenant_id"],body.sku.strip(),body.name.strip(),body.price,body.stock))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"product.created"))
        except sqlite3.IntegrityError: raise HTTPException(409,"کد کالا تکراری است.")
    return {"id":cur.lastrowid,"message":"کالا ثبت شد."}

@app.get("/api/customers")
def customers(user=Depends(user_from_header)):
    with db() as c: rows=c.execute("SELECT id,name,phone FROM customers WHERE tenant_id=? ORDER BY id DESC",(user["tenant_id"],)).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/customers")
def add_customer(body: CustomerIn,user=Depends(user_from_header)):
    with db() as c:
        cur=c.execute("INSERT INTO customers(tenant_id,name,phone) VALUES(?,?,?)",(user["tenant_id"],body.name.strip(),body.phone.strip()))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(user["tenant_id"],"customer.created"))
    return {"id":cur.lastrowid,"message":"مشتری ثبت شد."}

@app.get("/api/insights")
def insights(user=Depends(user_from_header)):
    with db() as c:
        low=c.execute("SELECT sku,name,stock FROM products WHERE tenant_id=? AND stock<=5 ORDER BY stock",(user["tenant_id"],)).fetchall()
    return {"mode":"rules_based_mvp","low_stock":[dict(r) for r in low],"message":"تحلیل قواعدمحور نمونه؛ نه خروجی مدل هوش مصنوعی."}

app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")
