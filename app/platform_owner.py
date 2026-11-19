"""Platform-owner identity routes kept separate from retired participation finance.

This module preserves the owner claim/recovery contract without exposing the
legacy contract, entries, reports, or settlement API under /api/finance.
"""
import hmac
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


def owner_user_ids():
    return {
        value.strip()
        for value in os.getenv("LEADORA_OWNER_USER_IDS", "").split(",")
        if value.strip()
    }


def create_router(db_factory, user_dependency):
    router = APIRouter(prefix="/api/finance", tags=["platform-owner-identity"])

    # These two tables pre-date this router and are retained for compatibility.
    # CREATE IF NOT EXISTS preserves any existing owner record and audit history.
    with db_factory() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS finance_platform_owner(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          user_id TEXT NOT NULL UNIQUE,
          email TEXT NOT NULL DEFAULT '',
          claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS finance_audit(
          id INTEGER PRIMARY KEY,
          tenant_id INTEGER NOT NULL,
          actor_email TEXT NOT NULL,
          action TEXT NOT NULL,
          details_json TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

    def is_owner(user):
        user_id = str(user.get("id", ""))
        if user_id and user_id in owner_user_ids():
            return True
        if not user_id:
            return False
        with db_factory() as conn:
            row = conn.execute(
                "SELECT user_id FROM finance_platform_owner WHERE singleton=1"
            ).fetchone()
        return bool(row and str(row["user_id"]) == user_id)

    def audit(conn, user, action, details):
        import json

        conn.execute(
            "INSERT INTO finance_audit(tenant_id,actor_email,action,details_json) VALUES(?,?,?,?)",
            (
                int(user.get("tenant_id", 0)),
                str(user.get("email", "")),
                action,
                json.dumps(details, ensure_ascii=False, default=str),
            ),
        )

    class OwnerClaimIn(BaseModel):
        token: str = Field(min_length=32, max_length=256)

    @router.get("/identity")
    def identity(user=Depends(user_dependency)):
        return {
            "user_id": user["id"],
            "tenant_id": user["tenant_id"],
            "email": user.get("email", ""),
            "is_platform_owner": is_owner(user),
        }

    @router.post("/owner/claim")
    def claim_owner(body: OwnerClaimIn, user=Depends(user_dependency)):
        expected = os.getenv("LEADORA_OWNER_BOOTSTRAP_TOKEN", "")
        if not expected:
            raise HTTPException(503, "فرایند ثبت مالک از سمت سرور فعال نشده است.")
        if owner_user_ids():
            raise HTTPException(
                409,
                "مالک سامانه از طریق تنظیمات امن سرور تعیین شده است؛ ثبت مالک جدید مجاز نیست.",
            )
        if not hmac.compare_digest(body.token, expected):
            raise HTTPException(403, "رمز یک‌بارمصرف مالک معتبر نیست.")
        expected_email = os.getenv("LEADORA_OWNER_BOOTSTRAP_EMAIL", "").strip().casefold()
        account_email = str(user.get("email", "")).strip().casefold()
        if expected_email and account_email != expected_email:
            raise HTTPException(403, "این حساب با ایمیل مجاز مالک مطابقت ندارد.")
        user_id = str(user.get("id", ""))
        if not user_id:
            raise HTTPException(400, "شناسه حساب معتبر نیست.")

        with db_factory() as conn:
            existing = conn.execute(
                "SELECT user_id FROM finance_platform_owner WHERE singleton=1"
            ).fetchone()
            if existing:
                if str(existing["user_id"]) == user_id:
                    return {
                        "ok": True,
                        "is_platform_owner": True,
                        "message": "این حساب قبلاً به‌عنوان مالک ثبت شده است.",
                    }
                raise HTTPException(409, "مالک سامانه قبلاً ثبت شده است؛ ثبت مجدد مسدود است.")
            try:
                conn.execute(
                    "INSERT INTO finance_platform_owner(singleton,user_id,email) VALUES(1,?,?)",
                    (user_id, user.get("email", "")),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(409, "ثبت مالک هم‌زمان انجام شده است؛ صفحه را تازه‌سازی کنید.")
            audit(conn, user, "platform.owner.claimed", {"user_id": user_id})

        return {
            "ok": True,
            "is_platform_owner": True,
            "message": "مالک سامانه با موفقیت ثبت شد.",
        }

    @router.post("/owner/recover")
    def recover_owner(body: OwnerClaimIn, user=Depends(user_dependency)):
        expected = os.getenv("LEADORA_OWNER_RECOVERY_TOKEN", "").strip()
        expected_email = os.getenv("LEADORA_OWNER_RECOVERY_EMAIL", "").strip().casefold()
        bootstrap_token = os.getenv("LEADORA_OWNER_BOOTSTRAP_TOKEN", "").strip()
        if len(expected) < 32 or not expected_email or hmac.compare_digest(expected, bootstrap_token):
            raise HTTPException(503, "بازیابی امن مالک در تنظیمات سرور فعال نشده است.")
        if owner_user_ids():
            raise HTTPException(
                409,
                "مالک از طریق تنظیمات امن شناسه کاربر تعیین شده است؛ بازیابی از پنل مجاز نیست.",
            )
        if not hmac.compare_digest(body.token, expected):
            raise HTTPException(403, "کلید بازیابی مالک معتبر نیست.")
        account_email = str(user.get("email", "")).strip().casefold()
        if account_email != expected_email:
            raise HTTPException(403, "ایمیل حساب با ایمیل مجاز بازیابی مالک مطابقت ندارد.")
        user_id = str(user.get("id", ""))
        if not user_id:
            raise HTTPException(400, "شناسه حساب معتبر نیست.")

        with db_factory() as conn:
            existing = conn.execute(
                "SELECT user_id,email FROM finance_platform_owner WHERE singleton=1"
            ).fetchone()
            if not existing:
                raise HTTPException(
                    409,
                    "مالک ثبت‌شده‌ای برای بازیابی وجود ندارد؛ از فرایند ثبت اولیه مالک استفاده کنید.",
                )
            previous_user_id = str(existing["user_id"])
            if previous_user_id == user_id:
                return {
                    "ok": True,
                    "is_platform_owner": True,
                    "message": "این حساب از قبل مالک اصلی سامانه است.",
                }
            conn.execute(
                "UPDATE finance_platform_owner SET user_id=?,email=?,claimed_at=CURRENT_TIMESTAMP WHERE singleton=1",
                (user_id, account_email),
            )
            audit(
                conn,
                user,
                "platform.owner.recovered",
                {
                    "previous_user_id": previous_user_id,
                    "previous_email": str(existing["email"]),
                    "new_user_id": user_id,
                    "new_email": account_email,
                    "method": "server_configured_recovery",
                },
            )

        return {
            "ok": True,
            "is_platform_owner": True,
            "message": "دسترسی مالک اصلی با تأیید امن بازیابی شد.",
        }

    return router
