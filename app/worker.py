"""LEADORA scheduled business discovery worker.

Runs independently of browser/app sessions. It only queries the public OpenStreetMap
Overpass endpoint, with conservative rate limits. Other providers require official
credentials/licensing and are not scraped by this worker.
"""
import json
import os
import socket
import time
import urllib.error
import urllib.request

from app import main

DB_PATH = main.DB_PATH
OWNER = f"{socket.gethostname()}:{os.getpid()}"
POLL_SECONDS = max(5, int(os.getenv("LEADORA_WORKER_POLL_SECONDS", "15")))
GLOBAL_MIN_INTERVAL = max(900, int(os.getenv("LEADORA_SOURCE_MIN_INTERVAL_SECONDS", "900")) )
MAX_BACKOFF = 21600


def ensure_worker_tables():
    with main.db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS prospecting_worker_lease(
          id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT NOT NULL DEFAULT '',
          lease_until REAL NOT NULL DEFAULT 0, last_external_request_at REAL NOT NULL DEFAULT 0,
          heartbeat_at REAL NOT NULL DEFAULT 0
        )""")
        columns = {r["name"] for r in c.execute("PRAGMA table_info(prospecting_worker_lease)").fetchall()}
        if "heartbeat_at" not in columns:
            c.execute("ALTER TABLE prospecting_worker_lease ADD COLUMN heartbeat_at REAL NOT NULL DEFAULT 0")
        c.execute("INSERT OR IGNORE INTO prospecting_worker_lease(id,owner,lease_until,last_external_request_at,heartbeat_at) VALUES(1,'',0,0,0)")


def acquire_lease():
    now = time.time()
    with main.db() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT owner,lease_until FROM prospecting_worker_lease WHERE id=1").fetchone()
        if row and row["lease_until"] > now and row["owner"] != OWNER:
            c.rollback()
            return False
        c.execute("UPDATE prospecting_worker_lease SET owner=?,lease_until=?,heartbeat_at=? WHERE id=1", (OWNER, now + 60, now))
        c.commit()
    return True


def release_lease():
    with main.db() as c:
        c.execute("UPDATE prospecting_worker_lease SET owner='',lease_until=0 WHERE id=1 AND owner=?", (OWNER,))


def run_one_due_tenant():
    now = time.time()
    with main.db() as c:
        row = c.execute("""SELECT s.* FROM prospecting_settings s
          WHERE s.enabled=1 AND s.next_run_at<=?
          ORDER BY s.next_run_at ASC LIMIT 1""", (now,)).fetchone()
        lease = c.execute("SELECT last_external_request_at FROM prospecting_worker_lease WHERE id=1").fetchone()
    if not row:
        return False
    if lease and now - float(lease["last_external_request_at"] or 0) < GLOBAL_MIN_INTERVAL:
        return False

    tenant_id = row["tenant_id"]
    query = main._overpass_query(row["latitude"], row["longitude"], row["radius_m"], row["category"])
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=query.encode("utf-8"),
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "User-Agent": "LEADORA/1.0 (scheduled business discovery; contact configured by deployment owner)",
        },
        method="POST",
    )
    attempted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with main.db() as c:
        c.execute("UPDATE prospecting_worker_lease SET last_external_request_at=? WHERE id=1 AND owner=?", (now, OWNER))
        c.execute("UPDATE prospecting_settings SET last_attempt_at=? WHERE tenant_id=?", (attempted_at, tenant_id))
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read(12_000_000).decode("utf-8"))
        elements = payload.get("elements", [])[:500]
        imported = updated = rejected = 0
        with main.db() as c:
            for element in elements:
                item = main._normalize_osm_element(element)
                if not item:
                    rejected += 1
                    continue
                row_data = {
                    "name": item["name"], "category": item["category"], "phone": item["phone"],
                    "website": item["website"], "address": item["address"], "city": item["city"],
                    "region": item["region"], "latitude": item["latitude"], "longitude": item["longitude"],
                    "source_url": item["source_url"], "source_record_id": f'{item["osm_type"]}/{item["osm_id"]}',
                }
                fingerprint = main._lead_fingerprint(row_data["name"], row_data["phone"], row_data["website"], row_data["city"], row_data["address"])
                existed = c.execute("SELECT id FROM business_leads WHERE tenant_id=? AND fingerprint=?", (tenant_id, fingerprint)).fetchone()
                c.execute("""INSERT INTO business_leads
                  (tenant_id,source,source_record_id,name,category,phone,website,address,city,region,latitude,longitude,source_url,fingerprint)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(tenant_id,fingerprint) DO UPDATE SET
                    source=excluded.source,
                    source_record_id=CASE WHEN excluded.source_record_id!='' THEN excluded.source_record_id ELSE business_leads.source_record_id END,
                    category=CASE WHEN excluded.category!='' THEN excluded.category ELSE business_leads.category END,
                    phone=CASE WHEN excluded.phone!='' THEN excluded.phone ELSE business_leads.phone END,
                    website=CASE WHEN excluded.website!='' THEN excluded.website ELSE business_leads.website END,
                    address=CASE WHEN excluded.address!='' THEN excluded.address ELSE business_leads.address END,
                    city=CASE WHEN excluded.city!='' THEN excluded.city ELSE business_leads.city END,
                    region=CASE WHEN excluded.region!='' THEN excluded.region ELSE business_leads.region END,
                    latitude=COALESCE(excluded.latitude,business_leads.latitude),
                    longitude=COALESCE(excluded.longitude,business_leads.longitude),
                    source_url=CASE WHEN excluded.source_url!='' THEN excluded.source_url ELSE business_leads.source_url END,
                    last_seen_at=CURRENT_TIMESTAMP""",
                  (tenant_id,"OpenStreetMap",row_data["source_record_id"],row_data["name"],row_data["category"],row_data["phone"],row_data["website"],row_data["address"],row_data["city"],row_data["region"],row_data["latitude"],row_data["longitude"],row_data["source_url"],fingerprint))
                if existed: updated += 1
                else: imported += 1
            c.execute("UPDATE prospecting_settings SET last_success_at=?,last_error='',consecutive_failures=0,next_run_at=?,updated_at=CURRENT_TIMESTAMP WHERE tenant_id=?",
                      (attempted_at, time.time() + int(row["interval_seconds"]), tenant_id))
            c.execute("INSERT INTO prospecting_worker_events(tenant_id,event_type,message,found) VALUES(?,?,?,?)",
                      (tenant_id,"success",f"OpenStreetMap: {imported} new, {updated} updated, {rejected} skipped", imported + updated))
            c.execute("INSERT INTO business_source_runs(tenant_id,source,status,imported,updated,rejected,message) VALUES(?,?,?,?,?,?,?)",
                      (tenant_id,"OpenStreetMap","completed" if rejected == 0 else "completed_with_rejections",imported,updated,rejected,"Scheduled discovery run"))
        print(f"[worker] tenant={tenant_id} imported={imported} updated={updated} rejected={rejected}", flush=True)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
        with main.db() as c:
            current = c.execute("SELECT consecutive_failures,interval_seconds FROM prospecting_settings WHERE tenant_id=?", (tenant_id,)).fetchone()
            failures = int(current["consecutive_failures"] if current else 0) + 1
            backoff = min(MAX_BACKOFF, max(int(row["interval_seconds"]), 300) * (2 ** min(failures - 1, 4)))
            message = str(exc)[:240]
            c.execute("UPDATE prospecting_settings SET last_error=?,consecutive_failures=?,next_run_at=?,updated_at=CURRENT_TIMESTAMP WHERE tenant_id=?",
                      (message, failures, time.time() + backoff, tenant_id))
            c.execute("INSERT INTO prospecting_worker_events(tenant_id,event_type,message,found) VALUES(?,?,?,0)",
                      (tenant_id,"error",message))
            c.execute("INSERT INTO business_source_runs(tenant_id,source,status,message) VALUES(?,?,?,?)",
                      (tenant_id,"OpenStreetMap","failed",message))
        print(f"[worker] tenant={tenant_id} failed; retry in {backoff}s: {message}", flush=True)
    return True


def main_loop():
    ensure_worker_tables()
    print(f"[worker] started owner={OWNER} db={DB_PATH}", flush=True)
    while True:
        try:
            if acquire_lease():
                try:
                    run_one_due_tenant()
                finally:
                    release_lease()
        except Exception as exc:
            # Keep the service alive after transient database/network/program errors.
            print(f"[worker] loop error: {type(exc).__name__}: {str(exc)[:240]}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main_loop()
