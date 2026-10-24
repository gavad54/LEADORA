> **وضعیت سند: تاریخی/بازنشسته.** طرح اولیه مشارکت مالی مالک دیگر نیازمندی فعال محصول نیست. PR شماره 46 مسیرهای قرارداد، سهم مالک، داشبورد مشارکت و تسویه سهم را حذف می‌کند. این سند صرفاً برای سابقه تصمیم‌ها نگهداری شده و نباید برای افزودن مجدد این قابلیت استفاده شود؛ داده‌های تاریخی بدون سیاست نگهداری و مهاجرت تأییدشده پاک نمی‌شوند.

# LEADORA Financial Participation Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tenant-isolated financial participation workflows and a responsive web/PWA interface to the existing LEADORA application.

**Architecture:** Keep the existing FastAPI/SQLite app and authentication as the source of identity. Add a focused `app/participation.py` router using the existing database factory and tenant-scoped user dependency, plus a separate `app/static/finance.html` view served at `/finance`. Restrict platform-owner routes to the protected `LEADORA_OWNER_EMAILS` allowlist.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite, HTML/CSS/JavaScript, pytest, existing GitHub Actions CI and Android WebView build.

## Global Constraints

- Keep each company's records tenant-scoped; owner-only cross-company operations require an explicit email allowlist.
- Store money as decimal strings and calculate using Python `Decimal`.
- Free trial alone never creates an owner share; contract activation, goal approval, and trial-end conditions must all be satisfied.
- Separate permanent license/support income from contractual profit share.
- No fictional external integrations: API-based synchronization stays marked not configured until provider credentials and mapping exist.
- Preserve closed reports; reject recalculation after approval/closure.
- This module does not replace the company's accounting system or independently validate legal contracts.
- Do not claim production deployment, device testing, or release signing unless the respective check actually passes.

---

### Task 1: Contract, source settings, ledger entries, reports, and owner authorization

**Files:**
- Create: `app/participation.py`
- Modify: `app/main.py`
- Test: `tests/test_finance.py`

**Interfaces:**
- `create_router(db_factory, user_dependency) -> APIRouter`
- API prefix: `/api/finance`
- Owner authorization: `LEADORA_OWNER_EMAILS` comma-separated allowlist

- [x] Add independent company source settings for manual, CSV, and integration methods.
- [x] Add contract, goal decision, monthly ledger, report approval/objection, settlement, owner overview, and audit routes.
- [x] Add focused tests for tenant isolation, duplicate documents, CSV rejections, calculations, contract goal gates, and closed-report immutability.
- [ ] Run Python compilation and pytest in CI; fix every observed failure.

### Task 2: Responsive web/PWA experience

**Files:**
- Create: `app/static/finance.html`
- Modify: `app/static/index.html`, `app/main.py`

**Interfaces:**
- `GET /finance`
- The page reuses `localStorage.leadora_token` and the existing Bearer token.

- [x] Add method settings, manual entry, CSV import, monthly report calculation, contract summary, owner dashboard, approval, objection, and audit UI.
- [x] Add a navigation link from the main responsive app.
- [ ] Run browser JavaScript syntax checks and verify PWA route responses in CI.

### Task 3: Operational documentation and build verification

**Files:**
- Modify: `README.md`, `SECURITY.md`
- Existing workflows: `.github/workflows/ci.yml`, `.github/workflows/android-apk.yml`

- [x] Document owner allowlist, source-integration limits, calculation basis, and security caveats.
- [ ] Verify current branch CI, including Docker and Android build workflow.
- [ ] Inspect live health and release artifacts before claiming production rollout.
- [ ] Report any required deployment secret or third-party credential that cannot be safely set by repository code.
