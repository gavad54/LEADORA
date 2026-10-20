"""Tenant-isolated AI command center and lead-to-cash workflow foundation for LEADORA."""
import json
import os
import urllib.request
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

AGENTS = [
 {"id":"commander","name":"فرمانده مرکزی","purpose":"تخصیص کار، اولویت‌بندی، کنترل SLA، پایش ایجنت‌ها و ارجاع استثناها","autonomy":"coordinate"},
 {"id":"discovery","name":"مشتری‌یابی","purpose":"کشف و ثبت سرنخ از منابع مجاز و متصل، حذف موارد تکراری","autonomy":"prepare"},
 {"id":"qualification","name":"ارزیابی سرنخ","purpose":"امتیازدهی تناسب مشتری، نیاز، کیفیت داده و اولویت پیگیری","autonomy":"recommend"},
 {"id":"outreach","name":"ارتباط و پیگیری","purpose":"تهیه پیام شخصی‌سازی‌شده و زمان‌بندی تماس با رعایت رضایت","autonomy":"draft_only"},
 {"id":"sales_chat","name":"چت‌بات فروش","purpose":"کشف نیاز، پاسخ مستند از کاتالوگ، تکمیل اطلاعات و ارجاع هوشمند","autonomy":"assist"},
 {"id":"offer","name":"پیشنهاد و مذاکره","purpose":"ساخت پیشنهاد از قیمت‌نامه معتبر و رعایت سقف تخفیف","autonomy":"draft_only"},
 {"id":"order_guard","name":"کنترل سفارش","purpose":"اعتبارسنجی اقلام، مقدار، قیمت، نشانی، شرایط و تأیید مشتری","autonomy":"validate"},
 {"id":"credit_risk","name":"ریسک و اعتبار","purpose":"بررسی سیاست اعتبار و بدهی سررسیدگذشته و هشدار ریسک","autonomy":"recommend"},
 {"id":"inventory","name":"موجودی و تأمین","purpose":"کنترل موجودی معتبر، کمبود، گردش کند و پیشنهاد تأمین","autonomy":"recommend"},
 {"id":"warehouse","name":"انبار و آماده‌سازی","purpose":"تهیه لیست برداشت، کنترل مغایرت و ثبت آمادگی ارسال","autonomy":"prepare"},
 {"id":"delivery","name":"توزیع و تحویل","purpose":"پیشنهاد مسیر، هماهنگی با حمل متصل و پیگیری مدرک تحویل","autonomy":"prepare"},
 {"id":"settlement","name":"تسویه و وصول","purpose":"تطبیق فاکتور، سررسید و رسید پرداخت و پیشنهاد یادآوری","autonomy":"recommend"},
 {"id":"retention","name":"حفظ مشتری","purpose":"تشخیص افت تعامل، ریسک ریزش و تهیه برنامه بازگشت","autonomy":"draft_only"},
 {"id":"analytics","name":"تحلیل و پیش‌بینی","purpose":"تحلیل قیف فروش، علل توقف، بهره‌وری مناطق و KPIها","autonomy":"recommend"},
 {"id":"compliance","name":"حریم خصوصی و انطباق","purpose":"کنترل رضایت، مجوز، حداقل‌سازی داده و ثبت ممیزی","autonomy":"guard"}
]
STAGES = ["lead","qualified","contact_drafted","need_discovered","offer_drafted","order_pending_confirmation","order_confirmed","picking","ready_to_ship","in_delivery","delivered","settlement_pending","settled","closed"]
LABELS = {"lead":"سرنخ ثبت‌شده","qualified":"ارزیابی‌شده","contact_drafted":"پیش‌نویس ارتباط آماده","need_discovered":"نیاز مشخص","offer_drafted":"پیشنهاد آماده","order_pending_confirmation":"در انتظار تأیید مشتری","order_confirmed":"سفارش تأییدشده","picking":"آماده‌سازی انبار","ready_to_ship":"آماده ارسال","in_delivery":"در مسیر تحویل","delivered":"تحویل‌شده","settlement_pending":"در انتظار تسویه","settled":"تسویه‌شده","closed":"بسته‌شده"}
GATES = ["ارسال پیام بیرونی","تخفیف خارج از سیاست","اعطای اعتبار","تأیید سفارش به‌جای مشتری","تعهد خرید","اعزام ناوگان","بازپرداخت یا اصلاح مالی","خروجی اطلاعات مشتریان"]

class ChatIn(BaseModel):
 message: str = Field(min_length=1,max_length=5000)
 customer_name: str = Field(default="",max_length=160)
 phone: str = Field(default="",max_length=50)
 channel: str = Field(default="web",max_length=30)
 conversation_id: Optional[int] = None
 consent_to_follow_up: bool = False
class WorkflowIn(BaseModel):
 customer_name: str = Field(min_length=1,max_length=160)
 phone: str = Field(default="",max_length=50)
 need: str = Field(default="",max_length=2000)
 source: str = Field(default="manual",max_length=80)
 consent_to_follow_up: bool = False
class AdvanceIn(BaseModel):
 action: str = Field(min_length=1,max_length=80)
 approved: bool = False
 note: str = Field(default="",max_length=1000)

class DiscoveryIn(BaseModel):
 customer_name: str = Field(min_length=1,max_length=160)
 phone: str = Field(default="",max_length=50)
 need: str = Field(default="",max_length=2000)
 source: str = Field(default="import",max_length=80)
 # None means the source omitted consent; False explicitly withdraws consent.
 consent_to_follow_up: Optional[bool] = None

class FollowupIn(BaseModel):
 workflow_id: int = Field(gt=0)
 due_in_minutes: int = Field(default=1440,ge=0,le=43200)
 channel: str = Field(default="web",min_length=1,max_length=30)


def create_router(db,user_from_header):
 router=APIRouter()
 with db() as c:
  c.executescript("""
  CREATE TABLE IF NOT EXISTS ai_workflows(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,customer_name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',need TEXT NOT NULL DEFAULT '',source TEXT NOT NULL DEFAULT 'manual',stage TEXT NOT NULL DEFAULT 'lead',status TEXT NOT NULL DEFAULT 'active',consent_to_follow_up INTEGER NOT NULL DEFAULT 0,human_required INTEGER NOT NULL DEFAULT 0,next_action TEXT NOT NULL DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE INDEX IF NOT EXISTS idx_aiwf_tenant_stage ON ai_workflows(tenant_id,stage,status);
  CREATE TABLE IF NOT EXISTS ai_conversations(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,customer_name TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',channel TEXT NOT NULL DEFAULT 'web',consent_to_follow_up INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'open',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS ai_messages(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,conversation_id INTEGER NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,intent TEXT NOT NULL DEFAULT 'general',agent_id TEXT NOT NULL DEFAULT 'sales_chat',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE INDEX IF NOT EXISTS idx_aimsg_conversation ON ai_messages(tenant_id,conversation_id,id);
  CREATE TABLE IF NOT EXISTS ai_approvals(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,workflow_id INTEGER,action TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',requested_by TEXT NOT NULL DEFAULT 'ai',decided_by INTEGER,note TEXT NOT NULL DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,decided_at TEXT);
  CREATE TABLE IF NOT EXISTS ai_audit_events(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,actor_type TEXT NOT NULL,actor_id INTEGER,event_type TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id INTEGER,detail_json TEXT NOT NULL DEFAULT '{}',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS ai_agent_tasks(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,workflow_id INTEGER NOT NULL,agent_id TEXT NOT NULL,task_type TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',priority INTEGER NOT NULL DEFAULT 50,input_json TEXT NOT NULL DEFAULT '{}',output_json TEXT NOT NULL DEFAULT '{}',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE INDEX IF NOT EXISTS idx_ai_tasks_tenant_status ON ai_agent_tasks(tenant_id,status,priority);
  CREATE TABLE IF NOT EXISTS ai_followups(id INTEGER PRIMARY KEY,tenant_id INTEGER NOT NULL,workflow_id INTEGER NOT NULL,channel TEXT NOT NULL DEFAULT 'web',status TEXT NOT NULL DEFAULT 'queued',due_at TEXT NOT NULL,draft TEXT NOT NULL DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE INDEX IF NOT EXISTS idx_ai_followups_due ON ai_followups(tenant_id,status,due_at);
  """)
 def audit(c,tid,actor,actor_id,event,entity,eid,detail):
  c.execute("INSERT INTO ai_audit_events(tenant_id,actor_type,actor_id,event_type,entity_type,entity_id,detail_json) VALUES(?,?,?,?,?,?,?)",(tid,actor,actor_id,event,entity,eid,json.dumps(detail,ensure_ascii=False)))
 def call_live_llm(message,intent,customer_name,history=None):
  """Use a local Ollama model or OpenAI Responses API; never claim external actions."""
  provider=os.getenv("LEADORA_AI_PROVIDER","").strip().lower()
  api_key=os.getenv("OPENAI_API_KEY","").strip()
  if not provider:
   provider="openai" if api_key else "none"
  system=("You are LEADORA's Persian-first B2B sales assistant. Be concise, polite, useful and ask targeted questions. "
          "Never invent product facts, stock, prices, delivery status, invoices, payment status, discounts or promises. "
          "No catalog, inventory, order, courier or payment data was supplied, so ask for missing details or say that a connected system or employee must verify them. "
          "Never claim you sent a message, created an order, dispatched goods or received money. "
          "Respect consent; for complaints, disputes, refunds, credit or sensitive exceptions recommend human handoff. "
          "Respond in Persian unless the customer clearly writes in another language.")
  prompt="Customer name: "+customer_name+"\nIntent classification: "+intent+"\nRecent conversation context (oldest first):\n"+json.dumps(history or [],ensure_ascii=False)+"\nLatest customer message: "+message
  try:
   if provider=="ollama":
    host=os.getenv("OLLAMA_HOST","http://127.0.0.1:11434").rstrip("/")
    payload={"model":os.getenv("OLLAMA_MODEL","qwen2.5:3b"),"stream":False,
             "messages":[{"role":"system","content":system},{"role":"user","content":prompt}],
             "options":{"temperature":0.2,"num_predict":300}}
    request=urllib.request.Request(host+"/api/chat",data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(request,timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS","45"))) as response:
     data=json.loads(response.read().decode("utf-8"))
    answer=(data.get("message") or {}).get("content","").strip()
    return answer[:5000] if answer else None
   if provider!="openai" or not api_key:
    return None
   payload={"model":os.getenv("OPENAI_MODEL","gpt-4.1-mini"),"instructions":system,
            "input":prompt,"max_output_tokens":300}
   request=urllib.request.Request("https://api.openai.com/v1/responses",data=json.dumps(payload).encode("utf-8"),
           headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},method="POST")
   with urllib.request.urlopen(request,timeout=12) as response:
    data=json.loads(response.read().decode("utf-8"))
   parts=[]
   for item in data.get("output",[]):
    if item.get("type")=="message":
     for part in item.get("content",[]):
      if part.get("type")=="output_text" and part.get("text"): parts.append(part["text"])
   answer="\n".join(parts).strip()
   return answer[:5000] if answer else None
  except Exception:
   return None
 def active_ai_provider():
  provider=os.getenv("LEADORA_AI_PROVIDER","").strip().lower()
  if provider=="ollama":
   return {"provider":"ollama","configured":True,"model":os.getenv("OLLAMA_MODEL","qwen2.5:3b")}
  if provider=="openai" and os.getenv("OPENAI_API_KEY","").strip():
   return {"provider":"openai","configured":True,"model":os.getenv("OPENAI_MODEL","gpt-4.1-mini")}
  if not provider and os.getenv("OPENAI_API_KEY","").strip():
   return {"provider":"openai","configured":True,"model":os.getenv("OPENAI_MODEL","gpt-4.1-mini")}
  return {"provider":"rules_fallback","configured":False,"model":None}
 def classify(msg):
  m=msg.casefold()
  if any(x in m for x in ["قیمت","هزینه","چنده","تخفیف","price","cost"]): return "pricing"
  if any(x in m for x in ["سفارش","خرید","میخوام","می‌خوام","می خواهم","order","buy"]): return "purchase"
  if any(x in m for x in ["تحویل","ارسال","کجاست","delivery","tracking"]): return "delivery"
  if any(x in m for x in ["پرداخت","تسویه","فاکتور","بدهی","واریز","payment","invoice"]): return "settlement"
  if any(x in m for x in ["موجودی","دارید","موجوده","انبار","stock","available"]): return "availability"
  if any(x in m for x in ["شکایت","ناراضی","مشکل","خراب","complaint","refund"]): return "complaint"
  if any(x in m for x in ["کارشناس","انسان","اپراتور","پشتیبانی","شخص واقعی","human"]): return "human_handoff"
  return "discovery"
 def reply(msg,intent,name):
  if intent=="pricing": return "برای اعلام قیمت دقیق، نام کالا/خدمت، مشخصات و مقدار را بفرمایید. قیمت از فهرست معتبر شرکت بررسی می‌شود؛ تخفیف خارج از سیاست نیازمند تأیید مسئول فروش است."
  if intent=="purchase": return "لطفاً کالا یا خدمت، مقدار، شهر یا نشانی تحویل و روش تسویه ترجیحی را مشخص کنید. پیش از نهایی‌شدن، خلاصه سفارش برای تأیید صریح شما نمایش داده می‌شود."
  if intent=="delivery": return "لطفاً شماره سفارش یا پیگیری را بفرمایید. اگر سامانه حمل متصل نباشد، وضعیت زنده را حدس نمی‌زنم و موضوع برای پیگیری علامت‌گذاری می‌شود."
  if intent=="settlement": return "شماره فاکتور یا سفارش و تاریخ پرداخت را بفرمایید. ثبت قطعی پرداخت به رسید یا اتصال معتبر نیاز دارد؛ پیام چت به‌تنهایی رسید پرداخت نیست."
  if intent=="availability": return "نام یا کد کالا و مقدار را بفرمایید. موجودی نهایی باید از انبار زنده بررسی شود؛ بدون داده متصل، موجودی را تأیید نمی‌کنم."
  if intent=="complaint": return "متأسفم با مشکل روبه‌رو شده‌اید. شماره سفارش و شرح کوتاه مشکل را بفرمایید تا برای بررسی مسئول مربوطه ثبت شود. پیش از بررسی، وعده بازپرداخت یا تعهد مالی نمی‌دهم."
  if intent=="human_handoff": return "درخواست ارتباط با کارشناس انسانی ثبت می‌شود. لطفاً موضوع و راه تماس مناسب را بنویسید."
  if any(x in msg.casefold() for x in ["سلام","درود","hello","hi"]): return "سلام"+(" "+name.strip() if name.strip() else "")+"، به فروش هوشمند خوش آمدید. دنبال چه کالا یا خدمتی هستید و چه مقدار نیاز دارید؟"
  return "برای راهنمایی دقیق، نوع کالا یا خدمت، مقدار موردنیاز و شهر تحویل را بفرمایید. فقط اطلاعات تأییدشده اعلام می‌شود و پیش از سفارش نهایی، تأیید شما گرفته خواهد شد."

 @router.post("/api/ai/discovery/ingest")
 def ingest_discovery(body:DiscoveryIn,user=Depends(user_from_header)):
  """Ingest a prospect from an explicitly authorized source and deduplicate within its tenant."""
  tid=user["tenant_id"]
  name=body.customer_name.strip()
  phone=body.phone.strip()
  phone_digits="".join(ch for ch in phone if ch.isdigit())
  source=body.source.strip() or "import"
  with db() as c:
   rows=c.execute("SELECT id,customer_name,phone,need,source,consent_to_follow_up,stage FROM ai_workflows WHERE tenant_id=? AND status='active' ORDER BY id DESC",(tid,)).fetchall()
   match=None
   for row in rows:
    existing_digits="".join(ch for ch in (row["phone"] or "") if ch.isdigit())
    if phone_digits and existing_digits and phone_digits==existing_digits:
     match=row; break
   if match is None and not phone_digits:
    normalized=name.casefold().strip()
    for row in rows:
     if not (row["phone"] or "").strip() and (row["customer_name"] or "").casefold().strip()==normalized:
      match=row; break
   if match:
    new_name=name or match["customer_name"]
    new_phone=phone or match["phone"]
    new_need=body.need.strip() or match["need"]
    new_source=source if source not in ("import","manual","unknown") else match["source"]
    consent=int(body.consent_to_follow_up) if body.consent_to_follow_up is not None else int(match["consent_to_follow_up"])
    c.execute("UPDATE ai_workflows SET customer_name=?,phone=?,need=?,source=?,consent_to_follow_up=?,next_action=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",
      (new_name,new_phone,new_need,new_source,consent,"ارزیابی سرنخ تکراری/به‌روزشده و تکمیل اطلاعات",match["id"],tid))
    wid=match["id"]; created=False
    audit(c,tid,"ai",None,"discovery.duplicate_updated","workflow",wid,{"source":source,"phone_match":bool(phone_digits),"consent_updated":body.consent_to_follow_up is not None})
   else:
    cur=c.execute("INSERT INTO ai_workflows(tenant_id,customer_name,phone,need,source,consent_to_follow_up,stage,next_action) VALUES(?,?,?,?,?,?,'lead',?)",
      (tid,name,phone,body.need.strip(),source,int(bool(body.consent_to_follow_up)),"ارزیابی خودکار سرنخ و شناسایی اطلاعات ناقص"))
    wid=cur.lastrowid; created=True
    audit(c,tid,"ai",None,"discovery.lead_ingested","workflow",wid,{"source":source,"has_phone":bool(phone_digits),"consent_to_follow_up":body.consent_to_follow_up})
  return {"id":wid,"created":created,"duplicate_detected":not created,"tenant_deduplication":True,"consent_to_follow_up":bool(consent if match else body.consent_to_follow_up),"next_action":"امتیازدهی، تکمیل داده‌های ناقص و پیگیری فقط در صورت رضایت"}
 @router.post("/api/ai/followups")
 def schedule_followup(body:FollowupIn,user=Depends(user_from_header)):
  tid=user["tenant_id"]
  with db() as c:
   w=c.execute("SELECT id,consent_to_follow_up,status FROM ai_workflows WHERE id=? AND tenant_id=?",(body.workflow_id,tid)).fetchone()
   if not w: raise HTTPException(404,"سرنخ یا فرایند یافت نشد.")
   if not w["consent_to_follow_up"]: raise HTTPException(409,"برای پیگیری بیرونی، رضایت صریح مشتری لازم است.")
   if w["status"]!="active": raise HTTPException(409,"برای فرایند بسته‌شده پیگیری جدید زمان‌بندی نمی‌شود.")
   cur=c.execute("INSERT INTO ai_followups(tenant_id,workflow_id,channel,status,due_at) VALUES(?,?,?,'queued',datetime(CURRENT_TIMESTAMP, '+' || ? || ' minutes'))",
     (tid,body.workflow_id,body.channel.strip(),body.due_in_minutes))
   fid=cur.lastrowid
   audit(c,tid,"ai",None,"followup.scheduled","followup",fid,{"workflow_id":body.workflow_id,"channel":body.channel,"due_in_minutes":body.due_in_minutes})
  return {"id":fid,"workflow_id":body.workflow_id,"status":"queued","due_in_minutes":body.due_in_minutes,"external_message_sent":False}
 @router.get("/api/ai/followups")
 def list_followups(user=Depends(user_from_header)):
  with db() as c:
   rows=c.execute("SELECT f.id,f.workflow_id,f.channel,f.status,f.due_at,f.draft,f.created_at FROM ai_followups f WHERE f.tenant_id=? ORDER BY f.due_at,f.id DESC LIMIT 200",(user["tenant_id"],)).fetchall()
  return [{"id":r["id"],"workflow_id":r["workflow_id"],"channel":r["channel"],"status":r["status"],"due_at":r["due_at"],"draft":r["draft"],"sent":False,"created_at":r["created_at"]} for r in rows]
 @router.post("/api/ai/followups/run")
 def run_due_followups(user=Depends(user_from_header)):
  tid=user["tenant_id"]; processed=[]
  with db() as c:
   rows=c.execute("SELECT f.*,w.customer_name,w.need,w.consent_to_follow_up,w.status AS workflow_status FROM ai_followups f JOIN ai_workflows w ON w.id=f.workflow_id AND w.tenant_id=f.tenant_id WHERE f.tenant_id=? AND f.status='queued' AND f.due_at<=CURRENT_TIMESTAMP ORDER BY f.due_at,f.id LIMIT 100",(tid,)).fetchall()
   for r in rows:
    if not r["consent_to_follow_up"] or r["workflow_status"]!="active":
     status="blocked"; draft=""
     reason="رضایت پیگیری موجود نیست یا فرایند بسته شده است"
    else:
     status="draft_ready"
     reason=""
     need=(r["need"] or "").strip()
     draft="سلام "+(r["customer_name"] or "وقت بخیر")+"، برای پیگیری درخواست شما"+(" درباره «"+need[:240]+"»" if need else "")+" آماده کمک هستیم. آیا مایلید اطلاعات یا مرحله بعد را بررسی کنیم؟"
    c.execute("UPDATE ai_followups SET status=?,draft=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=? AND status='queued'",(status,draft,r["id"],tid))
    audit(c,tid,"ai",None,"followup."+status,"followup",r["id"],{"workflow_id":r["workflow_id"],"reason":reason,"sent":False})
    processed.append({"id":r["id"],"status":status,"draft":draft,"sent":False,"reason":reason})
  return {"processed":len(processed),"results":processed,"external_message_sent":False,"note":"متن پیگیری آماده می‌شود؛ ارسال واقعی تا اتصال کانال و فعال‌سازی مجوز ارسال انجام نمی‌شود."}

 @router.get("/api/ai/agents")
 def agents(user=Depends(user_from_header)):
  return {"product":"LEADORA","separate_from_ARIANA":True,"command_center":"AI Command Center","agents":AGENTS,"human_approval_gates":GATES,"external_side_effects_require_integrations":True}
 @router.get("/api/ai/command-center")
 def dashboard(user=Depends(user_from_header)):
  tid=user["tenant_id"]
  with db() as c:
   total=c.execute("SELECT COUNT(*) n FROM ai_workflows WHERE tenant_id=?",(tid,)).fetchone()["n"]
   active=c.execute("SELECT COUNT(*) n FROM ai_workflows WHERE tenant_id=? AND status='active'",(tid,)).fetchone()["n"]
   pending=c.execute("SELECT COUNT(*) n FROM ai_approvals WHERE tenant_id=? AND status='pending'",(tid,)).fetchone()["n"]
   conv=c.execute("SELECT COUNT(*) n FROM ai_conversations WHERE tenant_id=? AND status='open'",(tid,)).fetchone()["n"]
   task_count=c.execute("SELECT COUNT(*) n FROM ai_agent_tasks WHERE tenant_id=? AND status IN ('queued','blocked','needs_human')",(tid,)).fetchone()["n"]
   stages=[dict(r) for r in c.execute("SELECT stage,COUNT(*) count FROM ai_workflows WHERE tenant_id=? AND status='active' GROUP BY stage",(tid,)).fetchall()]
   recent=[dict(r) for r in c.execute("SELECT id,customer_name,stage,status,human_required,next_action,updated_at FROM ai_workflows WHERE tenant_id=? ORDER BY id DESC LIMIT 10",(tid,)).fetchall()]
  return {"summary":{"workflows_total":total,"workflows_active":active,"approvals_pending":pending,"open_conversations":conv,"agent_tasks_pending":task_count},"stages":[{**r,"label":LABELS.get(r["stage"],r["stage"])} for r in stages],"recent_workflows":recent,"automation_policy":{"routine_actions":"only after verified data, permissions and policy checks","human_approval_gates":GATES,"live_llm_configured":active_ai_provider()["configured"],"ai_provider":active_ai_provider(),"external_channels_connected":False,"payment_execution_connected":False}}
 @router.post("/api/ai/workflows")
 def create_workflow(body:WorkflowIn,user=Depends(user_from_header)):
  tid=user["tenant_id"]
  with db() as c:
   cur=c.execute("INSERT INTO ai_workflows(tenant_id,customer_name,phone,need,source,consent_to_follow_up,stage,next_action) VALUES(?,?,?,?,?,?,'lead',?)",(tid,body.customer_name.strip(),body.phone.strip(),body.need.strip(),body.source.strip(),int(body.consent_to_follow_up),"ارزیابی اولیه سرنخ و تکمیل اطلاعات ضروری"))
   wid=cur.lastrowid
   audit(c,tid,"human",user["id"],"workflow.created","workflow",wid,{"stage":"lead"})
  return {"id":wid,"stage":"lead","stage_label":LABELS["lead"],"status":"active","next_action":"ارزیابی اولیه سرنخ و تکمیل اطلاعات ضروری"}
 @router.get("/api/ai/workflows")
 def workflows(stage:Optional[str]=None,user=Depends(user_from_header)):
  if stage and stage not in STAGES: raise HTTPException(422,"مرحله فرایند نامعتبر است.")
  with db() as c:
   rows=c.execute("SELECT * FROM ai_workflows WHERE tenant_id=?"+(" AND stage=?" if stage else "")+" ORDER BY id DESC LIMIT 200", (user["tenant_id"],stage) if stage else (user["tenant_id"],)).fetchall()
  return [{"id":r["id"],"customer_name":r["customer_name"],"phone":r["phone"],"need":r["need"],"source":r["source"],"stage":r["stage"],"stage_label":LABELS.get(r["stage"],r["stage"]),"status":r["status"],"consent_to_follow_up":bool(r["consent_to_follow_up"]),"human_required":bool(r["human_required"]),"next_action":r["next_action"],"created_at":r["created_at"],"updated_at":r["updated_at"]} for r in rows]
 @router.post("/api/ai/workflows/{workflow_id}/advance")
 def advance(workflow_id:int,body:AdvanceIn,user=Depends(user_from_header)):
  mapping={"qualify":("qualified","تکمیل امتیازدهی"),"draft_contact":("contact_drafted","بازبینی پیام و ارسال در کانال مجاز"),"discover_need":("need_discovered","تکمیل نیاز و شرایط"),"draft_offer":("offer_drafted","بازبینی پیشنهاد و قیمت معتبر"),"request_order_confirmation":("order_pending_confirmation","دریافت تأیید صریح مشتری"),"confirm_order":("order_confirmed","کنترل موجودی و آماده‌سازی انبار"),"start_picking":("picking","برداشت و کنترل اقلام"),"mark_ready_to_ship":("ready_to_ship","تأیید برنامه ارسال"),"start_delivery":("in_delivery","ثبت پیگیری از سامانه حمل"),"mark_delivered":("delivered","تطبیق مدرک تحویل"),"request_settlement":("settlement_pending","تطبیق فاکتور و رسید"),"mark_settled":("settled","کنترل نهایی"),"close":("closed","ثبت علت بستن")}
  if body.action not in mapping: raise HTTPException(422,"اقدام نامعتبر است.")
  tid=user["tenant_id"]; stage,next_action=mapping[body.action]
  human=body.action in ("draft_contact","draft_offer","confirm_order","start_delivery","mark_settled")
  allowed_from={"qualify":["lead"],"draft_contact":["qualified"],"discover_need":["contact_drafted","qualified"],"draft_offer":["need_discovered"],"request_order_confirmation":["offer_drafted"],"confirm_order":["order_pending_confirmation"],"start_picking":["order_confirmed"],"mark_ready_to_ship":["picking"],"start_delivery":["ready_to_ship"],"mark_delivered":["in_delivery"],"request_settlement":["delivered"],"mark_settled":["settlement_pending"]}
  with db() as c:
   row=c.execute("SELECT id,stage,consent_to_follow_up FROM ai_workflows WHERE id=? AND tenant_id=?",(workflow_id,tid)).fetchone()
   if not row: raise HTTPException(404,"فرایند یافت نشد.")
   if body.action in allowed_from and row["stage"] not in allowed_from[body.action]:
    raise HTTPException(409,"ترتیب فرایند رعایت نشده است؛ مرحله فعلی: "+LABELS.get(row["stage"],row["stage"]))
   if body.action=="draft_contact" and not row["consent_to_follow_up"]:
    raise HTTPException(409,"پیش‌نویس تماس تا ثبت رضایت مشتری مجاز نیست.")
   if body.action in ("confirm_order","start_delivery","mark_settled") and not body.approved:
    raise HTTPException(409,"این اقدام نیازمند تأیید صریح انسانی است.")
   c.execute("UPDATE ai_workflows SET stage=?,human_required=?,next_action=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",(stage,int(human),next_action,workflow_id,tid))
   if human: c.execute("INSERT INTO ai_approvals(tenant_id,workflow_id,action,status,requested_by,note) VALUES(?,?,?,'pending','ai',?)",(tid,workflow_id,body.action,body.note))
   audit(c,tid,"human" if body.approved else "ai",user["id"] if body.approved else None,"workflow.advanced","workflow",workflow_id,{"action":body.action,"stage":stage,"approved":body.approved})
  return {"id":workflow_id,"stage":stage,"stage_label":LABELS[stage],"human_required":human,"next_action":next_action,"external_action_executed":False}
 @router.get("/api/ai/approvals")
 def approvals(user=Depends(user_from_header)):
  with db() as c: rows=c.execute("SELECT id,workflow_id,action,status,note,created_at FROM ai_approvals WHERE tenant_id=? ORDER BY id DESC LIMIT 200",(user["tenant_id"],)).fetchall()
  return [dict(r) for r in rows]
 @router.post("/api/ai/approvals/{approval_id}/decide")
 def decide(approval_id:int,body:AdvanceIn,user=Depends(user_from_header)):
  with db() as c:
   row=c.execute("SELECT * FROM ai_approvals WHERE id=? AND tenant_id=?",(approval_id,user["tenant_id"])).fetchone()
   if not row: raise HTTPException(404,"درخواست تأیید یافت نشد.")
   if row["status"]!="pending": raise HTTPException(409,"درخواست قبلاً تعیین تکلیف شده است.")
   status="approved" if body.approved else "rejected"
   c.execute("UPDATE ai_approvals SET status=?,decided_by=?,note=?,decided_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",(status,user["id"],body.note,approval_id,user["tenant_id"]))
   if row["workflow_id"]: c.execute("UPDATE ai_workflows SET human_required=0,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",(row["workflow_id"],user["tenant_id"]))
   audit(c,user["tenant_id"],"human",user["id"],"approval."+status,"approval",approval_id,{"action":row["action"],"note":body.note})
  return {"id":approval_id,"status":status,"external_action_executed":False}
 @router.post("/api/ai/chat")
 def chat(body:ChatIn,user=Depends(user_from_header)):
  tid=user["tenant_id"]; msg=body.message.strip()
  if not msg: raise HTTPException(422,"پیام خالی است.")
  intent=classify(msg); handoff=intent in ("complaint","human_handoff")
  with db() as c:
   cid=body.conversation_id
   if cid is None:
    cur=c.execute("INSERT INTO ai_conversations(tenant_id,customer_name,phone,channel,consent_to_follow_up) VALUES(?,?,?,?,?)",(tid,body.customer_name.strip(),body.phone.strip(),body.channel.strip(),int(body.consent_to_follow_up))); cid=cur.lastrowid
   else:
    exists=c.execute("SELECT id FROM ai_conversations WHERE id=? AND tenant_id=?",(cid,tid)).fetchone()
    if not exists: raise HTTPException(404,"گفت‌وگو یافت نشد.")
    if body.consent_to_follow_up: c.execute("UPDATE ai_conversations SET consent_to_follow_up=1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",(cid,tid))
   prior=[{"role":r["role"],"content":r["content"]} for r in c.execute("SELECT role,content FROM ai_messages WHERE tenant_id=? AND conversation_id=? ORDER BY id DESC LIMIT 8",(tid,cid)).fetchall()][::-1]
   c.execute("INSERT INTO ai_messages(tenant_id,conversation_id,role,content,intent,agent_id) VALUES(?,?, 'customer', ?, ?, 'sales_chat')",(tid,cid,msg,intent))
   answer=call_live_llm(msg,intent,body.customer_name,prior)
   llm_used=bool(answer)
   if not answer: answer=reply(msg,intent,body.customer_name)
   c.execute("INSERT INTO ai_messages(tenant_id,conversation_id,role,content,intent,agent_id) VALUES(?,?, 'assistant', ?, ?, 'sales_chat')",(tid,cid,answer,intent))
   audit(c,tid,"ai",None,"chat.responded","conversation",cid,{"intent":intent,"channel":body.channel})
   if handoff: c.execute("INSERT INTO ai_approvals(tenant_id,action,status,requested_by,note) VALUES(?,?,'pending','ai',?)",(tid,"human_handoff",f"گفت‌وگوی {cid}: ارجاع انسانی، قصد={intent}"))
  return {"conversation_id":cid,"intent":intent,"agent":"sales_chat","reply":answer,"handoff_required":handoff,"automation":{"live_llm":llm_used,"external_message_sent":False,"consent_to_follow_up":body.consent_to_follow_up}}
 @router.get("/api/ai/chat/{conversation_id}")
 def history(conversation_id:int,user=Depends(user_from_header)):
  with db() as c:
   conv=c.execute("SELECT id,customer_name,phone,channel,consent_to_follow_up,status,created_at FROM ai_conversations WHERE id=? AND tenant_id=?",(conversation_id,user["tenant_id"])).fetchone()
   if not conv: raise HTTPException(404,"گفت‌وگو یافت نشد.")
   messages=[dict(r) for r in c.execute("SELECT id,role,content,intent,agent_id,created_at FROM ai_messages WHERE conversation_id=? AND tenant_id=? ORDER BY id",(conversation_id,user["tenant_id"])).fetchall()]
  return {"conversation":dict(conv),"messages":messages}
 @router.get("/api/ai/tasks")
 def tasks(status:Optional[str]=None,user=Depends(user_from_header)):
  allowed=("queued","completed","blocked","needs_human","failed")
  if status and status not in allowed: raise HTTPException(422,"وضعیت وظیفه نامعتبر است.")
  with db() as c:
   rows=c.execute("SELECT * FROM ai_agent_tasks WHERE tenant_id=?"+(" AND status=?" if status else "")+" ORDER BY priority ASC,id DESC LIMIT 200",(user["tenant_id"],status) if status else (user["tenant_id"],)).fetchall()
  return [{"id":r["id"],"workflow_id":r["workflow_id"],"agent_id":r["agent_id"],"task_type":r["task_type"],"status":r["status"],"priority":r["priority"],"input":json.loads(r["input_json"] or "{}"),"output":json.loads(r["output_json"] or "{}"),"created_at":r["created_at"],"updated_at":r["updated_at"]} for r in rows]
 @router.post("/api/ai/orchestrate")
 def orchestrate(user=Depends(user_from_header)):
  tid=user["tenant_id"]
  plan={"lead":("qualification","qualify",10),"qualified":("outreach","draft_contact",20),"contact_drafted":("sales_chat","discover_need",20),"need_discovered":("offer","draft_offer",25),"offer_drafted":("order_guard","request_order_confirmation",20),"order_pending_confirmation":("order_guard","await_customer_confirmation",15),"order_confirmed":("warehouse","prepare_picklist",20),"picking":("warehouse","human_pick_pack",10),"ready_to_ship":("delivery","dispatch_order",20),"in_delivery":("delivery","verify_delivery",20),"delivered":("settlement","reconcile_payment",20),"settlement_pending":("settlement","reconcile_payment",15),"settled":("retention","retention_followup",40)}
  created=[]; ran=[]
  with db() as c:
   rows=c.execute("SELECT * FROM ai_workflows WHERE tenant_id=? AND status='active' ORDER BY id",(tid,)).fetchall()
   for w in rows:
    spec=plan.get(w["stage"])
    if not spec: continue
    agent,task_type,priority=spec
    exists=c.execute("SELECT id FROM ai_agent_tasks WHERE tenant_id=? AND workflow_id=? AND task_type=? AND status IN ('queued','blocked','needs_human')",(tid,w["id"],task_type)).fetchone()
    if exists: continue
    cur=c.execute("INSERT INTO ai_agent_tasks(tenant_id,workflow_id,agent_id,task_type,priority,input_json) VALUES(?,?,?,?,?,?)",(tid,w["id"],agent,task_type,priority,json.dumps({"stage":w["stage"],"customer_name":w["customer_name"],"need":w["need"],"consent_to_follow_up":bool(w["consent_to_follow_up"])},ensure_ascii=False)))
    created.append(cur.lastrowid)
   audit(c,tid,"ai",None,"orchestrator.dispatched","tenant",tid,{"created_tasks":len(created),"active_workflows":len(rows)})
  for task_id in created:
   result=execute_task(task_id,tid)
   ran.append({"task_id":task_id,**result})
  return {"created_tasks":len(created),"processed":len(ran),"results":ran,"note":"وظایف امن به‌صورت محدود اجرا شدند؛ ارسال بیرونی، پرداخت، اعزام و عملیات فیزیکی بدون اتصال و تأیید اجرا نمی‌شوند."}
 def execute_task(task_id,tid):
  with db() as c:
   t=c.execute("SELECT * FROM ai_agent_tasks WHERE id=? AND tenant_id=?",(task_id,tid)).fetchone()
   if not t: raise HTTPException(404,"وظیفه پیدا نشد.")
   if t["status"]!="queued": return {"status":t["status"],"message":"این وظیفه در صف اجرا نیست."}
   w=c.execute("SELECT * FROM ai_workflows WHERE id=? AND tenant_id=?",(t["workflow_id"],tid)).fetchone()
   if not w: raise HTTPException(404,"فرایند مرتبط پیدا نشد.")
   kind=t["task_type"]; status="completed"; output={}; new_stage=None; next_action=w["next_action"]
   if kind=="qualify":
    # Explainable first-pass score; never infer buying intent from missing data.
    factors=[]
    score=0
    if w["customer_name"].strip():
     score+=10; factors.append({"factor":"نام مشتری","points":10,"reason":"نام ثبت شده"})
    else:
     factors.append({"factor":"نام مشتری","points":0,"reason":"نام تکمیل نشده"})
    if w["need"].strip():
     score+=35; factors.append({"factor":"نیاز مشخص","points":35,"reason":"نیاز در پرونده ثبت شده"})
    else:
     factors.append({"factor":"نیاز مشخص","points":0,"reason":"نیاز باید با پرسش هدفمند کشف شود"})
    if w["phone"].strip():
     score+=15; factors.append({"factor":"راه تماس","points":15,"reason":"شماره تماس ثبت شده"})
    else:
     factors.append({"factor":"راه تماس","points":0,"reason":"راه تماس ثبت نشده"})
    if w["source"].strip() and w["source"].strip().lower() not in ("manual","unknown","نامشخص"):
     score+=10; factors.append({"factor":"منبع سرنخ","points":10,"reason":"منبع سرنخ مشخص است"})
    else:
     factors.append({"factor":"منبع سرنخ","points":0,"reason":"منبع سرنخ نیازمند ثبت است"})
    if w["consent_to_follow_up"]:
     score+=20; factors.append({"factor":"رضایت پیگیری","points":20,"reason":"رضایت ثبت شده"})
    else:
     factors.append({"factor":"رضایت پیگیری","points":0,"reason":"ارتباط تبلیغاتی/پیگیری بیرونی مجاز نیست"})
    if w["need"].strip() and len(w["need"].strip())>=25:
     score+=10; factors.append({"factor":"جزئیات نیاز","points":10,"reason":"شرح نیاز جزئیات کافی دارد"})
    else:
     factors.append({"factor":"جزئیات نیاز","points":0,"reason":"مقدار، زمان یا شرایط خرید را روشن کنید"})
    tier="hot" if score>=75 else ("warm" if score>=45 else "needs_enrichment")
    missing=[f["factor"] for f in factors if f["points"]==0]
    questions=[]
    if not w["need"].strip(): questions.append("دقیقاً چه کالا یا خدمتی و برای چه کاربردی نیاز دارید؟")
    if w["need"].strip() and len(w["need"].strip())<25: questions.append("چه مقدار، چه زمان تحویل و چه مشخصاتی مدنظر است؟")
    if not w["phone"].strip(): questions.append("در صورت تمایل، راه تماس مناسب برای پیگیری چیست؟")
    if not w["consent_to_follow_up"]: questions.append("آیا رضایت می‌دهید از طریق کانال انتخابی خود پیگیری بعدی انجام شود؟")
    output={"lead_score":score,"tier":tier,"score_method":"explainable_rules_v1","factors":factors,"missing_fields":missing,"targeted_questions":questions,"reason":"امتیاز بر اساس داده‌های ثبت‌شده محاسبه شده؛ این امتیاز تضمین خرید نیست."}
    new_stage="qualified"; next_action=("تکمیل داده‌های ناقص سرنخ: "+ "؛ ".join(questions[:2])) if questions else "تهیه پیش‌نویس ارتباط متناسب با نیاز و کانال مجاز"
   elif kind=="draft_contact":
    if not w["consent_to_follow_up"]:
     status="blocked"; output={"reason":"رضایت پیگیری ثبت نشده است"}
    else:
     output={"draft":"سلام، برای بررسی دقیق نیاز شما آماده‌ایم. لطفاً کالا/خدمت، مقدار و زمان تحویل موردنظر را تأیید کنید.","sent":False}
     new_stage="contact_drafted"; next_action="تکمیل نیاز مشتری از طریق کانال مجاز"
   elif kind=="discover_need":
    if not w["need"].strip():
     status="blocked"; output={"reason":"نیاز مشتری هنوز ثبت نشده است"}
    else:
     output={"need_summary":w["need"],"source":"workflow_record"}; new_stage="need_discovered"; next_action="اتصال کاتالوگ و قیمت معتبر برای تهیه پیشنهاد"
   elif kind=="draft_offer":
    status="blocked"; output={"reason":"کاتالوگ، قیمت‌نامه و موجودی معتبر به موتور پیشنهاد متصل نیستند؛ قیمت‌سازی ممنوع است"}
   elif kind in ("request_order_confirmation","await_customer_confirmation"):
    status="blocked"; output={"reason":"منتظر تعامل واقعی مشتری و ثبت تأیید صریح سفارش هستیم","sent":False}
   elif kind in ("prepare_picklist","human_pick_pack"):
    status="needs_human"; output={"reason":"برداشت، شمارش و بسته‌بندی فیزیکی باید توسط نیروی انبار انجام و ثبت شود"}
   elif kind in ("dispatch_order","verify_delivery"):
    status="blocked"; output={"reason":"اتصال شرکت حمل و مدرک تحویل هنوز پیکربندی نشده است"}
   elif kind=="reconcile_payment":
    status="blocked"; output={"reason":"برای تطبیق تسویه، فاکتور معتبر و رسید پرداخت یا اتصال درگاه/بانک لازم است"}
   elif kind=="retention_followup":
    if not w["consent_to_follow_up"]:
     status="blocked"; output={"reason":"رضایت برای پیگیری بعدی ثبت نشده است"}
    else:
     output={"draft":"سلام، امیدواریم تجربه خوبی داشته باشید. آیا برای سفارش بعدی یا رفع نیاز جدید کمکی لازم دارید؟","sent":False}
   c.execute("UPDATE ai_agent_tasks SET status=?,output_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",(status,json.dumps(output,ensure_ascii=False),task_id,tid))
   if new_stage:
    c.execute("UPDATE ai_workflows SET stage=?,next_action=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",(new_stage,next_action,w["id"],tid))
   audit(c,tid,"ai",None,"agent.task."+status,"task",task_id,{"agent":t["agent_id"],"task_type":kind,"workflow_id":w["id"],"output":output})
  return {"status":status,"task_type":kind,"output":output}
 @router.post("/api/ai/tasks/{task_id}/run")
 def run_task(task_id:int,user=Depends(user_from_header)):
  return execute_task(task_id,user["tenant_id"])

 @router.get("/api/ai/health")
 def health(user=Depends(user_from_header)):
  with db() as c: c.execute("SELECT 1").fetchone()
  return {"status":"ok","tenant_isolated":True,"persistence":"sqlite","registered_agents":len(AGENTS),"live_llm_configured":active_ai_provider()["configured"],"ai_provider":active_ai_provider(),"external_channels_connected":False,"payment_execution_connected":False}
 @router.get("/api/ai/observability")
 def observability(user=Depends(user_from_header)):
  """Tenant-scoped operational snapshot; reports recorded state, not external system truth."""
  tid=user["tenant_id"]
  with db() as c:
   def count(sql,params=(tid,)):
    return int(c.execute(sql,params).fetchone()[0])
   workflows={
    "total":count("SELECT COUNT(*) FROM ai_workflows WHERE tenant_id=?"),
    "active":count("SELECT COUNT(*) FROM ai_workflows WHERE tenant_id=? AND status='active'"),
    "stale_over_72h":count("SELECT COUNT(*) FROM ai_workflows WHERE tenant_id=? AND status='active' AND updated_at < datetime('now','-72 hours')")
   }
   tasks={status:count("SELECT COUNT(*) FROM ai_agent_tasks WHERE tenant_id=? AND status=?",(tid,status)) for status in ("queued","blocked","needs_human","failed","completed")}
   approvals={status:count("SELECT COUNT(*) FROM ai_approvals WHERE tenant_id=? AND status=?",(tid,status)) for status in ("pending","approved","rejected")}
   followups={status:count("SELECT COUNT(*) FROM ai_followups WHERE tenant_id=? AND status=?",(tid,status)) for status in ("queued","draft_ready","cancelled","failed")}
   events=c.execute("SELECT id,actor_type,event_type,entity_type,entity_id,created_at FROM ai_audit_events WHERE tenant_id=? ORDER BY id DESC LIMIT 20",(tid,)).fetchall()
  return {
   "scope":"tenant",
   "generated_at_sql":"CURRENT_TIMESTAMP",
   "workflows":workflows,
   "agent_tasks":tasks,
   "approvals":approvals,
   "followups":followups,
   "recent_events":[dict(r) for r in events],
   "integrations":{"llm":active_ai_provider(),"messaging":"not_connected","catalog_inventory":"not_verified_as_connected","shipping":"not_connected","accounting_payment":"not_connected"},
   "safety_note":"شمارنده‌ها از پایگاه داده LEADORA هستند؛ تا زمان اتصال و آزمون سامانه‌های بیرونی، وضعیت زنده انبار، حمل، حسابداری یا پرداخت را اثبات نمی‌کنند."
  }

 return router
