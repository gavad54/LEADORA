# LEADORA Commercial Completion Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the existing LEADORA product safely for commercial web and Android operation, with independently verified data safety, identity/ownership, tenant isolation, financial correctness, and release evidence.

**Architecture:** Preserve the current FastAPI/SQLite/PWA/Android WebView architecture and the existing tenant data model. Continue from PR #46 (public-home and finance safeguards) and PR #49 (owner claim/recovery and transactional email); do not rebuild or replace the product. All production changes remain gated behind independently verified backup/restore and a reviewed, matched commit.

**Tech Stack:** Python 3.12, FastAPI, SQLite, Pydantic, pytest, Playwright/Chromium, HTML/CSS/JavaScript, Android Java/WebView, Gradle, GitHub Actions, Railway, Brevo transactional email.

## Global Constraints

- Preserve existing application structure, customer data, historical records, and supported workflows unless a reviewed change explicitly requires otherwise.
- Persian-first, RTL, mobile-first web and Android experience; public landing page is the entry point, and authentication appears only after the visitor chooses it.
- Keep tenant data isolated; a customer company must not access another company's records.
- Store monetary values in IRR as specified by the product; do not re-convert already converted historical amounts.
- Retire active participation-contract behavior without deleting historical participation records.
- Owner/license/support operations require least privilege, auditability, verified contact channels, and safe recovery.
- Never commit secrets, OTP values, signing keys, national identifiers, passwords, or live customer data.
- Do not perform production deploys, schema migrations on the live database, or volume changes until an independent backup outside Railway and a successful restore in a separate environment are evidenced.
- Do not publish an APK or web release unless the exact commit passes CI, security/regression, public-home acceptance, Android launch/UI acceptance, release signing, and UAT gates.
- A green build or emulator launch is not equivalent to commercial release readiness.

---

## Evidence Baseline — 2026-11-03

- PR #46 is open and unmerged; it contains the public landing/auth-flow, Android startup, finance safeguards, and legacy participation retirement.
- PR #49 is open and unmerged, based on `fix/public-home-optional-auth`; it contains owner claim/recovery and the Brevo adapter.
- On PR #49 HEAD `5b195f2cbf34baf61d685653f3e2e245eb4f9661`, regression/security passed **126 tests**, and CI including Python compile, JavaScript syntax, manifest, Compose validation, and Docker build passed.
- Android APK build, emulator install/launch, and artifact verification passed on that HEAD; the release gate failed because six public-home acceptance checks against the currently deployed Railway homepage failed. APK release publication was skipped.
- Railway Production still reports deployment `224694ef-5e27-42e8-bc8c-ac1d0975a7d2`, created 2026-10-21, with no staged changes. The `leadora-data` volume is mounted at `/data`, size 500 MB.
- No PR has an approving review. No independent off-platform backup/restore, official signing proof, or real-device UAT has been established.
- The Starlette/httpx TestClient deprecation warning remains.

## Task 1: Secure email-verified platform-owner transfer

**Files:**
- Create: `tests/test_owner_transfer.py`
- Modify: `app/main.py`
- Modify: `app/email_service.py`
- Modify: `app/static/platform-owner.html`
- Modify: `docs/BREVO_EMAIL_SETUP_FA.md`

**Interfaces:**
- Consumes: `user_from_header`, `db()`, `_is_platform_owner_id()`, `send_transactional_email()`, and the `finance_platform_owner` singleton row.
- Produces: owner-only transfer request, current-owner email confirmation, incoming-owner email acceptance, transfer status, audit events, and former-owner session invalidation.

- [ ] **Step 1: Add focused failing tests**
  - Request by non-owner returns 403.
  - Unknown target account, same owner account, invalid email, and unconfigured Brevo return safe errors without changing ownership.
  - A valid request sends two distinct codes: one to current owner's stored email and one to target account email; the response never includes either code.
  - Only code hashes are stored; codes are never persisted or logged.
  - Current-owner code and target-owner code are independently required; either order is supported.
  - Expired request, reused code, wrong code, and more than five attempts are rejected.
  - Only one active request can complete; concurrent/duplicate acceptance cannot create two owners.
  - Successful transfer updates the singleton owner row atomically, writes an audit event, and invalidates the former owner's existing sessions.
- [ ] **Step 2: Verify the relevant failure**
  - Run: `python -m pytest -q tests/test_owner_transfer.py`
  - Expected: tests fail because the transfer endpoints and pending-transfer state do not exist.
- [ ] **Step 3: Implement the minimum behavior**
  - Add a transfer-request table with request ID, old/new user IDs, current/target email hashes or normalized addresses as needed for routing, code hashes, expiry, attempt counters, confirmation flags, status, and timestamps.
  - Generate independent cryptographically random codes; store only SHA-256/HMAC fingerprints. Use a short expiry (10 minutes), a maximum of five attempts per code, and a cooldown per owner.
  - Require authenticated current owner to initiate. Require current owner to confirm their code and the target account to authenticate and confirm the target code.
  - Use `BEGIN IMMEDIATE` for confirmation and final owner update. Do not change owner until both confirmations are true.
  - Invalidate former-owner sessions using a revocation timestamp checked by `user_from_header`.
  - Add audit events for request, each confirmation, expiry/failure, and completed transfer. Never include codes or secrets in audit details.
  - Add UI forms for initiating, current-owner confirmation, and incoming-owner acceptance.
- [ ] **Step 4: Verify the focused pass**
  - Run: `python -m pytest -q tests/test_owner_transfer.py`
  - Expected: all transfer tests pass with mocked email transport.
- [ ] **Step 5: Run affected integration checks**
  - Run: `python -m pytest -q tests/test_email_service.py tests/test_finance.py tests/test_security_regression.py`
  - Run: `python -m compileall -q app`
  - Extract and run `node --check` for the owner page script through the existing CI workflow.
- [ ] **Step 6: Commit the passing deliverable**
  - Commit only the transfer module, focused tests, page, and email documentation changes.

## Task 2: Public landing and Android start-flow acceptance

**Files:**
- Modify: `app/static/index.html`
- Modify: `android/app/src/main/java/com/leadora/app/MainActivity.java`
- Modify: `.github/workflows/android-apk.yml`
- Test: `tests/test_public_home_contract.py`
- Test: `tests/test_browser_e2e.py`
- Test: `tests/test_android_workflow_contract.py`

**Interfaces:**
- Consumes: the public landing DOM contract (`publicHome`, `authOverlay`, `workspaceShell`, `showPublicHome()`, public login/start actions) and canonical Production URL.
- Produces: deterministic public-first web and Android startup, with authentication/workspace hidden until explicitly requested.

- [ ] **Step 1: Add focused browser and Android contract tests** for logged-out fresh install, existing session, reload, process recreation, back navigation, mobile viewport, and offline/network failure.
- [ ] **Step 2: Verify failures** with `python -m pytest -q tests/test_public_home_contract.py tests/test_browser_e2e.py tests/test_android_workflow_contract.py`.
- [ ] **Step 3: Fix startup state and WebView behavior** without bypassing Production acceptance checks. Preserve authenticated sessions but never restore a stale login overlay as the initial public screen.
- [ ] **Step 4: Verify** the focused tests and Android emulator workflow; inspect the screenshot and DOM evidence, not only Activity launch.
- [ ] **Step 5: Run** `python -m pytest -q`, `python -m compileall -q app`, and the Android workflow.
- [ ] **Step 6: Commit** the isolated startup correction.

## Task 3: Financial correctness, IRR invariants, and historical-data preservation

**Files:**
- Modify: `app/participation.py`
- Modify: `app/main.py`
- Modify: `tests/test_finance.py`
- Modify: `tests/test_legacy_participation_preservation.py`
- Modify: `tests/test_licensing_banking.py`
- Modify: `docs/PRODUCTION_READINESS_AUDIT_FA.md`

**Interfaces:**
- Consumes: existing tenant-scoped finance tables, Decimal calculations, legacy participation schema, and current IRR validation.
- Produces: deterministic IRR-only new writes, no double conversion of historical data, preserved legacy records, auditable corrections, and correct report-period behavior.

- [ ] **Step 1: Add boundary and migration tests** for zero, large whole-IRR amounts, fractional amounts, negative values, non-finite values, duplicate documents, report recalculation, historical records, and tenant boundaries.
- [ ] **Step 2: Verify failures** with focused finance and legacy-preservation tests.
- [ ] **Step 3: Correct only evidenced calculation or migration defects**; never bulk-convert live records without a read-only inventory, backup, and explicit migration plan.
- [ ] **Step 4: Verify** historical row counts and representative values remain unchanged in fixture databases.
- [ ] **Step 5: Run** `python -m pytest -q tests/test_finance.py tests/test_legacy_participation_preservation.py tests/test_licensing_banking.py`.
- [ ] **Step 6: Commit** the finance-only deliverable.

## Task 4: Tenant isolation, authorization, and application security

**Files:**
- Modify: `app/main.py`
- Modify: `app/participation.py`
- Modify: `tests/test_security_regression.py`
- Modify: `tests/test_route_regressions.py`
- Modify: `.github/workflows/regression-security.yml`

**Interfaces:**
- Consumes: current authentication token, tenant ID, owner authorization, database query conventions, and rate-limit tables.
- Produces: tenant-scoped access for all business routes, explicit role/owner checks, session revocation, request throttles, safe errors, and audit trails.

- [ ] **Step 1: Add adversarial tests** for cross-tenant reads/writes, IDOR, expired/suspended licenses, owner-only routes, revoked sessions, rate-limit bypass, malformed payloads, and legacy allowlist behavior.
- [ ] **Step 2: Verify failures** with `python -m pytest -q tests/test_security_regression.py tests/test_route_regressions.py`.
- [ ] **Step 3: Fix authorization at the server boundary**; frontend hiding is never treated as access control. Keep recovery fallback documented and tightly constrained.
- [ ] **Step 4: Verify** all denial paths return safe status codes without leaking tenant data or secrets.
- [ ] **Step 5: Run** the full security/regression workflow and inspect dependency warnings.
- [ ] **Step 6: Commit** security changes separately from UI work.

## Task 5: Independent backup and restore proof

**Files:**
- Inspect/modify: `app/main.py` backup and restore endpoints
- Create if needed: `scripts/backup_restore_acceptance.py`
- Test: `tests/test_security_regression.py`
- Modify: `docs/MASTER_EXECUTION_STATUS_FA.md`

**Interfaces:**
- Consumes: owner-authenticated backup endpoint, SQLite integrity/foreign-key checks, and a separately provisioned test environment.
- Produces: encrypted backup outside Railway Volume, checksum, manifest, independent restore, row-count and integrity evidence.

- [ ] **Step 1: Add tests** for unauthorized backup, interrupted backup, corrupted file, incompatible schema, foreign-key failure, and restore isolation.
- [ ] **Step 2: Verify** all failure cases reject safely.
- [ ] **Step 3: Implement or harden** streaming backup and offline verification without writing backups to the same Railway Volume.
- [ ] **Step 4: Execute** one owner-authorized backup to an external destination and restore it in a separate non-production environment; record hashes and verification outputs without exposing customer records.
- [ ] **Step 5: Verify** SQLite integrity, foreign keys, expected tables, tenant counts, and sampled aggregate totals.
- [ ] **Step 6: Commit** scripts/docs; Production remains untouched until independent proof is reviewed.

## Task 6: Android official signing and controlled release

**Files:**
- Modify: `android/app/build.gradle`
- Modify: `.github/workflows/android-release.yml`
- Modify: `.github/workflows/android-apk.yml`
- Modify: `docs/RELEASE_STATUS_FA.md`

**Interfaces:**
- Consumes: protected signing secrets, reviewed release commit, successful production homepage gate, and Android acceptance evidence.
- Produces: signed APK/AAB, certificate fingerprint, SHA-256, build provenance, and release artifact.

- [ ] **Step 1: Add workflow contract tests** for missing/invalid secrets, wrong branch, failed Production gate, unsigned artifacts, and checksum mismatch.
- [ ] **Step 2: Verify** each gate fails closed.
- [ ] **Step 3: Keep signing keys only in protected GitHub/Railway secret storage**; never upload a private key to chat or repository.
- [ ] **Step 4: Build and verify** release signature, certificate fingerprint, artifact checksum, and exact source commit.
- [ ] **Step 5: Run** emulator install/launch and real-device UAT before broad release.
- [ ] **Step 6: Publish** only after all release gates and required human approvals are complete.

## Task 7: Operational readiness, observability, and UAT

**Files:**
- Modify: `docs/MASTER_EXECUTION_STATUS_FA.md`
- Modify: `docs/PRODUCTION_READINESS_AUDIT_FA.md`
- Modify: `docs/QA_MATRIX_FA.md`
- Modify: `docs/RELEASE_STATUS_FA.md`
- Add tests under `tests/` only for confirmed uncovered behavior.

**Interfaces:**
- Consumes: verified CI results, production commit/deployment metadata, backup/restore evidence, security review, Android artifacts, and UAT findings.
- Produces: a dated release decision record with pass/fail/blocked evidence and rollback instructions.

- [ ] **Step 1: Define UAT scenarios** for public browsing, account creation/login, tenant separation, inventory, customer/distribution workflows, accounting, licensing, support, backup/restore, and owner transfer.
- [ ] **Step 2: Execute** browser automation and real-device scenarios using synthetic or authorized test data.
- [ ] **Step 3: Verify** every critical defect has a linked test or reproducible issue; do not label untested scenarios passed.
- [ ] **Step 4: Update** all release dashboards from current evidence, not old commit results.
- [ ] **Step 5: Run** full CI, regression/security, Android, production smoke, backup/restore, and review gates on one exact candidate commit.
- [ ] **Step 6: Approve or block** release; keep Production unchanged if any critical gate is open.

---

## Release decision gates

A commercial release is permitted only when all are true on the same candidate commit:

1. PR #46 and dependent PR #49 have completed review and are integrated in the intended order.
2. CI, regression/security, and browser acceptance pass.
3. Production public-home acceptance passes on the deployed commit.
4. Independent off-platform backup and isolated restore are verified.
5. Tenant isolation and IRR/history invariants pass.
6. Android Release is signed with the protected official key and checksum/certificate evidence is recorded.
7. Android real-device UAT and business workflow UAT pass.
8. Rollback and operational monitoring are documented.

Until then the authoritative status is **DEPLOYMENT BLOCKED**.

## Unresolved external prerequisites

- Owner authorization and a secure external destination for the independent Production backup/restore exercise.
- Authorized manager access to configure and verify the Brevo sender domain and protected API key in Railway.
- Official Android signing key and protected GitHub secrets.
- Human review/approval of PRs and UAT on a real Android device.
