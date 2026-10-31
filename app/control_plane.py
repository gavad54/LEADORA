"""Standalone owner control plane for LEADORA.

This service owns only licensing, staff authorization, support entitlements and
audit metadata. It must use a separate database and never open a customer
LEADORA_DB or business-data volume.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import struct
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, Field

from app.instance_config import customer_volume_name
from app.instance_licensing import LicenseValidationError, sign_license_token, verify_license_token


ALLOWED_SCOPES = {
    "licenses:read",
    "licenses:write",
    "support:read",
    "support:write",
    "staff:manage",
    "audit:read",
    "instances:read",
}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TOKEN_TTL_SECONDS = 8 * 60 * 60


class ControlPlaneConfigurationError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _hash_secret(value: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, 310_000)
    return base64.b64encode(salt).decode("ascii"), base64.b64encode(digest).decode("ascii")


def _verify_secret(value: str, salt_b64: str, digest_b64: str) -> bool:
    try:
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
    except (ValueError, base64.binascii.Error):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), salt, 310_000)
    return hmac.compare_digest(actual, expected)


def _valid_totp(secret: str, code: str, now: int | None = None) -> bool:
    if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
        return False
    try:
        key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8), casefold=True)
    except (ValueError, base64.binascii.Error):
        return False
    current = int(time.time() if now is None else now)
    for offset in (-30, 0, 30):
        counter = struct.pack(">Q", (current + offset) // 30)
        digest = hmac.new(key, counter, hashlib.sha1).digest()
        index = digest[-1] & 0x0F
        number = struct.unpack(">I", digest[index:index + 4])[0] & 0x7FFFFFFF
        expected = f"{number % 1_000_000:06d}"
        if hmac.compare_digest(expected, code):
            return True
    return False


def _is_persian_keyword(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value.strip()) >= 8
        and any("\u0600" <= char <= "\u06ff" for char in value)
    )


def create_app(
    db_path: str | Path | None = None,
    *,
    settings: Mapping[str, str] | None = None,
) -> FastAPI:
    config = dict(os.environ)
    if settings:
        config.update(settings)
    database_path = Path(
        db_path or config.get("LEADORA_CONTROL_DB", "/tmp/leadora-control-plane.sqlite3")
    ).expanduser()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    control_secret = config.get("LEADORA_CONTROL_SECRET", "")
    private_key_b64 = config.get("LEADORA_LICENSE_PRIVATE_KEY", "")
    environment = config.get("LEADORA_ENV", "development")
    if environment == "production":
        if len(control_secret) < 32:
            raise ControlPlaneConfigurationError("LEADORA_CONTROL_SECRET must contain at least 32 characters")
        if not private_key_b64:
            raise ControlPlaneConfigurationError("control plane signing private key is required")
        try:
            if len(base64.b64decode(private_key_b64, validate=True)) != 32:
                raise ValueError("wrong key length")
        except (ValueError, base64.binascii.Error) as exc:
            raise ControlPlaneConfigurationError("control plane signing private key must be a base64 Ed25519 key") from exc
        if not config.get("LEADORA_OWNER_MFA_SECRET"):
            raise ControlPlaneConfigurationError("owner MFA secret is required")

    @contextmanager
    def db():
        connection = sqlite3.connect(str(database_path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def init_db() -> None:
        with db() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS control_users(
                    id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK(role IN ('owner','license_manager','support_agent','auditor')),
                    scopes_json TEXT NOT NULL DEFAULT '[]',
                    salt TEXT NOT NULL,
                    secret_hash TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS control_sessions(
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES control_users(id),
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS control_staff_invitations(
                    id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at INTEGER NOT NULL,
                    redeemed_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS control_licenses(
                    id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    customer_ref TEXT NOT NULL,
                    edition TEXT NOT NULL,
                    modules_json TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    offline_grace_days INTEGER NOT NULL,
                    token_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active','revoked','superseded')),
                    revoked_at TEXT,
                    created_by INTEGER NOT NULL REFERENCES control_users(id),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS control_licenses_instance_idx
                    ON control_licenses(instance_id,status);
                CREATE UNIQUE INDEX IF NOT EXISTS control_licenses_one_active_per_instance
                    ON control_licenses(instance_id) WHERE status='active';
                CREATE TABLE IF NOT EXISTS control_support_contracts(
                    id INTEGER PRIMARY KEY,
                    customer_ref TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active','expired','suspended','cancelled')),
                    notes TEXT NOT NULL DEFAULT '',
                    created_by INTEGER NOT NULL REFERENCES control_users(id),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS control_audit(
                    id INTEGER PRIMARY KEY,
                    actor_id INTEGER NOT NULL REFERENCES control_users(id),
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS control_login_attempts(
                    email_key TEXT PRIMARY KEY,
                    attempts INTEGER NOT NULL,
                    window_start INTEGER NOT NULL
                );
                """
            )
        bootstrap_owner()

    def bootstrap_owner() -> None:
        with db() as connection:
            if connection.execute("SELECT 1 FROM control_users WHERE role='owner'").fetchone():
                return
            email = config.get("LEADORA_OWNER_EMAIL", "").strip().casefold()
            keyword = config.get("LEADORA_OWNER_KEYWORD", "")
            mfa_secret = config.get("LEADORA_OWNER_MFA_SECRET", "")
            if not email and environment != "production":
                return
            if not EMAIL_RE.fullmatch(email):
                raise ControlPlaneConfigurationError("a valid LEADORA_OWNER_EMAIL is required for first owner bootstrap")
            if not _is_persian_keyword(keyword):
                raise ControlPlaneConfigurationError("owner keyword must be a Persian phrase of at least 8 characters")
            if not mfa_secret:
                raise ControlPlaneConfigurationError("LEADORA_OWNER_MFA_SECRET is required")
            try:
                decoded_mfa = base64.b32decode(
                    mfa_secret.upper() + "=" * (-len(mfa_secret) % 8), casefold=True
                )
                if len(decoded_mfa) < 16:
                    raise ValueError("MFA secret is too short")
            except (ValueError, base64.binascii.Error) as exc:
                raise ControlPlaneConfigurationError("LEADORA_OWNER_MFA_SECRET must be at least 16 bytes of Base32") from exc
            salt, digest = _hash_secret(keyword)
            connection.execute(
                "INSERT INTO control_users(email,role,scopes_json,salt,secret_hash) VALUES(?,?,?,?,?)",
                (email, "owner", json.dumps(sorted(ALLOWED_SCOPES)), salt, digest),
            )

    def _login_key(email: str) -> str:
        return hashlib.sha256((control_secret + "|" + email.strip().casefold()).encode()).hexdigest()

    def check_login_rate(email: str) -> None:
        key = _login_key(email)
        now = int(time.time())
        with db() as connection:
            row = connection.execute(
                "SELECT attempts,window_start FROM control_login_attempts WHERE email_key=?",
                (key,),
            ).fetchone()
            if row and now - row["window_start"] < 900 and row["attempts"] >= 5:
                raise HTTPException(429, "تلاش‌های ورود بیش از حد مجاز است؛ ۱۵ دقیقه دیگر تلاش کنید.")
            if row and now - row["window_start"] >= 900:
                connection.execute("DELETE FROM control_login_attempts WHERE email_key=?", (key,))

    def record_login_failure(email: str) -> None:
        key = _login_key(email)
        now = int(time.time())
        with db() as connection:
            row = connection.execute(
                "SELECT attempts,window_start FROM control_login_attempts WHERE email_key=?",
                (key,),
            ).fetchone()
            if not row or now - row["window_start"] >= 900:
                connection.execute(
                    "INSERT OR REPLACE INTO control_login_attempts(email_key,attempts,window_start) VALUES(?,?,?)",
                    (key, 1, now),
                )
            else:
                connection.execute(
                    "UPDATE control_login_attempts SET attempts=attempts+1 WHERE email_key=?",
                    (key,),
                )

    def clear_login_failures(email: str) -> None:
        with db() as connection:
            connection.execute(
                "DELETE FROM control_login_attempts WHERE email_key=?",
                (_login_key(email),),
            )

    def audit(actor_id: int, action: str, target_type: str, target_id: str, details: dict[str, Any] | None = None) -> None:
        with db() as connection:
            connection.execute(
                "INSERT INTO control_audit(actor_id,action,target_type,target_id,details_json) VALUES(?,?,?,?,?)",
                (actor_id, action, target_type, str(target_id), json.dumps(details or {}, ensure_ascii=False, sort_keys=True)),
            )

    def create_session(user_id: int) -> str:
        raw_token = secrets.token_urlsafe(36)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        with db() as connection:
            connection.execute(
                "INSERT INTO control_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                (token_hash, user_id, int(time.time()) + TOKEN_TTL_SECONDS),
            )
        return raw_token

    def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "نشست معتبر نیست.")
        raw_token = authorization[7:].strip()
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        with db() as connection:
            row = connection.execute(
                """SELECT u.* FROM control_sessions s
                   JOIN control_users u ON u.id=s.user_id
                   WHERE s.token_hash=? AND s.expires_at>=? AND u.active=1""",
                (token_hash, int(time.time())),
            ).fetchone()
        if not row:
            raise HTTPException(401, "نشست منقضی یا لغو شده است.")
        user = dict(row)
        user["scopes"] = json.loads(user.pop("scopes_json"))
        user.pop("salt", None)
        user.pop("secret_hash", None)
        return user

    def require_scope(scope: str):
        def dependency(user=Depends(current_user)):
            if user["role"] != "owner" and scope not in user["scopes"]:
                raise HTTPException(403, "دسترسی لازم برای این عملیات وجود ندارد.")
            return user
        return dependency

    class OwnerLoginIn(BaseModel):
        email: str = Field(min_length=5, max_length=180)
        keyword: str = Field(min_length=8, max_length=200)
        totp: str = Field(min_length=6, max_length=6)

    class StaffLoginIn(BaseModel):
        email: str = Field(min_length=5, max_length=180)
        password: str = Field(min_length=12, max_length=200)

    class StaffInviteIn(BaseModel):
        email: str = Field(min_length=5, max_length=180)
        scopes: list[str] = Field(min_length=1, max_length=7)

    class StaffActivateIn(BaseModel):
        invitation_code: str = Field(min_length=32, max_length=256)
        password: str = Field(min_length=12, max_length=200)

    class StaffUpdateIn(BaseModel):
        active: bool | None = None
        scopes: list[str] | None = None

    class LicenseCreateIn(BaseModel):
        instance_id: str = Field(min_length=3, max_length=63)
        customer_ref: str = Field(min_length=3, max_length=120)
        edition: str = Field(min_length=2, max_length=40)
        modules: list[str] = Field(min_length=1, max_length=30)
        expires_at: datetime
        offline_grace_days: int = Field(default=14, ge=0, le=30)

    class LicenseRenewIn(BaseModel):
        expires_at: datetime
        offline_grace_days: int = Field(default=14, ge=0, le=30)

    class LicenseSyncIn(BaseModel):
        license_token: str = Field(min_length=100, max_length=16384)

    class SupportCreateIn(BaseModel):
        customer_ref: str = Field(min_length=3, max_length=120)
        instance_id: str = Field(min_length=3, max_length=63)
        plan: str = Field(min_length=2, max_length=80)
        starts_at: datetime
        ends_at: datetime
        notes: str = Field(default="", max_length=2000)

    class SupportUpdateIn(BaseModel):
        status: str = Field(pattern="^(active|expired|suspended|cancelled)$")

    api = FastAPI(title="LEADORA Owner Control Plane", version="1.0.0")

    @api.middleware("http")
    async def control_security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @api.get("/")
    def control_dashboard():
        return FileResponse(Path(__file__).resolve().parent / "static" / "control-plane.html")

    @api.get("/api/control/me")
    def who_am_i(user=Depends(current_user)):
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "scopes": user["scopes"],
        }

    @api.get("/api/control/health")
    def health():
        with db() as connection:
            connection.execute("SELECT 1")
        return {"status": "ok", "service": "leadora-control-plane", "business_data_access": False}

    @api.post("/api/control/auth/owner/login")
    def owner_login(body: OwnerLoginIn):
        email = body.email.strip().casefold()
        check_login_rate(email)
        with db() as connection:
            row = connection.execute(
                "SELECT * FROM control_users WHERE email=? AND role='owner' AND active=1",
                (email,),
            ).fetchone()
        if not row:
            record_login_failure(email)
            raise HTTPException(401, "اطلاعات مالک معتبر نیست.")
        if not _verify_secret(body.keyword, row["salt"], row["secret_hash"]):
            record_login_failure(email)
            raise HTTPException(401, "اطلاعات مالک معتبر نیست.")
        mfa_secret = config.get("LEADORA_OWNER_MFA_SECRET", "")
        if not _valid_totp(mfa_secret, body.totp):
            record_login_failure(email)
            raise HTTPException(401, "کد تأیید دومرحله‌ای معتبر نیست.")
        clear_login_failures(email)
        token = create_session(row["id"])
        audit(row["id"], "owner.login", "owner", row["id"])
        return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS}

    @api.post("/api/control/auth/staff/login")
    def staff_login(body: StaffLoginIn):
        email = body.email.strip().casefold()
        check_login_rate(email)
        with db() as connection:
            row = connection.execute(
                "SELECT * FROM control_users WHERE email=? AND role!='owner' AND active=1",
                (email,),
            ).fetchone()
        if not row or not _verify_secret(body.password, row["salt"], row["secret_hash"]):
            record_login_failure(email)
            raise HTTPException(401, "ایمیل یا گذرواژه معتبر نیست.")
        clear_login_failures(email)
        token = create_session(row["id"])
        audit(row["id"], "staff.login", "staff", row["id"])
        return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS}

    @api.post("/api/control/auth/logout")
    def logout(user=Depends(current_user), authorization: str | None = Header(default=None)):
        raw_token = authorization[7:].strip()
        with db() as connection:
            connection.execute(
                "DELETE FROM control_sessions WHERE token_hash=?",
                (hashlib.sha256(raw_token.encode()).hexdigest(),),
            )
        audit(user["id"], "session.revoked", "session", str(user["id"]))
        return {"ok": True}

    @api.get("/api/control/owner/identity")
    def owner_identity(user=Depends(current_user)):
        if user["role"] != "owner":
            raise HTTPException(403, "اطلاعات هویتی مالک محرمانه است.")
        return {"owner_id": user["id"], "email": user["email"], "role": "owner"}

    @api.post("/api/control/staff/invitations")
    def invite_staff(body: StaffInviteIn, user=Depends(require_scope("staff:manage"))):
        email = body.email.strip().casefold()
        scopes = sorted(set(body.scopes))
        if not EMAIL_RE.fullmatch(email):
            raise HTTPException(422, "ایمیل معتبر نیست.")
        if len(scopes) != len(body.scopes) or not set(scopes).issubset(ALLOWED_SCOPES - {"staff:manage"}):
            raise HTTPException(422, "دامنه دسترسی کارکنان معتبر نیست.")
        code = secrets.token_urlsafe(36)
        with db() as connection:
            if connection.execute("SELECT 1 FROM control_users WHERE email=?", (email,)).fetchone():
                raise HTTPException(409, "این کارمند قبلاً ثبت شده است.")
            connection.execute(
                "INSERT INTO control_staff_invitations(email,scopes_json,token_hash,expires_at) VALUES(?,?,?,?)",
                (email, json.dumps(scopes), hashlib.sha256(code.encode()).hexdigest(), int(time.time()) + 86400),
            )
        audit(user["id"], "staff.invited", "staff", email, {"scopes": scopes})
        return {"email": email, "invitation_code": code, "expires_in": 86400}

    @api.post("/api/control/staff/activate")
    def activate_staff(body: StaffActivateIn):
        token_hash = hashlib.sha256(body.invitation_code.encode()).hexdigest()
        with db() as connection:
            invite = connection.execute(
                "SELECT * FROM control_staff_invitations WHERE token_hash=? AND redeemed_at IS NULL AND expires_at>=?",
                (token_hash, int(time.time())),
            ).fetchone()
            if not invite:
                raise HTTPException(400, "دعوت‌نامه معتبر یا قابل استفاده نیست.")
            scopes = json.loads(invite["scopes_json"])
            role = "license_manager" if "licenses:write" in scopes else (
                "support_agent" if "support:write" in scopes else "auditor"
            )
            salt, digest = _hash_secret(body.password)
            cursor = connection.execute(
                "INSERT INTO control_users(email,role,scopes_json,salt,secret_hash) VALUES(?,?,?,?,?)",
                (invite["email"], role, json.dumps(scopes), salt, digest),
            )
            staff_id = cursor.lastrowid
            connection.execute(
                "UPDATE control_staff_invitations SET redeemed_at=CURRENT_TIMESTAMP WHERE id=?",
                (invite["id"],),
            )
        return {"ok": True, "staff_id": staff_id, "role": role, "scopes": scopes}

    @api.get("/api/control/staff")
    def list_staff(user=Depends(require_scope("staff:manage"))):
        with db() as connection:
            rows = connection.execute(
                "SELECT id,email,role,scopes_json,active,created_at FROM control_users WHERE role!='owner' ORDER BY id"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "email": row["email"],
                "role": row["role"],
                "scopes": json.loads(row["scopes_json"]),
                "active": bool(row["active"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @api.patch("/api/control/staff/{staff_id}")
    def update_staff(staff_id: int, body: StaffUpdateIn, user=Depends(require_scope("staff:manage"))):
        with db() as connection:
            row = connection.execute(
                "SELECT id,role,scopes_json,active FROM control_users WHERE id=? AND role!='owner'",
                (staff_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "کارمند پیدا نشد.")
            scopes = json.loads(row["scopes_json"]) if body.scopes is None else sorted(set(body.scopes))
            if body.scopes is not None and (
                len(scopes) != len(body.scopes)
                or not set(scopes).issubset(ALLOWED_SCOPES - {"staff:manage"})
            ):
                raise HTTPException(422, "دامنه دسترسی کارکنان معتبر نیست.")
            active = int(row["active"]) if body.active is None else int(body.active)
            role = "license_manager" if "licenses:write" in scopes else (
                "support_agent" if "support:write" in scopes else "auditor"
            )
            connection.execute(
                "UPDATE control_users SET active=?,role=?,scopes_json=? WHERE id=?",
                (active, role, json.dumps(scopes), staff_id),
            )
            connection.execute(
                "DELETE FROM control_sessions WHERE user_id=?",
                (staff_id,),
            )
        audit(user["id"], "staff.updated", "staff", str(staff_id), {"active": bool(active), "scopes": scopes})
        return {"ok": True, "staff_id": staff_id, "active": bool(active), "scopes": scopes}

    @api.get("/api/control/licenses")
    def list_licenses(user=Depends(require_scope("licenses:read"))):
        with db() as connection:
            rows = connection.execute(
                """SELECT id,instance_id,customer_ref,edition,modules_json,issued_at,
                          expires_at,offline_grace_days,status,revoked_at,created_at
                   FROM control_licenses ORDER BY created_at DESC,id DESC"""
            ).fetchall()
        return [
            {
                "license_id": row["id"],
                "instance_id": row["instance_id"],
                "customer_ref": row["customer_ref"],
                "edition": row["edition"],
                "modules": json.loads(row["modules_json"]),
                "issued_at": row["issued_at"],
                "expires_at": row["expires_at"],
                "offline_grace_days": row["offline_grace_days"],
                "status": row["status"],
                "revoked_at": row["revoked_at"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @api.post("/api/control/licenses")
    def issue_license(body: LicenseCreateIn, user=Depends(require_scope("licenses:write"))):
        try:
            volume_name = customer_volume_name(body.instance_id)
        except ValueError as exc:
            raise HTTPException(422, "شناسه نصب معتبر نیست.") from exc
        modules = sorted(set(body.modules))
        if len(modules) != len(body.modules) or any(not re.fullmatch(r"[a-z][a-z0-9_-]{1,39}", item) for item in modules):
            raise HTTPException(422, "فهرست ماژول‌ها معتبر نیست.")
        issued_at = _utc_now()
        expires_at = body.expires_at.astimezone(timezone.utc) if body.expires_at.tzinfo else None
        if expires_at is None or expires_at <= issued_at:
            raise HTTPException(422, "تاریخ پایان مجوز باید در آینده و دارای منطقه زمانی باشد.")
        with db() as connection:
            existing_instance = connection.execute(
                "SELECT customer_ref,status FROM control_licenses WHERE instance_id=? LIMIT 1",
                (body.instance_id,),
            ).fetchone()
            if existing_instance:
                if existing_instance["customer_ref"] != body.customer_ref.strip():
                    raise HTTPException(409, "شناسه نصب قبلاً به مشتری دیگری اختصاص یافته و قابل استفاده مجدد نیست.")
                raise HTTPException(409, "شناسه نصب قبلاً ثبت شده است؛ برای تمدید از مسیر تمدید مجوز استفاده کنید.")
        license_id = "lic_" + secrets.token_urlsafe(18)
        claim = {
            "schema_version": 1,
            "license_id": license_id,
            "instance_id": body.instance_id,
            "customer_ref": body.customer_ref.strip(),
            "edition": body.edition.strip(),
            "modules": modules,
            "issued_at": _iso(issued_at),
            "expires_at": _iso(expires_at),
            "offline_grace_days": body.offline_grace_days,
        }
        try:
            token = sign_license_token(claim, private_key_b64)
        except Exception as exc:
            raise HTTPException(503, "کلید امضای مرکز مجوز تنظیم نشده یا معتبر نیست.") from exc
        try:
            with db() as connection:
                connection.execute(
                    """INSERT INTO control_licenses(
                        id,instance_id,customer_ref,edition,modules_json,issued_at,expires_at,
                        offline_grace_days,token_sha256,status,created_by
                    ) VALUES(?,?,?,?,?,?,?,?,?,'active',?)""",
                    (
                        license_id,
                        body.instance_id,
                        body.customer_ref.strip(),
                        body.edition.strip(),
                        json.dumps(modules),
                        _iso(issued_at),
                        _iso(expires_at),
                        body.offline_grace_days,
                        hashlib.sha256(token.encode()).hexdigest(),
                        user["id"],
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "برای این نصب هم‌زمان مجوز فعال دیگری صادر شده است.") from exc
        audit(user["id"], "license.issued", "license", license_id, {
            "instance_id": body.instance_id,
            "customer_ref": body.customer_ref,
            "edition": body.edition,
            "modules": modules,
            "expires_at": _iso(expires_at),
            "volume_name": volume_name,
        })
        return {"license_id": license_id, "instance_id": body.instance_id, "license_token": token}

    @api.post("/api/control/licenses/{license_id}/revoke")
    def revoke_license(license_id: str, user=Depends(require_scope("licenses:write"))):
        with db() as connection:
            row = connection.execute(
                "SELECT id,status FROM control_licenses WHERE id=?",
                (license_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "مجوز پیدا نشد.")
            if row["status"] == "revoked":
                return {"ok": True, "status": "revoked"}
            connection.execute(
                "UPDATE control_licenses SET status='revoked',revoked_at=? WHERE id=?",
                (_iso(_utc_now()), license_id),
            )
        audit(user["id"], "license.revoked", "license", license_id)
        return {"ok": True, "status": "revoked", "effective_on_next_instance_sync": True}

    def control_public_key() -> str:
        try:
            private_bytes = base64.b64decode(private_key_b64, validate=True)
            private = Ed25519PrivateKey.from_private_bytes(private_bytes)
            public_bytes = private.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        except (ValueError, base64.binascii.Error) as exc:
            raise HTTPException(503, "کلید امضای مرکز کنترل تنظیم نشده است.") from exc
        return base64.b64encode(public_bytes).decode("ascii")

    @api.post("/api/control/licenses/sync")
    def sync_customer_license(body: LicenseSyncIn):
        try:
            untrusted_claim = json.loads(
                base64.urlsafe_b64decode(
                    body.license_token.split(".", 1)[0]
                    + "=" * (-len(body.license_token.split(".", 1)[0]) % 4)
                ).decode("utf-8")
            )
            instance_id = untrusted_claim.get("instance_id", "")
            claim = verify_license_token(
                body.license_token,
                control_public_key(),
                instance_id,
            )
        except (ValueError, UnicodeError, LicenseValidationError, json.JSONDecodeError, AttributeError, IndexError):
            raise HTTPException(401, "توکن مجوز معتبر نیست.")
        token_hash = hashlib.sha256(body.license_token.encode()).hexdigest()
        with db() as connection:
            row = connection.execute(
                "SELECT status,token_sha256 FROM control_licenses WHERE id=? AND instance_id=?",
                (claim["license_id"], claim["instance_id"]),
            ).fetchone()
        if not row or not hmac.compare_digest(row["token_sha256"], token_hash):
            raise HTTPException(401, "این مجوز در مرکز کنترل ثبت نشده است.")
        if row["status"] in ("revoked", "superseded"):
            raise HTTPException(410, "مجوز این نصب لغو یا جایگزین شده است.")
        return {
            "status": claim["status"],
            "license_id": claim["license_id"],
            "instance_id": claim["instance_id"],
            "server_time": _iso(_utc_now()),
        }

    @api.post("/api/control/licenses/{license_id}/renew")
    def renew_license(license_id: str, body: LicenseRenewIn, user=Depends(require_scope("licenses:write"))):
        with db() as connection:
            old = connection.execute(
                "SELECT * FROM control_licenses WHERE id=?",
                (license_id,),
            ).fetchone()
            if not old:
                raise HTTPException(404, "مجوز پیدا نشد.")
            if old["status"] in ("revoked", "superseded"):
                raise HTTPException(409, "مجوز لغوشده یا جایگزین‌شده قابل تمدید نیست.")
        expires_at = body.expires_at.astimezone(timezone.utc) if body.expires_at.tzinfo else None
        issued_at = _utc_now()
        if expires_at is None or expires_at <= issued_at:
            raise HTTPException(422, "تاریخ پایان مجوز باید در آینده و دارای منطقه زمانی باشد.")
        new_id = "lic_" + secrets.token_urlsafe(18)
        modules = json.loads(old["modules_json"])
        claim = {
            "schema_version": 1,
            "license_id": new_id,
            "instance_id": old["instance_id"],
            "customer_ref": old["customer_ref"],
            "edition": old["edition"],
            "modules": modules,
            "issued_at": _iso(issued_at),
            "expires_at": _iso(expires_at),
            "offline_grace_days": body.offline_grace_days,
        }
        try:
            token = sign_license_token(claim, private_key_b64)
        except Exception as exc:
            raise HTTPException(503, "کلید امضای مرکز مجوز معتبر نیست.") from exc
        with db() as connection:
            changed = connection.execute(
                "UPDATE control_licenses SET status='superseded' WHERE id=? AND status='active'",
                (license_id,),
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "مجوز هم‌زمان تغییر کرده است؛ وضعیت را دوباره بررسی کنید.")
            connection.execute(
                """INSERT INTO control_licenses(
                    id,instance_id,customer_ref,edition,modules_json,issued_at,expires_at,
                    offline_grace_days,token_sha256,status,created_by
                ) VALUES(?,?,?,?,?,?,?,?,?,'active',?)""",
                (
                    new_id, old["instance_id"], old["customer_ref"], old["edition"],
                    json.dumps(modules), _iso(issued_at), _iso(expires_at),
                    body.offline_grace_days, hashlib.sha256(token.encode()).hexdigest(), user["id"],
                ),
            )
        audit(user["id"], "license.renewed", "license", new_id, {"supersedes": license_id})
        return {"license_id": new_id, "supersedes": license_id, "instance_id": old["instance_id"], "license_token": token}

    @api.post("/api/control/support")
    def create_support_contract(body: SupportCreateIn, user=Depends(require_scope("support:write"))):
        try:
            customer_volume_name(body.instance_id)
        except ValueError as exc:
            raise HTTPException(422, "شناسه نصب معتبر نیست.") from exc
        start = body.starts_at.astimezone(timezone.utc) if body.starts_at.tzinfo else None
        end = body.ends_at.astimezone(timezone.utc) if body.ends_at.tzinfo else None
        if not start or not end or end <= start:
            raise HTTPException(422, "بازه پشتیبانی معتبر نیست.")
        with db() as connection:
            cursor = connection.execute(
                """INSERT INTO control_support_contracts(
                    customer_ref,instance_id,plan,starts_at,ends_at,status,notes,created_by
                ) VALUES(?,?,?,?,?,'active',?,?)""",
                (
                    body.customer_ref.strip(),
                    body.instance_id,
                    body.plan.strip(),
                    _iso(start),
                    _iso(end),
                    body.notes.strip(),
                    user["id"],
                ),
            )
            contract_id = cursor.lastrowid
        audit(user["id"], "support.created", "support_contract", str(contract_id), {
            "customer_ref": body.customer_ref,
            "instance_id": body.instance_id,
            "plan": body.plan,
            "ends_at": _iso(end),
        })
        return {"support_id": contract_id, "status": "active"}

    @api.get("/api/control/support")
    def list_support(user=Depends(require_scope("support:read"))):
        with db() as connection:
            rows = connection.execute(
                """SELECT id,customer_ref,instance_id,plan,starts_at,ends_at,status,notes,created_at
                   FROM control_support_contracts ORDER BY created_at DESC,id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    @api.patch("/api/control/support/{support_id}")
    def update_support(support_id: int, body: SupportUpdateIn, user=Depends(require_scope("support:write"))):
        with db() as connection:
            row = connection.execute(
                "SELECT id FROM control_support_contracts WHERE id=?",
                (support_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "قرارداد پشتیبانی پیدا نشد.")
            connection.execute(
                "UPDATE control_support_contracts SET status=? WHERE id=?",
                (body.status, support_id),
            )
        audit(user["id"], "support.status_changed", "support_contract", str(support_id), {"status": body.status})
        return {"ok": True, "status": body.status}

    @api.get("/api/control/audit")
    def list_audit(limit: int = 100, user=Depends(require_scope("audit:read"))):
        with db() as connection:
            rows = connection.execute(
                "SELECT id,actor_id,action,target_type,target_id,details_json,created_at FROM control_audit ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "actor_id": row["actor_id"],
                "action": row["action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "details": json.loads(row["details_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    init_db()
    return api


app = create_app()
