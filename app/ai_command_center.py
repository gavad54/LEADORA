"""Tenant-isolated AI command center and lead-to-cash workflow foundation for LEADORA."""
import json
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
  """)
 def audit(c,tid,actor,actor_id,event,entity,eid,detail):
  c.execute("INSERT INTO ai_audit_events(tenant_id,actor_type,actor_id,event_type,entity_type,entity_id,detail_json) VALUES(?,?,?,?,?,?,?)",(tid,actor,actor_id,event,entity,eid,json.dumps(detail,ensure_ascii=False)))
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
   stages=[dict(r) for r in c.execute("SELECT stage,COUNT(*) count FROM ai_workflows WHERE tenant_id=? AND status='active' GROUP BY stage",(tid,)).fetchall()]
   recent=[dict(r) for r in c.execute("SELECT id,customer_name,stage,status,human_required,next_action,updated_at FROM ai_workflows WHERE tenant_id=? ORDER BY id DESC LIMIT 10",(tid,)).fetchall()]
  return {"summary":{"workflows_total":total,"workflows_active":active,"approvals_pending":pending,"open_conversations":conv},"stages":[{**r,"label":LABELS.get(r["stage"],r["stage"])} for r in stages],"recent_workflows":recent,"automation_policy":{"routine_actions":"only after verified data, permissions and policy checks","human_approval_gates":GATES,"live_llm_connected":False,"external_channels_connected":False,"payment_execution_connected":False}}
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
  if body.action in ("confirm_order","start_delivery","mark_settled") and not body.approved: raise HTTPException(409,"این اقدام نیازمند تأیید صریح انسانی است.")
  tid=user["tenant_id"]; stage,next_action=mapping[body.action]
  human=body.action in ("draft_contact","draft_offer","confirm_order","start_delivery","mark_settled")
  with db() as c:
   row=c.execute("SELECT id FROM ai_workflows WHERE id=? AND tenant_id=?",(workflow_id,tid)).fetchone()
   if not row: raise HTTPException(404,"فرایند یافت نشد.")
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
   c.execute("INSERT INTO ai_messages(tenant_id,conversation_id,role,content,intent,agent_id) VALUES(?,?, 'customer', ?, ?, 'sales_chat')",(tid,cid,msg,intent))
   answer=reply(msg,intent,body.customer_name)
   c.execute("INSERT INTO ai_messages(tenant_id,conversation_id,role,content,intent,agent_id) VALUES(?,?, 'assistant', ?, ?, 'sales_chat')",(tid,cid,answer,intent))
   audit(c,tid,"ai",None,"chat.responded","conversation",cid,{"intent":intent,"channel":body.channel})
   if handoff: c.execute("INSERT INTO ai_approvals(tenant_id,action,status,requested_by,note) VALUES(?,?,'pending','ai',?)",(tid,"human_handoff",f"گفت‌وگوی {cid}: ارجاع انسانی، قصد={intent}"))
  return {"conversation_id":cid,"intent":intent,"agent":"sales_chat","reply":answer,"handoff_required":handoff,"automation":{"live_llm":False,"external_message_sent":False,"consent_to_follow_up":body.consent_to_follow_up}}
 @router.get("/api/ai/chat/{conversation_id}")
 def history(conversation_id:int,user=Depends(user_from_header)):
  with db() as c:
   conv=c.execute("SELECT id,customer_name,phone,channel,consent_to_follow_up,status,created_at FROM ai_conversations WHERE id=? AND tenant_id=?",(conversation_id,user["tenant_id"])).fetchone()
   if not conv: raise HTTPException(404,"گفت‌وگو یافت نشد.")
   messages=[dict(r) for r in c.execute("SELECT id,role,content,intent,agent_id,created_at FROM ai_messages WHERE conversation_id=? AND tenant_id=? ORDER BY id",(conversation_id,user["tenant_id"])).fetchall()]
  return {"conversation":dict(conv),"messages":messages}
 @router.get("/api/ai/health")
 def health(user=Depends(user_from_header)):
  with db() as c: c.execute("SELECT 1").fetchone()
  return {"status":"ok","tenant_isolated":True,"persistence":"sqlite","registered_agents":len(AGENTS),"live_llm_connected":False,"external_channels_connected":False,"payment_execution_connected":False}
 return router
