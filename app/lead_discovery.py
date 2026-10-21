"""Tenant-isolated lead discovery from user-provided public business sources."""
import os, re, json, html, socket, ipaddress, urllib.request, urllib.parse, urllib.error
from html.parser import HTMLParser
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl

MAX_SOURCE_BYTES = 900_000
USER_AGENT = "LEADORA-LeadDiscovery/1.0 (+public business research)"
class SourceIn(BaseModel):
    kind: str = Field(default="website", pattern="^(website|store|app|chat|text)$")
    url: str = Field(default="", max_length=2048)
    content: str = Field(default="", max_length=12000)
    label: str = Field(default="", max_length=160)
class DiscoverIn(BaseModel):
    sources: list[SourceIn] = Field(min_length=1, max_length=10)
    goal: str = Field(default="both", pattern="^(customers|suppliers|both)$")
    industry: str = Field(default="", max_length=160)
    markets: list[str] = Field(default_factory=list, max_length=12)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    limit: int = Field(default=10, ge=1, le=25)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.title=False; self.title_text=[]; self.text=[]; self.meta={}; self.links=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag in ("script","style","noscript","svg"): self.skip+=1
        if tag=="title": self.title=True
        if tag=="meta" and (a.get("name") or a.get("property")):
            self.meta[(a.get("name") or a.get("property")).lower()]=a.get("content","")[:1200]
        if tag=="a" and a.get("href") and len(self.links)<250: self.links.append((a.get("href")[:1000],a.get("aria-label","")[:160]))
    def handle_endtag(self, tag):
        if tag=="title": self.title=False
        if tag in ("script","style","noscript","svg") and self.skip: self.skip-=1
    def handle_data(self,data):
        if self.skip:return
        value=" ".join(data.split())
        if not value:return
        if self.title:self.title_text.append(value)
        if len(self.text)<8000:self.text.append(value)

def _validate_public_url(raw):
    try: u=urllib.parse.urlsplit(raw.strip())
    except Exception: raise HTTPException(422,"نشانی منبع معتبر نیست.")
    if u.scheme not in ("http","https") or not u.hostname or u.username or u.password:
        raise HTTPException(422,"فقط نشانی عمومی HTTP/HTTPS پذیرفته می‌شود.")
    host=u.hostname.rstrip(".").lower()
    if host in ("localhost","localhost.localdomain") or host.endswith(".local") or host.endswith(".internal"):
        raise HTTPException(422,"نشانی داخلی یا محلی مجاز نیست.")
    try:
        infos=socket.getaddrinfo(host,u.port or (443 if u.scheme=="https" else 80),type=socket.SOCK_STREAM)
        if not infos: raise ValueError()
        for info in infos:
            ip=ipaddress.ip_address(info[4][0].split("%")[0])
            if not ip.is_global: raise HTTPException(422,"نشانی‌های خصوصی، محلی یا رزروشده قابل دریافت نیستند.")
    except HTTPException: raise
    except Exception: raise HTTPException(422,"میزبان نشانی قابل بررسی نیست.")
    return u

def _fetch_public_page(raw):
    current=raw
    for _ in range(4):
        u=_validate_public_url(current)
        req=urllib.request.Request(current,headers={"User-Agent":USER_AGENT,"Accept":"text/html,application/xhtml+xml;q=0.9"})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPHandler(),urllib.request.HTTPSHandler())
        try:
            with opener.open(req,timeout=7) as response:
                final=response.geturl()
                if final!=current:
                    _validate_public_url(final)
                ctype=response.headers.get("Content-Type","").lower()
                if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
                    raise HTTPException(415,"این منبع صفحه وب متنی نیست؛ توضیحات یا متن عمومی آن را وارد کنید.")
                data=response.read(MAX_SOURCE_BYTES+1)
                if len(data)>MAX_SOURCE_BYTES: raise HTTPException(413,"حجم صفحه بیش از حد مجاز است.")
                charset=response.headers.get_content_charset() or "utf-8"
                return final,data.decode(charset,errors="replace")
        except HTTPException: raise
        except urllib.error.HTTPError as e:
            if e.code in (301,302,303,307,308) and e.headers.get("Location"):
                current=urllib.parse.urljoin(current,e.headers["Location"]); continue
            raise HTTPException(422,f"دریافت صفحه ناموفق بود (HTTP {e.code}).")
        except Exception:
            raise HTTPException(422,"دریافت صفحه ناموفق بود؛ نشانی عمومی، دسترسی و اتصال سرور را بررسی کنید.")
    raise HTTPException(422,"تعداد تغییرمسیرهای صفحه بیش از حد مجاز است.")

def _clean(s):
    return re.sub(r"\s+"," ",html.unescape(str(s or ""))).strip()

def _source_profile(source):
    if source.url.strip():
        final,raw=_fetch_public_page(source.url)
        p=PageParser()
        try:p.feed(raw)
        except Exception:pass
        title=_clean(" ".join(p.title_text))[:240]
        desc=_clean(p.meta.get("description") or p.meta.get("og:description") or p.meta.get("twitter:description"))[:1000]
        og=_clean(p.meta.get("og:site_name") or p.meta.get("application-name"))[:160]
        text=_clean(" ".join(p.text))[:6500]
        # Extract only business-facing internal links; never collect personal profile details.
        base=urllib.parse.urlsplit(final)
        paths=[]
        for href,label in p.links:
            target=urllib.parse.urljoin(final,href)
            t=urllib.parse.urlsplit(target)
            if t.hostname==base.hostname and t.scheme in ("http","https") and any(k in (t.path+" "+label).lower() for k in ("product","service","catalog","shop","store","about","contact","category")):
                paths.append({"url":target[:1000],"label":_clean(label)[:120]})
        return {"kind":source.kind,"label":source.label or og or title or base.hostname,"url":final,"title":title,"description":desc,"text":text,"business_links":paths[:30],"status":"scanned"}
    if not source.content.strip():
        raise HTTPException(422,"برای هر منبع، نشانی یا متن عمومی وارد کنید.")
    return {"kind":source.kind,"label":source.label or source.kind,"url":"","title":source.label,"description":"","text":_clean(source.content)[:6500],"business_links":[],"status":"provided_text"}

def _search_tavily(query, limit):
    key=os.getenv("TAVILY_API_KEY","").strip()
    if not key:return None
    payload=json.dumps({"api_key":key,"query":query,"search_depth":"basic","max_results":min(10,limit),"include_answer":False,"include_raw_content":False}).encode()
    req=urllib.request.Request("https://api.tavily.com/search",data=payload,headers={"Content-Type":"application/json","Accept":"application/json","User-Agent":USER_AGENT},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=12) as r: data=json.loads(r.read(1_500_000).decode("utf-8"))
        out=[]
        for x in data.get("results",[]):
            url=str(x.get("url",""))
            if not url.startswith(("http://","https://")):continue
            out.append({"name":_clean(x.get("title"))[:240],"url":url[:1500],"summary":_clean(x.get("content"))[:1000],"source":"web_search","score":x.get("score")})
        return out
    except Exception:
        raise HTTPException(502,"سرویس جست‌وجوی وب تنظیم شده اما در دسترس نیست؛ وضعیت TAVILY_API_KEY و اتصال سرور را بررسی کنید.")

def install_lead_discovery(app, db, user_from_header, ROOT):
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS lead_discovery_runs(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
          goal TEXT NOT NULL, profile_json TEXT NOT NULL, queries_json TEXT NOT NULL,
          provider TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS discovered_leads(
          id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, run_id INTEGER,
          name TEXT NOT NULL, url TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
          lead_type TEXT NOT NULL DEFAULT 'unknown', source TEXT NOT NULL DEFAULT 'web_search',
          status TEXT NOT NULL DEFAULT 'new', confidence REAL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(tenant_id,url));
        CREATE INDEX IF NOT EXISTS idx_discovered_leads_tenant_status ON discovered_leads(tenant_id,status);
        """)
    @app.get("/lead-discovery")
    def lead_discovery_page():
        return FileResponse(ROOT/"static"/"lead-discovery.html")
    @app.get("/api/lead-discovery/status")
    def lead_discovery_status(u=Depends(user_from_header)):
        return {"web_search_configured":bool(os.getenv("TAVILY_API_KEY","").strip()),
                "providers":["Tavily"] if os.getenv("TAVILY_API_KEY","").strip() else [],
                "source_types":["website","store","app","chat","text"],
                "max_sources":10,"max_results":25,
                "message":"بدون کلید جست‌وجوی وب، تحلیل منابع واردشده و ساخت عبارت‌های جست‌وجو فعال است؛ کشف آنلاین تا تنظیم TAVILY_API_KEY فعال نمی‌شود."}
    @app.post("/api/lead-discovery/run")
    def run_discovery(p:DiscoverIn,u=Depends(user_from_header)):
        with db() as c:
            recent=c.execute("SELECT COUNT(*) n FROM lead_discovery_runs WHERE tenant_id=? AND created_at>=datetime('now','-1 day')",(u["tenant_id"],)).fetchone()["n"]
        if recent>=30:raise HTTPException(429,"سقف ۳۰ اجرای مشتریابی در ۲۴ ساعت برای این شرکت تکمیل شده است.")
        profiles=[]
        for source in p.sources:
            profiles.append(_source_profile(source))
        public_profiles=[{k:v for k,v in item.items() if k!="text"} for item in profiles]
        all_text=" ".join(" ".join((x.get("label",""),x.get("title",""),x.get("description",""),x.get("text",""))) for x in profiles)
        # Keep only bounded, user-supplied business keywords; no personal-data inference.
        words=[]
        for word in re.findall(r"[A-Za-z0-9\u0600-\u06FF][A-Za-z0-9\u0600-\u06FF&+.-]{2,}",all_text.lower()):
            if word not in words and word not in ("https","http","www","com","the","and","for","with","this","that","from","your","our","you","are","www","شرکت","برای","این","است","های","فروشگاه","محصولات"):
                words.append(word)
            if len(words)>=18:break
        keywords=list(dict.fromkeys([_clean(x)[:80] for x in p.keywords if _clean(x)]+words))[:25]
        markets=[_clean(x)[:80] for x in p.markets if _clean(x)][:8]
        industry=_clean(p.industry)[:160]
        queries=[]
        kinds=["customers","suppliers"] if p.goal=="both" else [p.goal]
        for kind in kinds:
            label="potential buyers/customers" if kind=="customers" else "suppliers/manufacturers/distributors"
            terms=" ".join(keywords[:8])
            sector=industry or terms or "business products and services"
            market=" ".join(markets[:3])
            queries.append({"type":kind,"query":_clean(f'{label} for {sector} {terms} {market}').strip()[:400]})
            if terms:
                queries.append({"type":kind,"query":_clean(f'{sector} {terms} {label} {market} official website').strip()[:400]})
        # Deduplicate query strings.
        seen=set(); queries=[q for q in queries if not (q["query"].lower() in seen or seen.add(q["query"].lower()))][:6]
        candidates=[]
        for q in queries:
            found=_search_tavily(q["query"],max(3,p.limit//max(1,len(queries))))
            if found is not None:
                for item in found:
                    item["lead_type"]=q["type"]
                    if item["url"] not in {x["url"] for x in candidates}:candidates.append(item)
        provider="tavily" if os.getenv("TAVILY_API_KEY","").strip() else "query_generation_only"
        with db() as c:
            cur=c.execute("INSERT INTO lead_discovery_runs(tenant_id,user_id,goal,profile_json,queries_json,provider) VALUES(?,?,?,?,?,?)",
                (u["tenant_id"],u["id"],p.goal,json.dumps(public_profiles,ensure_ascii=False),json.dumps(queries,ensure_ascii=False),provider))
            run_id=cur.lastrowid
            saved=[]
            for item in candidates[:p.limit]:
                try:
                    cur=c.execute("INSERT INTO discovered_leads(tenant_id,run_id,name,url,summary,lead_type,source,confidence) VALUES(?,?,?,?,?,?,?,?)",
                        (u["tenant_id"],run_id,item["name"] or item["url"],item["url"],item["summary"],item["lead_type"],item["source"],item.get("score")))
                    saved.append({"id":cur.lastrowid,**item,"status":"new"})
                except Exception:
                    row=c.execute("SELECT id,name,url,summary,lead_type,source,status,confidence FROM discovered_leads WHERE tenant_id=? AND url=?",(u["tenant_id"],item["url"])).fetchone()
                    if row:saved.append(dict(row))
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(u["tenant_id"],"lead_discovery.run:"+str(run_id)))
        return {"run_id":run_id,"profile":public_profiles,"keywords":keywords,"queries":queries,
                "provider":provider,"search_configured":provider=="tavily","results":saved,
                "result_count":len(saved),"message":("کشف آنلاین انجام شد؛ نتایج باید از نظر تناسب و اعتبار بررسی شوند." if provider=="tavily" else "منابع تحلیل و عبارت‌های جست‌وجو ساخته شدند؛ برای یافتن خودکار شرکت‌های واقعی، مدیر سامانه باید TAVILY_API_KEY را در متغیرهای امن Railway تنظیم کند.")}
    @app.get("/api/lead-discovery/leads")
    def list_discovered_leads(status:str="",limit:int=100,u=Depends(user_from_header)):
        if limit<1 or limit>300:raise HTTPException(422,"limit باید بین ۱ تا ۳۰۰ باشد.")
        with db() as c:
            if status and status not in ("new","qualified","contacted","won","lost","ignored"):raise HTTPException(422,"وضعیت نامعتبر است.")
            if status:
                rows=c.execute("SELECT id,name,url,summary,lead_type,source,status,confidence,created_at FROM discovered_leads WHERE tenant_id=? AND status=? ORDER BY id DESC LIMIT ?",(u["tenant_id"],status,limit)).fetchall()
            else:
                rows=c.execute("SELECT id,name,url,summary,lead_type,source,status,confidence,created_at FROM discovered_leads WHERE tenant_id=? ORDER BY id DESC LIMIT ?",(u["tenant_id"],limit)).fetchall()
        return [dict(r) for r in rows]
    @app.patch("/api/lead-discovery/leads/{lead_id}")
    def update_discovered_lead(lead_id:int,p:dict,u=Depends(user_from_header)):
        status=p.get("status")
        if status not in ("new","qualified","contacted","won","lost","ignored"):raise HTTPException(422,"وضعیت نامعتبر است.")
        with db() as c:
            cur=c.execute("UPDATE discovered_leads SET status=? WHERE id=? AND tenant_id=?",(status,lead_id,u["tenant_id"]))
            if not cur.rowcount:raise HTTPException(404,"سرنخ یافت نشد.")
            c.execute("INSERT INTO audit_log(tenant_id,action) VALUES(?,?)",(u["tenant_id"],"lead_discovery.lead_status:"+str(lead_id)+":"+status))
        return {"id":lead_id,"status":status}
