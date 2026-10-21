import uuid
from fastapi.testclient import TestClient
from app.main import app

def make_account():
    c=TestClient(app); s=uuid.uuid4().hex[:10]
    r=c.post("/api/register",json={"company_name":"Prospect "+s,"industry":"distribution","email":"prospect-"+s+"@example.com","password":"test-password-2026"})
    assert r.status_code==200,r.text
    return c,{"Authorization":"Bearer "+r.json()["token"]}

def test_text_source_generates_customer_and_supplier_queries(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY",raising=False)
    c,h=make_account()
    r=c.post("/api/lead-discovery/run",headers=h,json={
        "sources":[{"kind":"text","label":"کاتالوگ","content":"We manufacture industrial pumps, valves and water treatment equipment for distributors."}],
        "goal":"both","industry":"industrial equipment","markets":["Germany","Turkey"],"keywords":["pump","valve"],"limit":10
    })
    assert r.status_code==200,r.text
    d=r.json()
    assert d["provider"]=="query_generation_only"
    assert d["search_configured"] is False
    assert d["result_count"]==0
    assert any(q["type"]=="customers" for q in d["queries"])
    assert any(q["type"]=="suppliers" for q in d["queries"])
    assert d["run_id"]>0

def test_discovered_leads_are_tenant_isolated(monkeypatch):
    import app.lead_discovery as discovery
    monkeypatch.setenv("TAVILY_API_KEY","test-key")
    monkeypatch.setattr(discovery,"_search_tavily",lambda query,limit:[{"name":"Example Wholesale","url":"https://example.org/business","summary":"Public business listing","source":"web_search","score":0.91}])
    c,a=make_account(); _,b=make_account()
    r=c.post("/api/lead-discovery/run",headers=a,json={
        "sources":[{"kind":"text","label":"profile","content":"Wholesale coffee beans and espresso machines"}],
        "goal":"customers","industry":"coffee wholesale","limit":5
    })
    assert r.status_code==200,r.text
    assert r.json()["result_count"]==1
    assert len(c.get("/api/lead-discovery/leads",headers=a).json())==1
    assert c.get("/api/lead-discovery/leads",headers=b).json()==[]
    lead_id=r.json()["results"][0]["id"]
    changed=c.patch(f"/api/lead-discovery/leads/{lead_id}",headers=a,json={"status":"qualified"})
    assert changed.status_code==200,changed.text
    shared=c.get("/api/prospecting/business-leads?status=qualified",headers=a).json()
    assert shared["total"]==1 and shared["items"][0]["website"]=="https://example.org/business"
    assert c.get("/api/prospecting/business-leads?status=qualified",headers=b).json()["total"]==0

def test_public_url_validation_rejects_private_hosts(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY",raising=False)
    c,h=make_account()
    r=c.post("/api/lead-discovery/run",headers=h,json={
        "sources":[{"kind":"website","url":"http://127.0.0.1/admin"}],"goal":"both"
    })
    assert r.status_code==422,r.text
