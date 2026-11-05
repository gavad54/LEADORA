# VAYRO ↔ LEADORA — Integration Boundary and Decision Record

**Decision date:** 2026-11-05  
**Status:** Architecture decision only; no live integration is enabled.

## Decision

Keep VAYRO and LEADORA as separate applications and independently deployable services. Do not merge the VAYRO Next.js application source, Prisma schema, authentication tables, or database into the LEADORA FastAPI/SQLite application.

This is a deliberate safety boundary, not a rejection of future integration.

## Evidence behind the decision

- VAYRO repository: `gavad54/zelmira-one-`; Next.js App Router, React, TypeScript, PostgreSQL and Prisma.
- LEADORA repository: `gavad54/LEADORA`; FastAPI/Python, SQLite and a separate Android WebView wrapper.
- The products have different release pipelines, data models, identity lifecycles and operational responsibilities.
- VAYRO PR #2 remains open and draft. VAYRO CI and CodeQL pass on commit `fbe8da07f43096d081c92ad997c107bac7eaf82f`; this does not make VAYRO production-ready.
- The connected Railway workspace currently has no VAYRO project. Do not point VAYRO configuration or secrets at the LEADORA or ARIA Web production services.
- Railway currently reports one LEADORA production service sourced from `gavad54/LEADORA` branch `main`, with a persistent 500 MB volume mounted at `/data`. The latest deployment shown by the environment inventory is `SUCCESS` from 2026-10-21; the inventory does not expose its exact source commit. No VAYRO service is present.
- LEADORA PR #46 contains public-home/auth and owner-participation retirement work. On 2026-11-04, its CI and regression/security workflows passed, but its Android workflow failed the production public-home acceptance gate. The APK installed and launched successfully in the emulator; the gate failed because the deployed homepage lacked the expected public landing-page elements. The workflow correctly blocked release.

## Product and data boundaries

1. LEADORA remains responsible for distribution, sales operations, inventory and its own customer-company records.
2. VAYRO remains the platform catalogue/control-plane application and must not become the owner of LEADORA's operational records.
3. ARIANA remains the accounting/ERP product. ARIA must not receive accounting or ERP features.
4. No shared database, shared SQLite file, copied Prisma models, or cross-product direct SQL access.
5. No shared session cookies or assumption that a VAYRO login automatically authenticates to LEADORA.
6. No customer data is copied between products unless a documented user-authorized workflow requires specific fields and records consent/audit evidence.

## Permitted future integration pattern

When both products have independently verified production environments, use a versioned server-to-server API connector:

- LEADORA owns its operational data and exposes only explicitly approved resources.
- VAYRO receives only the minimum response fields needed for a requested workflow.
- Authenticate each service with a dedicated, revocable, narrowly scoped service identity; never reuse a human password or browser session.
- Derive tenant/company access from server-verified membership and authorization. A caller-supplied tenant ID is not proof of access.
- Require explicit user/company consent for data exchange and audit actor, tenant, action, target, timestamp, outcome and correlation ID.
- Use TLS, schema validation, request-size limits, rate limits, idempotency keys, timeouts, retries with bounded backoff and fail-closed behavior.
- Version API contracts and test compatibility before enabling a connector.
- Keep billing, payment, accounting and legally consequential actions within the product that owns the workflow; require human confirmation where appropriate.
- Provide disconnect, credential revocation, data export and deletion procedures.

No endpoint, credential, webhook or data synchronization is currently approved by this record. Do not implement speculative calls to undocumented LEADORA routes.

## Railway deployment boundary

Preferred target is a separately provisioned VAYRO project with its own PostgreSQL service, variables, secrets, backup policy and deployment approvals. LEADORA keeps its existing service, SQLite volume and release pipeline. If a future owner-approved Railway topology places both products in one project, each must still use separate services, service-scoped variables, isolated databases and explicit deployment gates. Never reuse LEADORA's production database or secrets for VAYRO.

## Release evidence required before integration

- [ ] VAYRO has an independently provisioned staging and production environment.
- [ ] VAYRO backup is stored outside its hosting provider and an isolated restore drill passes.
- [ ] LEADORA public-home production acceptance passes on the exact deployed commit.
- [ ] LEADORA Android artifact is verified against the approved commit and its public-home gate passes.
- [ ] Both products pass tenant-isolation and security tests.
- [ ] API contract, data mapping, consent, retention and failure behavior are reviewed.
- [ ] A sandbox connector passes positive, negative, cross-tenant and replay/idempotency tests.
- [ ] Product owner approves the exact data fields and workflows to exchange.

## Current status

**No source merge and no live data integration performed.** This document records the safe architecture decision and the evidence required to proceed. It does not claim either product is fully released.
