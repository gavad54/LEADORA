import uuid
from fastapi.testclient import TestClient
from app.main import app

def account():
    c=TestClient(app); s=uuid.uuid4().hex[:10]
    r=c.post("/api/register",json={"company_name":"CO "+s,"industry":"services","email":"co-"+s+"@example.com","password":"test-password-2026"})
    assert r.status_code==200,r.text
    return c,{"Authorization":"Bearer "+r.json()["token"]}

def test_support_tickets_are_tenant_isolated():
    c,a=account(); _,b=account()
    r=c.post("/api/support/tickets",headers=a,json={"subject":"خطای گزارش","description":"گزارش فروش باز نمی‌شود","priority":"high"})
    assert r.status_code==200,r.text
    ticket=r.json()
    assert ticket["status"]=="open" and ticket["tenant_id"] != 0
    assert any(x["id"]==ticket["id"] for x in c.get("/api/support/tickets",headers=a).json())
    assert all(x["id"]!=ticket["id"] for x in c.get("/api/support/tickets",headers=b).json())
    assert c.patch(f"/api/support/tickets/{ticket['id']}",headers=b,json={"status":"closed"}).status_code==404

def test_cross_module_event_creates_approval_gated_steps():
    c,h=account()
    r=c.post("/api/automation/events",headers=h,json={"event_type":"sales.order_created","source_ref":"ORDER-1","payload":{"order_id":"ORDER-1"}})
    assert r.status_code==200,r.text
    steps=r.json()["steps"]
    assert any(s["action_key"]=="inventory.check" and s["status"]=="queued" for s in steps)
    gated=next(s for s in steps if s["requires_approval"])
    assert gated["status"]=="pending_approval"
    approved=c.post(f"/api/automation/steps/{gated['id']}/decision",headers=h,json={"decision":"approve","note":"بررسی شد"})
    assert approved.status_code==200 and approved.json()["status"]=="approved"
    assert c.post(f"/api/automation/steps/{gated['id']}/decision",headers=h,json={"decision":"approve"}).status_code==409

def test_automation_runs_are_tenant_isolated_and_unknown_events_rejected():
    c,a=account(); _,b=account()
    assert c.post("/api/automation/events",headers=a,json={"event_type":"not.a.real.event"}).status_code==422
    r=c.post("/api/automation/events",headers=a,json={"event_type":"inventory.low_stock","source_ref":"SKU-7"})
    assert r.status_code==200,r.text
    assert any(x["run_id"]==r.json()["run_id"] for x in c.get("/api/automation/runs",headers=a).json())
    assert all(x["run_id"]!=r.json()["run_id"] for x in c.get("/api/automation/runs",headers=b).json())
