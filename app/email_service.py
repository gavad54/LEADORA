"""Minimal, synchronous Brevo transactional-email adapter.

Secrets are read only from the process environment. This module never logs
recipient addresses, message bodies, API keys, or provider response bodies.
"""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class EmailDeliveryError(RuntimeError):
    """Safe-to-display email delivery failure without provider secrets."""


def email_service_status():
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "").strip().lower()
    sender_name = os.getenv("BREVO_SENDER_NAME", "LEADORA").strip() or "LEADORA"
    return {
        "provider": "brevo",
        "configured": bool(api_key and sender_email and EMAIL_RE.fullmatch(sender_email)),
        "api_key_configured": bool(api_key),
        "sender_configured": bool(sender_email and EMAIL_RE.fullmatch(sender_email)),
        "sender_name_configured": bool(sender_name),
    }


def send_transactional_email(recipient, subject, text_content, html_content=None, tags=None):
    """Send one transactional email and return the provider message ID."""
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "").strip().lower()
    sender_name = os.getenv("BREVO_SENDER_NAME", "LEADORA").strip() or "LEADORA"

    if not api_key or not sender_email or not EMAIL_RE.fullmatch(sender_email):
        raise EmailDeliveryError("تنظیمات سرویس ایمیل کامل نیست.")
    if not isinstance(recipient, str) or not EMAIL_RE.fullmatch(recipient.strip()):
        raise EmailDeliveryError("نشانی گیرنده معتبر نیست.")
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 180:
        raise EmailDeliveryError("موضوع ایمیل معتبر نیست.")
    if not isinstance(text_content, str) or not text_content.strip() or len(text_content) > 12000:
        raise EmailDeliveryError("متن ایمیل معتبر نیست.")
    if html_content is not None and (not isinstance(html_content, str) or len(html_content) > 30000):
        raise EmailDeliveryError("محتوای HTML ایمیل معتبر نیست.")

    payload = {
        "sender": {"name": sender_name[:80], "email": sender_email},
        "to": [{"email": recipient.strip().lower()}],
        "subject": subject.strip(),
        "textContent": text_content,
        "tags": ["leadora-transactional", *(tags or [])][:10],
    }
    if html_content:
        payload["htmlContent"] = html_content

    request = Request(
        BREVO_SEND_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        # Provider details can contain private data; expose only a generic error.
        raise EmailDeliveryError("ارسال ایمیل انجام نشد؛ تنظیمات فرستنده و گزارش سرویس را بررسی کنید.") from None

    message_id = result.get("messageId") if isinstance(result, dict) else None
    if not isinstance(message_id, str) or not message_id.strip():
        raise EmailDeliveryError("پاسخ سرویس ایمیل قابل تأیید نیست.")
    return message_id
