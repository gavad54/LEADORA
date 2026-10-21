# LEADORA Multi-Tenant Licensing and Company Banking Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn LEADORA into a licensable multi-company SaaS where the product owner sells and supports the application, each tenant independently controls its data and bank/payment connections, trial access expires after at most 90 days, and participation-contract workflows are removed from the product.

**Architecture:** Preserve the current FastAPI application and persistent SQLite database while introducing explicit tenant ownership and tenant-scoped access checks before expanding data models. The platform owner manages product licenses and support; tenant admins manage only their own users, data, modules, and multiple bank/payment configurations. Payment provider integration is adapter-based: manual bank-account records are supported without pretending to transfer funds, while real payments require a provider implementation, signed webhooks, and merchant credentials configured by each tenant.

**Tech Stack:** Existing Python/FastAPI, SQLite on Railway persistent volume, HTML/JavaScript frontend, pytest/httpx, Playwright, GitHub Actions, Railway.

## Global Constraints

- The platform owner and customer-company ownership are separate roles and data domains.
- A tenant must never read or mutate another tenant's records, users, bank settings, reports, license keys, or audit events.
- A company can configure multiple bank accounts and payment-provider connections independently.
- Credentials and secrets must never be returned by API responses or written to logs. Provider secrets must be encrypted at rest using a dedicated deployment secret; never store raw bank login passwords.
- A trial lasts no longer than 90 days from its server-recorded start. Client clocks cannot extend it. A valid paid license activates the purchased edition/features.
- The owner earns through product license sales and support, not in-app profit sharing.
- Remove participation/partnership contract workflows from customer navigation and normal product flows; do not destructively delete historical records or migrations.
- Do not represent a bank transfer as complete without authoritative provider confirmation or a separately auditable manual reconciliation.
- Preserve the existing persistent database and data. Apply additive, backup-aware migrations only.
- All enabled navigation items, shortcuts, modules, engines, reports, and cross-module links must point to a real route/action; mark unsupported integrations as unconfigured rather than falsely active.
- Never claim production readiness until CI, deployment health, tenant-isolation tests, and a browser smoke test pass.

---

### Task 1: Tenant identity, isolation, and migration

**Files:**
- Modify: `app/main.py`
- Modify: `app/participation.py`
- Modify: `app/distribution_erp.py`
- Modify: `app/ai_command_center.py`
- Modify: `app/pricing_modules.py`
- Create: `tests/test_tenant_isolation.py`
- Modify: relevant existing tests under `tests/`

**Interfaces:**
- Add a tenant context resolver based on the authenticated session, not a client-supplied tenant ID alone.
- Add additive tables for tenants, tenant memberships/roles, and migration metadata.
- Every tenant-owned read/write operation must use the resolved tenant ID and enforce membership/role checks.

- [ ] Add failing tests for two companies, users belonging to only one company, forged tenant IDs, and attempts to access another company's reports, users, and settings.
- [ ] Run `python -m pytest -q tests/test_tenant_isolation.py`; expect failures until tenant scoping exists.
- [ ] Implement additive schema migration and central tenant-scoped authorization helpers. Existing owner-level platform settings remain separate from tenant data. Backfill legacy data only when ownership can be determined safely; quarantine ambiguous rows for explicit assignment rather than sharing them across tenants.
- [ ] Re-run focused tests; assert cross-tenant requests return 403 or a non-disclosing 404 and never leak data.
- [ ] Run `python -m pytest -q` and browser smoke tests.
- [ ] Commit the independently passing deliverable.

### Task 2: Product-owner console, licenses, 90-day trial, and activation

**Files:**
- Modify: `app/main.py`
- Modify: `app/pricing_modules.py`
- Modify: `app/static/owner-pricing.html`
- Modify: `app/static/plans.html`
- Create: proposed `tests/test_licensing.py`

**Interfaces:**
- License states: `trial`, `active`, `expired`, `suspended`; store server-side trial start/end, purchase/activation timestamp, edition, enabled modules, and tenant binding.
- A one-time activation key is generated server-side, shown only when issued, stored hashed, bound to a tenant, and redeemed through an authenticated activation endpoint.
- Owner console manages license issue/revoke/renewal and support entitlements; tenant admin sees only its own license status and activation UI.

- [ ] Add failing tests for trial expiration at 90 days, clock tampering, invalid/reused keys, wrong-tenant key redemption, suspended licenses, and paid activation.
- [ ] Run `python -m pytest -q tests/test_licensing.py`; confirm the missing behavior is caught.
- [ ] Implement license state transitions using server time and a testable clock; never let a browser date extend a trial. License expiry blocks protected product operations but preserves export/access to data needed for lawful retrieval and support.
- [ ] Add onboarding flow: create company/admin, start trial, display expiry date, enter purchased activation key, show enabled edition/features.
- [ ] Verify tests for trial, paid activation, expiry, renewal, and revoked keys.
- [ ] Run full tests and commit.

### Task 3: Company-owned bank accounts and payment-provider adapters

**Files:**
- Modify: `app/participation.py`
- Modify: `app/main.py`
- Modify: `app/static/finance.html`
- Create: proposed `app/payment_providers.py`
- Create: proposed `tests/test_company_banking.py`
- Create: proposed `tests/test_payment_webhooks.py`

**Interfaces:**
- Tenant-scoped bank-account CRUD supports multiple accounts per company and fields limited to business metadata (label, institution, account/IBAN display, currency, status); sensitive account identifiers must be masked in ordinary views.
- Provider adapter interface separates `create_payment`, `verify_webhook`, and `fetch_payment_status`; the no-provider state is explicit and cannot claim real payment processing.
- Provider credentials are tenant-scoped, encrypted at rest with a deployment-managed encryption key, write-only after save, and redacted from logs/responses.
- A payment becomes `confirmed` only after authenticated provider confirmation or an explicitly authorized, auditable manual reconciliation. Idempotency keys prevent duplicate webhook processing.

- [ ] Add failing tests for multiple accounts, tenant isolation, secret redaction, invalid signatures, duplicate webhook delivery, pending/failed/confirmed transitions, and manual receipt versus real transfer semantics.
- [ ] Run focused tests and confirm they fail before implementation.
- [ ] Implement company finance settings, multiple bank accounts, provider configuration status, a provider adapter contract, signed/idempotent webhook processing, and a manual reconciliation path that clearly does not initiate a transfer.
- [ ] Do not invent a bank integration or simulate successful transfers. Enable real provider adapters only after the company chooses a supported provider and configures valid merchant credentials.
- [ ] Verify focused tests and full regression tests; commit.

### Task 4: Remove participation contracts, wire modules/reports, and verify release

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/finance.html`
- Modify: `app/static/agents.html`
- Modify: `app/static/distribution.html`
- Modify: other static module pages only where the audit proves a broken link or placeholder
- Modify: relevant files in `tests/`
- Create: proposed `tests/test_module_routes.py`
- Create: proposed `docs/SAAS_TENANT_OPERATIONS_FA.md`

**Interfaces:**
- Customer navigation excludes partnership/participation-contract creation and profit-sharing actions. Legacy APIs/data are retained until a reviewed migration and retention policy exists.
- Every visible module/shortcut has a valid route and a working action; unavailable integrations show a clear disabled/unconfigured state.
- Reports are tenant-scoped and derived from persisted records; report filters and export endpoints enforce the same access checks.

- [ ] Add failing route/flow tests for removed participation navigation, every visible module route, report tenant scoping, and JavaScript runtime errors on finance and main pages.
- [ ] Run focused tests and record failures.
- [ ] Remove customer-facing participation-contract flows; audit each navigation item and wire real routes/actions or explicitly mark integrations unconfigured. Do not label a module “active” when it is only a placeholder.
- [ ] Add onboarding, licensing, bank-configuration, support, backup/restore, and troubleshooting documentation in Persian.
- [ ] Run `python -m compileall -q app`, `python -m pytest -q`, Node syntax checks used by CI, production Docker build, and Playwright smoke tests for mobile/desktop routes.
- [ ] Deploy only after green CI; verify the Railway deployment is successful, `/` and `/finance` return expected responses, and authenticated tenant flows work without a blank screen. Keep the previous deployment and database backup available for rollback.

## Unresolved external decisions

- Which payment providers and countries must be supported first. The architecture can accept multiple adapters, but real processing requires a provider that supports the company's legal entity/country and valid merchant credentials.
- Whether paid licenses are perpetual or subscription-based, and the pricing/renewal/refund policy. The license model supports both, but the owner must set the commercial terms before enabling checkout.
- Which legacy records belong to which company when historical data has no reliable tenant owner. Such rows must be explicitly assigned; guessing would risk cross-company disclosure.
