"""Tenant-isolated smart procurement workflow for LEADORA.

Public supplier discovery and negotiation drafting are automated; external messages,
purchase commitments, goods receipt, and real-money transfers require explicit actions.
"""
import os
import re
import json
import sqlite3
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


class NeedIn(BaseModel):
    product_name: str = Field(min_length=2, max_length=180)
    sku: str = Field(default="", max_length=80)
    quantity: float = Field(gt=0, le=1_000_000)
    unit: str = Field(default="عدد", max_length=30)
    target_unit_price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="IRR", pattern="^(IRR|EUR|USD|TRY|AED)$")
    required_by: str = Field(default="", max_length=40)
    quality_spec: str = Field(default="", max_length=1500)
    delivery_city: str = Field(default="", max_length=120)


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    website: str = Field(default="", max_length=1000)
    contact_channel: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=2000)


class QuoteIn(BaseModel):
    supplier_id: int = Field(gt=0)
    need_id: int = Field(gt=0)
    unit_price: float = Field(ge=0)
    currency: str = Field(default="IRR", pattern="^(IRR|EUR|USD|TRY|AED)$")
    minimum_order_qty: float = Field(default=1, gt=0)
    delivery_days: int = Field(default=0, ge=0, le=3650)
    shipping_cost: float = Field(default=0, ge=0)
    quality_score: int = Field(default=3, ge=1, le=5)
    payment_terms: str = Field(default="", max_length=1000)
    return_terms: str = Field(default="", max_length=1000)
    source_url: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=2000)


class OrderIn(BaseModel):
    need_id: int = Field(gt=0)
    quote_id: int = Field(gt=0)
    quantity: float = Field(gt=0, le=1_000_000)
    approved_by_user: bool = False
    approval_note: str = Field(default="", max_length=1000)


class ReceiptIn(BaseModel):
    quantity_received: float = Field(gt=0, le=1_000_000)
    accepted: bool = False
    note: str = Field(default="", max_length=1000)


def install_procurement(app, db, user_from_header, ROOT):
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS procurement_needs(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
          product_name TEXT NOT NULL, sku TEXT NOT NULL DEFAULT '', quantity REAL NOT NULL CHECK(quantity>0),
          unit TEXT NOT NULL DEFAULT 'عدد', target_unit_price REAL, currency TEXT NOT NULL DEFAULT 'IRR',
          required_by TEXT NOT NULL DEFAULT '', quality_spec TEXT NOT NULL DEFAULT '',
          delivery_city TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_proc_needs_tenant_status ON procurement_needs(tenant_id,status,id);
        CREATE TABLE IF NOT EXISTS procurement_suppliers(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, name TEXT NOT NULL,
          website TEXT NOT NULL DEFAULT '', contact_channel TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '', discovery_source TEXT NOT NULL DEFAULT 'manual',
          source_url TEXT NOT NULL DEFAULT '', verification_status TEXT NOT NULL DEFAULT 'unverified',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_proc_suppliers_tenant ON procurement_suppliers(tenant_id,id);
        CREATE TABLE IF NOT EXISTS procurement_quotes(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, need_id INTEGER NOT NULL,
          supplier_id INTEGER NOT NULL, unit_price REAL NOT NULL CHECK(unit_price>=0),
          currency TEXT NOT NULL DEFAULT 'IRR', minimum_order_qty REAL NOT NULL DEFAULT 1,
          delivery_days INTEGER NOT NULL DEFAULT 0, shipping_cost REAL NOT NULL DEFAULT 0,
          quality_score INTEGER NOT NULL DEFAULT 3, payment_terms TEXT NOT NULL DEFAULT '',
          return_terms TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'received',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_proc_quotes_tenant_need ON procurement_quotes(tenant_id,need_id);
        CREATE TABLE IF NOT EXISTS procurement_orders(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, need_id INTEGER NOT NULL,
          quote_id INTEGER NOT NULL, supplier_id INTEGER NOT NULL, quantity REAL NOT NULL,
          unit_price REAL NOT NULL, shipping_cost REAL NOT NULL DEFAULT 0,
          currency TEXT NOT NULL DEFAULT 'IRR', total_amount REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'awaiting_approval',
          approval_note TEXT NOT NULL DEFAULT '', created_by INTEGER NOT NULL,
          approved_at TEXT, received_qty REAL NOT NULL DEFAULT 0,
          receipt_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_proc_orders_tenant_status ON procurement_orders(tenant_id,status,id);
        CREATE TABLE IF NOT EXISTS procurement_payment_records(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, order_id INTEGER NOT NULL,
          amount REAL NOT NULL CHECK(amount>0), currency TEXT NOT NULL DEFAULT 'IRR',
          method TEXT NOT NULL DEFAULT 'manual', reference TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'recorded_not_transferred',
          created_by INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS procurement_receipts(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, order_id INTEGER NOT NULL,
          quantity REAL NOT NULL CHECK(quantity>0), amount REAL NOT NULL CHECK(amount>0),
          currency TEXT NOT NULL DEFAULT 'IRR', journal_id INTEGER,
          accepted_by INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS idx_proc_receipts_tenant_order ON procurement_receipts(tenant_id,order_id,id);
        """)

    def tenant_row(table, row_id, tenant_id, columns="*"):
        with db() as c:
            row = c.execute(f"SELECT {columns} FROM {table} WHERE id=? AND tenant_id=?", (row_id, tenant_id)).fetchone()
        if not row:
            raise HTTPException(404, "رکورد پیدا نشد یا به این شرکت تعلق ندارد.")
        return dict(row)

    @app.get("/procurement")
    def procurement_page():
        return FileResponse(ROOT / "static" / "procurement.html")

    @app.get("/api/procurement/status")
    def procurement_status(u=Depends(user_from_header)):
        return {
            "supplier_web_search_configured": bool(os.getenv("TAVILY_API_KEY", "").strip()),
            "supported_currencies": ["IRR", "EUR", "USD", "TRY", "AED"],
            "automated_external_messages": False,
            "real_bank_transfer_enabled": False,
            "features": ["need-planning", "public-supplier-discovery", "quote-comparison",
                         "negotiation-drafts", "purchase-orders", "receipt-control", "payment-ledger"],
            "message": "کشف عمومی فروشنده در صورت تنظیم سرویس جست‌وجو فعال است. ارسال پیام، تعهد خرید و انتقال وجه واقعی خودکار نیست."
        }

    @app.post("/api/procurement/needs")
    def create_need(body: NeedIn, u=Depends(user_from_header)):
        with db() as c:
            cur = c.execute("""INSERT INTO procurement_needs
              (tenant_id,user_id,product_name,sku,quantity,unit,target_unit_price,currency,required_by,quality_spec,delivery_city)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (u["tenant_id"],u["id"],body.product_name.strip(),body.sku.strip(),body.quantity,body.unit,
               body.target_unit_price,body.currency,body.required_by.strip(),body.quality_spec.strip(),body.delivery_city.strip()))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (u["tenant_id"],"procurement.need.created"))
            need_id = cur.lastrowid
        return tenant_row("procurement_needs", need_id, u["tenant_id"])

    @app.get("/api/procurement/needs")
    def list_needs(u=Depends(user_from_header)):
        with db() as c:
            rows = c.execute("SELECT * FROM procurement_needs WHERE tenant_id=? ORDER BY id DESC LIMIT 200", (u["tenant_id"],)).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/procurement/suppliers")
    def create_supplier(body: SupplierIn, u=Depends(user_from_header)):
        website = body.website.strip()
        if website and not re.match(r"^https?://[^\s]+$", website, re.I):
            raise HTTPException(422, "نشانی وب باید با http:// یا https:// شروع شود.")
        with db() as c:
            if website and c.execute("SELECT 1 FROM procurement_suppliers WHERE tenant_id=? AND website=?", (u["tenant_id"],website)).fetchone():
                raise HTTPException(409, "این وب‌سایت قبلاً برای این شرکت ثبت شده است.")
            try:
                cur = c.execute("""INSERT INTO procurement_suppliers
                  (tenant_id,name,website,contact_channel,notes,discovery_source,source_url)
                  VALUES(?,?,?,?,?,'manual',?)""",
                  (u["tenant_id"],body.name.strip(),website,body.contact_channel.strip(),body.notes.strip(),website))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "این وب‌سایت قبلاً برای این شرکت ثبت شده است.")
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (u["tenant_id"],"procurement.supplier.created"))
            supplier_id = cur.lastrowid
        return tenant_row("procurement_suppliers", supplier_id, u["tenant_id"])

    @app.get("/api/procurement/suppliers")
    def list_suppliers(u=Depends(user_from_header)):
        with db() as c:
            rows = c.execute("SELECT * FROM procurement_suppliers WHERE tenant_id=? ORDER BY id DESC LIMIT 300", (u["tenant_id"],)).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/procurement/discover")
    def discover_suppliers(need_id: int, limit: int = 10, u=Depends(user_from_header)):
        if limit < 1 or limit > 20:
            raise HTTPException(422, "تعداد نتایج باید بین ۱ تا ۲۰ باشد.")
        need = tenant_row("procurement_needs", need_id, u["tenant_id"])
        if not os.getenv("TAVILY_API_KEY", "").strip():
            return {"provider": "query_generation_only", "results": [], "search_configured": False,
                    "queries": [f"{need['product_name']} عمده فروش تامین کننده تولیدکننده {need['delivery_city']}".strip(),
                                f"{need['product_name']} supplier manufacturer wholesale {need['delivery_city']}".strip()],
                    "message": "برای جست‌وجوی آنلاین باید TAVILY_API_KEY در محیط امن سرور تنظیم شود؛ عبارت‌ها آماده شده‌اند."}
        from app.lead_discovery import _search_tavily
        query = f"{need['product_name']} supplier manufacturer wholesale {need['delivery_city']} {need['quality_spec']}".strip()
        results = _search_tavily(query, limit)
        saved = []
        with db() as c:
            for item in (results or []):
                url = str(item.get("url", ""))[:1000]
                name = str(item.get("name", "")).strip()[:200] or url
                if not re.match(r"^https?://", url, re.I):
                    continue
                exists = c.execute("SELECT id FROM procurement_suppliers WHERE tenant_id=? AND website=?", (u["tenant_id"],url)).fetchone()
                if exists:
                    saved.append({"id": exists["id"], "name": name, "website": url, "existing": True})
                    continue
                cur = c.execute("""INSERT INTO procurement_suppliers
                  (tenant_id,name,website,notes,discovery_source,source_url,verification_status)
                  VALUES(?,?,?,?,'public_web_search',?,'unverified')""",
                  (u["tenant_id"],name,url,str(item.get("summary",""))[:1800],url))
                saved.append({"id": cur.lastrowid, "name": name, "website": url, "existing": False})
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (u["tenant_id"],"procurement.supplier.discovery"))
        return {"provider": "Tavily", "search_configured": True, "results": saved,
                "message": "فروشندگان کشف‌شده هنوز تأیید نشده‌اند؛ قبل از سفارش، هویت، شرایط و اعتبار را بررسی کنید."}

    @app.post("/api/procurement/quotes")
    def create_quote(body: QuoteIn, u=Depends(user_from_header)):
        tenant_row("procurement_needs", body.need_id, u["tenant_id"])
        tenant_row("procurement_suppliers", body.supplier_id, u["tenant_id"])
        with db() as c:
            cur = c.execute("""INSERT INTO procurement_quotes
              (tenant_id,need_id,supplier_id,unit_price,currency,minimum_order_qty,delivery_days,shipping_cost,
               quality_score,payment_terms,return_terms,source_url,notes)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (u["tenant_id"],body.need_id,body.supplier_id,body.unit_price,body.currency,body.minimum_order_qty,
               body.delivery_days,body.shipping_cost,body.quality_score,body.payment_terms.strip(),
               body.return_terms.strip(),body.source_url.strip(),body.notes.strip()))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (u["tenant_id"],"procurement.quote.created"))
            quote_id = cur.lastrowid
        return tenant_row("procurement_quotes", quote_id, u["tenant_id"])

    @app.get("/api/procurement/quotes")
    def list_quotes(need_id: int, u=Depends(user_from_header)):
        tenant_row("procurement_needs", need_id, u["tenant_id"])
        with db() as c:
            rows = c.execute("""SELECT q.*,s.name supplier_name,s.website supplier_website
              FROM procurement_quotes q JOIN procurement_suppliers s ON s.id=q.supplier_id AND s.tenant_id=q.tenant_id
              WHERE q.tenant_id=? AND q.need_id=? ORDER BY q.created_at DESC""", (u["tenant_id"],need_id)).fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/procurement/needs/{need_id}/compare")
    def compare_quotes(need_id: int, u=Depends(user_from_header)):
        need = tenant_row("procurement_needs", need_id, u["tenant_id"])
        with db() as c:
            rows = c.execute("""SELECT q.*,s.name supplier_name,s.website supplier_website,s.verification_status
              FROM procurement_quotes q JOIN procurement_suppliers s ON s.id=q.supplier_id AND s.tenant_id=q.tenant_id
              WHERE q.tenant_id=? AND q.need_id=?""", (u["tenant_id"],need_id)).fetchall()
        quotes = [dict(r) for r in rows]
        for q in quotes:
            q["estimated_total"] = round(q["unit_price"] * max(need["quantity"],q["minimum_order_qty"]) + q["shipping_cost"], 2)
            q["score"] = round(100 * (0.55 / (1 + q["unit_price"] / max(min([x["unit_price"] for x in quotes], default=1),1))
                + 0.20 * q["quality_score"]/5 + 0.15/(1+q["delivery_days"]/7)
                + 0.10 * (1 if q["verification_status"]=="verified" else 0.5)), 2) if quotes else 0
        quotes.sort(key=lambda q: (-q["score"],q["estimated_total"]))
        return {"need": need, "quotes": quotes,
                "note": "امتیاز، برآورد اولیه است؛ ارزها فقط در صورت یکسان بودن قابل مقایسه‌اند و تأیید کیفیت/اعتبار همچنان لازم است."}

    @app.get("/api/procurement/quotes/{quote_id}/negotiation-draft")
    def negotiation_draft(quote_id: int, u=Depends(user_from_header)):
        q = tenant_row("procurement_quotes", quote_id, u["tenant_id"])
        need = tenant_row("procurement_needs", q["need_id"], u["tenant_id"])
        supplier = tenant_row("procurement_suppliers", q["supplier_id"], u["tenant_id"])
        target = need["target_unit_price"]
        if target is None:
            target = round(q["unit_price"] * 0.95, 2)
        draft = (f"سلام و وقت بخیر،\nبرای تأمین {need['product_name']} به تعداد {need['quantity']} {need['unit']} قصد همکاری داریم. "
                 f"قیمت پیشنهادی ثبت‌شده شما {q['unit_price']:,.2f} {q['currency']} است. "
                 f"لطفاً بهترین قیمت عمده، تخفیف حجمی، حداقل سفارش، زمان تحویل، هزینه حمل، ضمانت اصالت/کیفیت، شرایط مرجوعی "
                 f"و شرایط پرداخت را اعلام فرمایید. هدف اولیه ما حدود {target:,.2f} {need['currency']} برای هر واحد است؛ "
                 "این عدد صرفاً پیشنهاد مذاکره است و تعهد خرید محسوب نمی‌شود. با تشکر.")
        return {"supplier": supplier["name"], "channel": supplier["contact_channel"], "draft": draft,
                "sent": False, "message": "پیش‌نویس آماده است؛ ارسال پیام هنوز انجام نشده است."}

    @app.post("/api/procurement/orders")
    def create_order(body: OrderIn, u=Depends(user_from_header)):
        if not body.approved_by_user:
            raise HTTPException(409, "برای ایجاد سفارش خرید، تأیید صریح کاربر لازم است.")
        need = tenant_row("procurement_needs", body.need_id, u["tenant_id"])
        quote = tenant_row("procurement_quotes", body.quote_id, u["tenant_id"])
        if quote["need_id"] != need["id"]:
            raise HTTPException(422, "پیشنهاد قیمت متعلق به این نیاز خرید نیست.")
        if body.quantity < quote["minimum_order_qty"]:
            raise HTTPException(422, "تعداد سفارش کمتر از حداقل سفارش فروشنده است.")
        if quote["currency"] != need["currency"]:
            raise HTTPException(422, "ارز پیشنهاد با ارز نیاز خرید یکسان نیست؛ تبدیل ارز تأییدشده لازم است.")
        total = round(body.quantity * quote["unit_price"] + quote["shipping_cost"], 2)
        if need["target_unit_price"] is not None and quote["unit_price"] > need["target_unit_price"] and not body.approval_note.strip():
            raise HTTPException(409, "قیمت از سقف هدف بیشتر است؛ دلیل تأیید مالک/کاربر را ثبت کنید.")
        with db() as c:
            cur = c.execute("""INSERT INTO procurement_orders
              (tenant_id,need_id,quote_id,supplier_id,quantity,unit_price,shipping_cost,currency,total_amount,
               status,approval_note,created_by,approved_at)
              VALUES(?,?,?,?,?,?,?,?,?,'approved_for_supplier_confirmation',?,?,?)""",
              (u["tenant_id"],need["id"],quote["id"],quote["supplier_id"],body.quantity,quote["unit_price"],
               quote["shipping_cost"],quote["currency"],total,body.approval_note.strip(),u["id"],datetime.now(timezone.utc).isoformat()))
            c.execute("UPDATE procurement_needs SET status='order_created' WHERE id=? AND tenant_id=?", (need["id"],u["tenant_id"]))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (u["tenant_id"],"procurement.order.approved"))
            order_id = cur.lastrowid
        order = tenant_row("procurement_orders", order_id, u["tenant_id"])
        order["message"] = "سفارش داخلی ثبت شد؛ این ثبت به معنی ارسال سفارش به فروشنده یا انتقال وجه نیست."
        return order

    @app.get("/api/procurement/orders")
    def list_orders(u=Depends(user_from_header)):
        with db() as c:
            rows = c.execute("""SELECT o.*,s.name supplier_name,n.product_name FROM procurement_orders o
              JOIN procurement_suppliers s ON s.id=o.supplier_id AND s.tenant_id=o.tenant_id
              JOIN procurement_needs n ON n.id=o.need_id AND n.tenant_id=o.tenant_id
              WHERE o.tenant_id=? ORDER BY o.id DESC LIMIT 200""", (u["tenant_id"],)).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/procurement/orders/{order_id}/receipt")
    def receive_order(order_id: int, body: ReceiptIn, u=Depends(user_from_header)):
        order = tenant_row("procurement_orders", order_id, u["tenant_id"])
        if not body.accepted:
            raise HTTPException(409, "برای ثبت ورود انبار، تأیید صریح پذیرش کالا لازم است.")
        if body.quantity_received + order["received_qty"] > order["quantity"]:
            raise HTTPException(422, "مقدار دریافتی از مقدار سفارش بیشتر است.")
        need = tenant_row("procurement_needs", order["need_id"], u["tenant_id"])
        # Procurement ledger amounts are currently native-currency values; only IRR can be
        # posted to the base ledger until a controlled FX-rate/valuation module exists.
        receipt_amount = round(body.quantity_received * order["unit_price"] +
                                order["shipping_cost"] * body.quantity_received / order["quantity"], 2)
        with db() as c:
            received = order["received_qty"] + body.quantity_received
            status = "received" if received == order["quantity"] else "partially_received"
            c.execute("UPDATE procurement_orders SET received_qty=?,status=?,receipt_note=? WHERE id=? AND tenant_id=?",
                      (received,status,body.note.strip(),order_id,u["tenant_id"]))
            c.execute("UPDATE procurement_needs SET status=? WHERE id=? AND tenant_id=?",
                      ("fulfilled" if status=="received" else "partially_received",order["need_id"],u["tenant_id"]))
            product = None
            if need["sku"]:
                product = c.execute("SELECT id FROM products WHERE tenant_id=? AND sku=?", (u["tenant_id"],need["sku"])).fetchone()
                if product:
                    c.execute("UPDATE products SET stock=stock+? WHERE id=? AND tenant_id=?", (body.quantity_received,product["id"],u["tenant_id"]))
            cur = c.execute("""INSERT INTO procurement_receipts
              (tenant_id,order_id,quantity,amount,currency,accepted_by,note)
              VALUES(?,?,?,?,?,?,?)""",
              (u["tenant_id"],order_id,body.quantity_received,receipt_amount,order["currency"],u["id"],body.note.strip()))
            receipt_id = cur.lastrowid
            journal = None
            if order["currency"] == "IRR":
                # Receipt is automatically journaled as a DRAFT. Posting requires the company's
                # normal accounting approval workflow. No supplier payment is initiated here.
                count = c.execute("SELECT COUNT(*)+1 n FROM gl_journals WHERE tenant_id=?", (u["tenant_id"],)).fetchone()["n"]
                journal_no = f"GL-{u['tenant_id']}-{count:06d}"
                source_ref = f"procurement-receipt-{receipt_id}"
                journal_cur = c.execute("""INSERT INTO gl_journals
                  (tenant_id,journal_no,journal_date,description,source_type,source_ref,status,created_by)
                  VALUES(?,?,?,?,? ,?,'draft',?)""",
                  (u["tenant_id"],journal_no,datetime.now(timezone.utc).date().isoformat(),
                   f"ورود خرید کالا - سفارش {order_id} - رسید {receipt_id}","receipt",source_ref,u["id"]))
                journal_id = journal_cur.lastrowid
                c.execute("""INSERT INTO gl_lines
                  (tenant_id,journal_id,line_no,account_code,memo,debit,credit,party_name)
                  VALUES(?,?,?,?,?,?,?,?)""",
                  (u["tenant_id"],journal_id,1,"1200","موجودی کالای دریافتی",f"{receipt_amount:.2f}","0.00",""))
                c.execute("""INSERT INTO gl_lines
                  (tenant_id,journal_id,line_no,account_code,memo,debit,credit,party_name)
                  VALUES(?,?,?,?,?,?,?,?,?)""".replace("VALUES(?,?,?,?,?,?,?,?,?)","VALUES(?,?,?,?,?,?,?,?,?)"),
                  (u["tenant_id"],journal_id,2,"2000","حساب پرداختنی تأمین‌کننده","0.00",f"{receipt_amount:.2f}",""))
                c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (u["tenant_id"],"accounting.journal.draft:"+journal_no))
                c.execute("UPDATE procurement_receipts SET journal_id=? WHERE id=? AND tenant_id=?", (journal_id,receipt_id,u["tenant_id"]))
                journal = {"id":journal_id,"journal_no":journal_no,"status":"draft","amount":receipt_amount}
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (u["tenant_id"],"procurement.receipt.accepted"))
        return {"order_id":order_id,"receipt_id":receipt_id,"received_qty":received,"status":status,
                "receipt_amount":receipt_amount,"currency":order["currency"],
                "inventory_stock_updated":bool(product),
                "accounting_journal":journal,
                "message":"ورود کالا ثبت شد. برای ریال، پیش‌نویس سند موجودی/حساب پرداختنی ساخته شد و نیازمند تأیید حسابداری است."
                if journal else "ورود کالا ثبت شد؛ برای ارز غیرریالی، ثبت حسابداری تا تعیین نرخ تبدیل تأییدشده ایجاد نشد."}

    @app.get("/api/procurement/orders/{order_id}/receipts")
    def list_receipts(order_id: int, u=Depends(user_from_header)):
        tenant_row("procurement_orders", order_id, u["tenant_id"])
        with db() as c:
            rows = c.execute("""SELECT r.id,r.order_id,r.quantity,r.amount,r.currency,r.journal_id,
              r.accepted_by,r.note,r.created_at,j.journal_no,j.status journal_status
              FROM procurement_receipts r LEFT JOIN gl_journals j
              ON j.id=r.journal_id AND j.tenant_id=r.tenant_id
              WHERE r.tenant_id=? AND r.order_id=? ORDER BY r.id DESC""",
              (u["tenant_id"],order_id)).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/procurement/orders/{order_id}/payments")
    def record_payment(order_id: int, amount: float, reference: str = "", u=Depends(user_from_header)):
        if amount <= 0:
            raise HTTPException(422, "مبلغ پرداخت باید بیشتر از صفر باشد.")
        order = tenant_row("procurement_orders", order_id, u["tenant_id"])
        with db() as c:
            cur = c.execute("""INSERT INTO procurement_payment_records
              (tenant_id,order_id,amount,currency,method,reference,status,created_by)
              VALUES(?,?,?,?,'manual',?,'recorded_not_transferred',?)""",
              (u["tenant_id"],order_id,amount,order["currency"],reference.strip()[:200],u["id"]))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)", (u["tenant_id"],"procurement.payment.recorded"))
        return {"id":cur.lastrowid,"order_id":order_id,"amount":amount,"currency":order["currency"],
                "status":"recorded_not_transferred","real_transfer":False,
                "message":"پرداخت به‌عنوان ثبت دستی ثبت شد؛ هیچ انتقال وجه واقعی انجام نشده است."}

    @app.get("/api/procurement/orders/{order_id}/payments")
    def list_payments(order_id: int, u=Depends(user_from_header)):
        tenant_row("procurement_orders", order_id, u["tenant_id"])
        with db() as c:
            rows = c.execute("SELECT id,order_id,amount,currency,method,reference,status,created_at FROM procurement_payment_records WHERE tenant_id=? AND order_id=? ORDER BY id DESC",
                             (u["tenant_id"],order_id)).fetchall()
        return [dict(r) for r in rows]
