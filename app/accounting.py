"""Additive tenant-isolated double-entry accounting for LEADORA."""
import sqlite3, csv, io
from datetime import date
from decimal import Decimal
from pathlib import Path
from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

SEED = [
("1000","صندوق","asset","debit"),("1010","بانک","asset","debit"),
("1100","حساب‌های دریافتنی","asset","debit"),("1200","موجودی کالا","asset","debit"),
("1500","دارایی ثابت","asset","debit"),("2000","حساب‌های پرداختنی","liability","credit"),
("2100","مالیات پرداختنی","liability","credit"),("2200","حقوق پرداختنی","liability","credit"),
("3000","سرمایه","equity","credit"),("3100","سود و زیان انباشته","equity","credit"),
("4000","فروش","revenue","credit"),("4100","درآمد خدمات","revenue","credit"),
("5000","بهای تمام‌شده","expense","debit"),("6000","هزینه حقوق","expense","debit"),
("6100","هزینه اجاره","expense","debit"),("6200","هزینه حمل","expense","debit"),
("6300","سایر هزینه‌ها","expense","debit")]

class AccountIn(BaseModel):
    code:str=Field(min_length=3,max_length=20,pattern=r"^[A-Za-z0-9._-]+$")
    name:str=Field(min_length=2,max_length=160)
    account_type:str=Field(pattern=r"^(asset|liability|equity|revenue|expense)$")
    normal_side:str=Field(pattern=r"^(debit|credit)$")
    parent_code:str=Field(default="",max_length=20)

class LineIn(BaseModel):
    account_code:str=Field(min_length=3,max_length=20)
    debit:Decimal=Field(default=Decimal("0"),ge=0,max_digits=18,decimal_places=2)
    credit:Decimal=Field(default=Decimal("0"),ge=0,max_digits=18,decimal_places=2)
    memo:str=Field(default="",max_length=240)
    party_name:str=Field(default="",max_length=160)
    @model_validator(mode="after")
    def one_side(self):
        if (self.debit>0)==(self.credit>0): raise ValueError("هر ردیف باید دقیقاً بدهکار یا بستانکار باشد.")
        return self

class JournalIn(BaseModel):
    journal_date:date
    description:str=Field(min_length=3,max_length=240)
    source_type:str=Field(default="manual",pattern=r"^(manual|sales|purchase|receipt|payment|payroll|adjustment|import)$")
    source_ref:str=Field(default="",max_length=100)
    lines:list[LineIn]=Field(min_length=2,max_length=100)
    @model_validator(mode="after")
    def balanced(self):
        if sum((x.debit for x in self.lines),Decimal(0))<=0 or sum((x.debit for x in self.lines),Decimal(0))!=sum((x.credit for x in self.lines),Decimal(0)):
            raise ValueError("سند باید تراز باشد؛ جمع بدهکار و بستانکار باید برابر و مثبت باشد.")
        return self

class QuickVoucher(BaseModel):
    journal_date:date
    document_ref:str=Field(min_length=1,max_length=100)
    party:str=Field(default="",max_length=160)
    amount:Decimal=Field(gt=0,max_digits=18,decimal_places=2)
    account_code:str=Field(default="",max_length=20)
    description:str=Field(default="ثبت پیشنهادی خودکار",max_length=240)

class CSVImportIn(BaseModel):
    content:str=Field(min_length=1,max_length=2_000_000)

def install_accounting(app, db, user_from_header, root:Path):
    def seed(c,tid):
        c.execute("INSERT OR IGNORE INTO gl_automation_settings(tenant_id) VALUES(?)",(tid,))
        for row in SEED:c.execute("INSERT OR IGNORE INTO gl_accounts(tenant_id,code,name,account_type,normal_side) VALUES(?,?,?,?,?)",(tid,*row))
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS gl_accounts(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),code TEXT NOT NULL,name TEXT NOT NULL,account_type TEXT NOT NULL CHECK(account_type IN ('asset','liability','equity','revenue','expense')),normal_side TEXT NOT NULL CHECK(normal_side IN ('debit','credit')),parent_code TEXT NOT NULL DEFAULT '',is_active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(tenant_id,code));
        CREATE TABLE IF NOT EXISTS gl_journals(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),journal_no TEXT NOT NULL,journal_date TEXT NOT NULL,description TEXT NOT NULL,source_type TEXT NOT NULL DEFAULT 'manual',source_ref TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','posted','void')),created_by INTEGER NOT NULL,posted_at TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(tenant_id,journal_no));
        CREATE UNIQUE INDEX IF NOT EXISTS idx_gl_source_unique ON gl_journals(tenant_id,source_type,source_ref) WHERE source_ref<>'';
        CREATE TABLE IF NOT EXISTS gl_lines(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL REFERENCES tenants(id),journal_id INTEGER NOT NULL REFERENCES gl_journals(id),line_no INTEGER NOT NULL,account_code TEXT NOT NULL,memo TEXT NOT NULL DEFAULT '',debit TEXT NOT NULL DEFAULT '0.00',credit TEXT NOT NULL DEFAULT '0.00',party_name TEXT NOT NULL DEFAULT '',UNIQUE(journal_id,line_no));
        CREATE INDEX IF NOT EXISTS idx_gl_journal_date ON gl_journals(tenant_id,journal_date,status);
        CREATE TABLE IF NOT EXISTS gl_automation_settings(tenant_id INTEGER PRIMARY KEY REFERENCES tenants(id),suggest_sales INTEGER NOT NULL DEFAULT 1,suggest_expenses INTEGER NOT NULL DEFAULT 1,duplicate_check INTEGER NOT NULL DEFAULT 1,require_approval INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        for t in c.execute("SELECT id FROM tenants").fetchall():
            seed(c,t["id"])
    def amount(n):return format(Decimal(str(n)).quantize(Decimal("0.01")),".2f")
    def make_journal(c,u,p):
        tid=u["tenant_id"];seed(c,tid)
        if p.source_ref:
            old=c.execute("SELECT journal_no FROM gl_journals WHERE tenant_id=? AND source_type=? AND source_ref=?",(tid,p.source_type,p.source_ref)).fetchone()
            if old:raise HTTPException(409,"برای این مرجع قبلاً سند ثبت شده است.")
        valid={r["code"] for r in c.execute("SELECT code FROM gl_accounts WHERE tenant_id=? AND is_active=1",(tid,))}
        missing={x.account_code for x in p.lines}-valid
        if missing:raise HTTPException(422,"کد حساب نامعتبر است: "+", ".join(sorted(missing)))
        d=sum((x.debit for x in p.lines),Decimal(0));cr=sum((x.credit for x in p.lines),Decimal(0))
        if d<=0 or d!=cr:raise HTTPException(422,"سند تراز نیست.")
        n=c.execute("SELECT COUNT(*)+1 n FROM gl_journals WHERE tenant_id=?",(tid,)).fetchone()["n"]
        no=f"GL-{tid}-{n:06d}"
        cur=c.execute("INSERT INTO gl_journals(tenant_id,journal_no,journal_date,description,source_type,source_ref,status,created_by) VALUES(?,?,?,?,?,?,?,?)",(tid,no,p.journal_date.isoformat(),p.description,p.source_type,p.source_ref,"draft",u["id"]))
        jid=cur.lastrowid
        for i,x in enumerate(p.lines,1):
            c.execute("INSERT INTO gl_lines(tenant_id,journal_id,line_no,account_code,memo,debit,credit,party_name) VALUES(?,?,?,?,?,?,?,?)",(tid,jid,i,x.account_code,x.memo,amount(x.debit),amount(x.credit),x.party_name))
        c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"accounting.journal.draft:"+no))
        settings=c.execute("SELECT require_approval FROM gl_automation_settings WHERE tenant_id=?",(tid,)).fetchone()
        status="draft"
        if settings and not settings["require_approval"] and p.source_type in ("sales","purchase","receipt","payment","import"):
            c.execute("UPDATE gl_journals SET status='posted',posted_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",(jid,tid))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"accounting.journal.auto_post:"+no))
            status="posted"
        return {"id":jid,"journal_no":no,"status":status,"debit_total":amount(d),"credit_total":amount(cr)}
    @app.get("/accounting")
    def accounting_page():return FileResponse(root/"static"/"accounting.html")
    @app.get("/api/accounting/overview")
    def overview(u=Depends(user_from_header)):
        with db() as c:
            seed(c,u["tenant_id"])
            s=c.execute("SELECT SUM(status='draft') drafts,SUM(status='posted') posted FROM gl_journals WHERE tenant_id=?",(u["tenant_id"],)).fetchone()
            b=c.execute("SELECT COALESCE(SUM(CAST(l.debit AS REAL)),0) d,COALESCE(SUM(CAST(l.credit AS REAL)),0) cr FROM gl_lines l JOIN gl_journals j ON j.id=l.journal_id AND j.tenant_id=l.tenant_id WHERE l.tenant_id=? AND j.status='posted'",(u["tenant_id"],)).fetchone()
            return {"drafts":s["drafts"] or 0,"posted":s["posted"] or 0,"posted_debit":round(b["d"],2),"posted_credit":round(b["cr"],2),"balanced":abs(b["d"]-b["cr"])<.005}
    @app.get("/api/accounting/accounts")
    def accounts(u=Depends(user_from_header)):
        with db() as c:
            seed(c,u["tenant_id"])
            return [dict(r) for r in c.execute("SELECT code,name,account_type,normal_side,parent_code,is_active FROM gl_accounts WHERE tenant_id=? ORDER BY code",(u["tenant_id"],))]
    @app.post("/api/accounting/accounts")
    def add_account(p:AccountIn,u=Depends(user_from_header)):
        if p.normal_side!=("debit" if p.account_type in ("asset","expense") else "credit"):raise HTTPException(422,"ماهیت عادی با گروه حساب سازگار نیست.")
        with db() as c:
            seed(c,u["tenant_id"])
            try:c.execute("INSERT INTO gl_accounts(tenant_id,code,name,account_type,normal_side,parent_code) VALUES(?,?,?,?,?,?)",(u["tenant_id"],p.code,p.name,p.account_type,p.normal_side,p.parent_code))
            except sqlite3.IntegrityError:raise HTTPException(409,"کد حساب تکراری است.")
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(u["tenant_id"],"accounting.account.create:"+p.code))
            return {"ok":True,"code":p.code}
    @app.get("/api/accounting/journals")
    def journals(status:str="",limit:int=100,u=Depends(user_from_header)):
        if status and status not in ("draft","posted","void"):raise HTTPException(422,"وضعیت نامعتبر است.")
        limit=max(1,min(limit,250));tid=u["tenant_id"]
        with db() as c:
            rows=c.execute("SELECT * FROM gl_journals WHERE tenant_id=?"+(" AND status=?" if status else "")+" ORDER BY id DESC LIMIT ?",(tid,*(([status] if status else [])),limit)).fetchall()
            out=[]
            for r in rows:
                item={k:r[k] for k in ("id","journal_no","journal_date","description","source_type","source_ref","status","created_at")}
                item["lines"]=[dict(x) for x in c.execute("SELECT line_no,account_code,memo,debit,credit,party_name FROM gl_lines WHERE tenant_id=? AND journal_id=? ORDER BY line_no",(tid,r["id"]))]
                out.append(item)
            return out
    @app.post("/api/accounting/journals")
    def add_journal(p:JournalIn,u=Depends(user_from_header)):
        with db() as c:return make_journal(c,u,p)
    @app.post("/api/accounting/journals/{jid}/post")
    def post_journal(jid:int,u=Depends(user_from_header)):
        tid=u["tenant_id"]
        with db() as c:
            j=c.execute("SELECT * FROM gl_journals WHERE id=? AND tenant_id=?",(jid,tid)).fetchone()
            if not j:raise HTTPException(404,"سند پیدا نشد.")
            if j["status"]!="draft":raise HTTPException(409,"فقط پیش‌نویس قابل تأیید است.")
            b=c.execute("SELECT SUM(CAST(debit AS REAL)) d,SUM(CAST(credit AS REAL)) cr FROM gl_lines WHERE tenant_id=? AND journal_id=?",(tid,jid)).fetchone()
            if not b["d"] or abs(b["d"]-b["cr"])>=.005:raise HTTPException(422,"سند تراز نیست.")
            c.execute("UPDATE gl_journals SET status='posted',posted_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",(jid,tid))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"accounting.journal.post:"+j["journal_no"]))
            return {"ok":True,"journal_no":j["journal_no"],"status":"posted"}
    @app.get("/api/accounting/trial-balance")
    def trial_balance(from_date:str="",to_date:str="",u=Depends(user_from_header)):
        for v in (from_date,to_date):
            if v:
                try:date.fromisoformat(v)
                except ValueError:raise HTTPException(422,"تاریخ نامعتبر است.")
        tid=u["tenant_id"]
        with db() as c:
            seed(c,tid);items=[]
            for a in c.execute("SELECT code,name,account_type FROM gl_accounts WHERE tenant_id=? ORDER BY code",(tid,)):
                q="SELECT COALESCE(SUM(CAST(l.debit AS REAL)),0) d,COALESCE(SUM(CAST(l.credit AS REAL)),0) cr FROM gl_lines l JOIN gl_journals j ON j.id=l.journal_id AND j.tenant_id=l.tenant_id WHERE l.tenant_id=? AND l.account_code=? AND j.status='posted'"
                args=[tid,a["code"]]
                if from_date:q+=" AND j.journal_date>=?";args.append(from_date)
                if to_date:q+=" AND j.journal_date<=?";args.append(to_date)
                b=c.execute(q,args).fetchone()
                if b["d"] or b["cr"]:items.append({"code":a["code"],"name":a["name"],"account_type":a["account_type"],"debit":round(b["d"],2),"credit":round(b["cr"],2)})
            d=round(sum(x["debit"] for x in items),2);cr=round(sum(x["credit"] for x in items),2)
            return {"items":items,"total_debit":d,"total_credit":cr,"balanced":abs(d-cr)<.005}
    @app.get("/api/accounting/reports/income-statement")
    def income_statement(from_date:str="",to_date:str="",u=Depends(user_from_header)):
        tb=trial_balance(from_date,to_date,u)
        rev=sum(x["credit"]-x["debit"] for x in tb["items"] if x["account_type"]=="revenue")
        exp=sum(x["debit"]-x["credit"] for x in tb["items"] if x["account_type"]=="expense")
        return {"revenue":round(rev,2),"expenses":round(exp,2),"net_profit":round(rev-exp,2)}
    def account_type(c,tid,code):
        row=c.execute("SELECT account_type FROM gl_accounts WHERE tenant_id=? AND code=? AND is_active=1",(tid,code)).fetchone()
        if not row:raise HTTPException(422,"کد حساب نامعتبر است: "+code)
        return row["account_type"]
    @app.post("/api/accounting/automation/sales-voucher")
    def sales_voucher(p:QuickVoucher,u=Depends(user_from_header)):
        revenue=p.account_code or "4000"
        with db() as c:
            if account_type(c,u["tenant_id"],revenue)!="revenue":raise HTTPException(422,"حساب فروش باید از گروه درآمد باشد.")
            q=JournalIn(journal_date=p.journal_date,description=p.description,source_type="sales",source_ref=p.document_ref,lines=[LineIn(account_code="1100",debit=p.amount,memo="حساب دریافتنی",party_name=p.party),LineIn(account_code=revenue,credit=p.amount,memo="درآمد فروش",party_name=p.party)])
            return make_journal(c,u,q)
    @app.post("/api/accounting/automation/expense-voucher")
    def expense_voucher(p:QuickVoucher,u=Depends(user_from_header)):
        expense=p.account_code or "6300"
        with db() as c:
            if account_type(c,u["tenant_id"],expense)!="expense":raise HTTPException(422,"حساب هزینه باید از گروه هزینه باشد.")
            q=JournalIn(journal_date=p.journal_date,description=p.description,source_type="purchase",source_ref=p.document_ref,lines=[LineIn(account_code=expense,debit=p.amount,memo="هزینه/خرید",party_name=p.party),LineIn(account_code="2000",credit=p.amount,memo="حساب پرداختنی",party_name=p.party)])
            return make_journal(c,u,q)
    @app.post("/api/accounting/automation/receipt-voucher")
    def receipt_voucher(p:QuickVoucher,u=Depends(user_from_header)):
        cash_bank=p.account_code or "1010"
        with db() as c:
            if account_type(c,u["tenant_id"],cash_bank)!="asset":raise HTTPException(422,"حساب دریافت وجه باید از گروه دارایی باشد.")
            q=JournalIn(journal_date=p.journal_date,description=p.description,source_type="receipt",source_ref=p.document_ref,lines=[LineIn(account_code=cash_bank,debit=p.amount,memo="دریافت وجه",party_name=p.party),LineIn(account_code="1100",credit=p.amount,memo="تسویه دریافتنی",party_name=p.party)])
            return make_journal(c,u,q)
    @app.post("/api/accounting/automation/payment-voucher")
    def payment_voucher(p:QuickVoucher,u=Depends(user_from_header)):
        cash_bank=p.account_code or "1010"
        with db() as c:
            if account_type(c,u["tenant_id"],cash_bank)!="asset":raise HTTPException(422,"حساب پرداخت وجه باید از گروه دارایی باشد.")
            q=JournalIn(journal_date=p.journal_date,description=p.description,source_type="payment",source_ref=p.document_ref,lines=[LineIn(account_code="2000",debit=p.amount,memo="تسویه پرداختنی",party_name=p.party),LineIn(account_code=cash_bank,credit=p.amount,memo="پرداخت وجه",party_name=p.party)])
            return make_journal(c,u,q)
    @app.post("/api/accounting/import/csv")
    def import_csv(p:CSVImportIn,u=Depends(user_from_header)):
        reader=csv.DictReader(io.StringIO(p.content.lstrip("\\ufeff")))
        required={"date","document_ref","type","amount"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise HTTPException(422,"ستون‌های لازم: date,document_ref,type,amount؛ ستون‌های اختیاری: party,account_code,description")
        rows=list(reader)
        if not rows or len(rows)>500:raise HTTPException(422,"تعداد ردیف باید بین ۱ تا ۵۰۰ باشد.")
        prepared=[]
        for i,row in enumerate(rows, start=2):
            try:
                typ=(row.get("type") or "").strip().lower()
                if typ not in ("sales","expense","receipt","payment"):raise ValueError("type باید sales/expense/receipt/payment باشد")
                p=QuickVoucher(journal_date=date.fromisoformat((row.get("date") or "").strip()),document_ref=(row.get("document_ref") or "").strip(),party=(row.get("party") or "").strip(),amount=Decimal((row.get("amount") or "").strip()),account_code=(row.get("account_code") or "").strip(),description=(row.get("description") or "ورود CSV").strip())
                prepared.append((typ,p))
            except Exception as e:
                raise HTTPException(422,f"خطای ردیف {i}: {str(e)[:180]}")
        created=[]
        with db() as c:
            tid=u["tenant_id"]
            for typ,p in prepared:
                code=p.account_code or {"sales":"4000","expense":"6300","receipt":"1010","payment":"1010"}[typ]
                group=account_type(c,tid,code)
                expected="revenue" if typ=="sales" else "expense" if typ=="expense" else "asset"
                if group!=expected:raise HTTPException(422,f"حساب {code} با نوع {typ} سازگار نیست.")
                if typ=="sales":
                    q=JournalIn(journal_date=p.journal_date,description=p.description,source_type="sales",source_ref=p.document_ref,lines=[LineIn(account_code="1100",debit=p.amount,party_name=p.party),LineIn(account_code=code,credit=p.amount,party_name=p.party)])
                elif typ=="expense":
                    q=JournalIn(journal_date=p.journal_date,description=p.description,source_type="purchase",source_ref=p.document_ref,lines=[LineIn(account_code=code,debit=p.amount,party_name=p.party),LineIn(account_code="2000",credit=p.amount,party_name=p.party)])
                elif typ=="receipt":
                    q=JournalIn(journal_date=p.journal_date,description=p.description,source_type="receipt",source_ref=p.document_ref,lines=[LineIn(account_code=code,debit=p.amount,party_name=p.party),LineIn(account_code="1100",credit=p.amount,party_name=p.party)])
                else:
                    q=JournalIn(journal_date=p.journal_date,description=p.description,source_type="payment",source_ref=p.document_ref,lines=[LineIn(account_code="2000",debit=p.amount,party_name=p.party),LineIn(account_code=code,credit=p.amount,party_name=p.party)])
                created.append(make_journal(c,u,q))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"accounting.csv.import:"+str(len(created))))
        return {"created":created,"count":len(created),"all_drafts":all(x["status"]=="draft" for x in created)}
    @app.get("/api/accounting/automation/settings")
    def get_settings(u=Depends(user_from_header)):
        with db() as c:
            seed(c,u["tenant_id"])
            return dict(c.execute("SELECT suggest_sales,suggest_expenses,duplicate_check,require_approval FROM gl_automation_settings WHERE tenant_id=?",(u["tenant_id"],)).fetchone())
    @app.put("/api/accounting/automation/settings")
    def put_settings(p:dict,u=Depends(user_from_header)):
        allowed={"suggest_sales","suggest_expenses","duplicate_check","require_approval"}
        if not p or set(p)-allowed or any(type(v)is not bool for v in p.values()):raise HTTPException(422,"تنظیمات نامعتبر است.")
        tid=u["tenant_id"]
        with db() as c:
            seed(c,tid);old=dict(c.execute("SELECT suggest_sales,suggest_expenses,duplicate_check,require_approval FROM gl_automation_settings WHERE tenant_id=?",(tid,)).fetchone())
            vals={**old,**{k:int(v) for k,v in p.items()}}
            c.execute("UPDATE gl_automation_settings SET suggest_sales=?,suggest_expenses=?,duplicate_check=?,require_approval=?,updated_at=CURRENT_TIMESTAMP WHERE tenant_id=?",(vals["suggest_sales"],vals["suggest_expenses"],vals["duplicate_check"],vals["require_approval"],tid))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(tid,"accounting.automation.settings.update"))
            return {"ok":True,**vals}
