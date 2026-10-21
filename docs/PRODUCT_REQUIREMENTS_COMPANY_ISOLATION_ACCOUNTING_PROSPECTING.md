# LEADORA Product Requirements: Company Isolation, Licensing, Accounting, and Smart Prospecting

Status: requirements baseline; this document does not claim that every requirement is implemented or deployed.

## 1. Product and commercial model

LEADORA is a multi-company business application sold to each customer company under its own license. Revenue for the product owner comes from:
- Initial or recurring application license/subscription fees charged to each company.
- Annual support and maintenance contracts, with scope, renewal date, status, and payment history tracked separately from the license.

The commercial module should track customer company, plan, license start/end, enabled modules, user/seat limits, invoice/payment status, annual support term, renewal reminders, and audit history. Expiration must follow a configurable policy (grace period, read-only access, and renewal flow) and must never silently delete company data.

## 2. Strict company isolation (tenant boundary)

Each subscribing company must have an independent workspace. All business records must be tenant-scoped, including users/roles, customers, suppliers, products, inventory, warehouses, sales, purchases, accounting, payroll, reports, prospecting sources, discovered leads, integrations, and audit logs.

Requirements:
- Every tenant-owned record must carry a trusted tenant identifier derived from the authenticated session, not from an untrusted request field.
- Every read, write, search, export, background job, and report must enforce tenant scope server-side.
- Role-based access: company owner/admin, accountant, sales, warehouse, HR, and read-only/auditor roles; permissions are least-privilege and configurable.
- Cross-tenant access tests must cover list, detail, update, delete, imports/exports, reporting, search, and indirect object references.
- A platform-owner console may manage licenses, support contracts, platform health, and billing metadata. It must not expose company business data by default; any support access to customer data requires explicit authorization, limited scope, and an audit trail.
- Company data retention, export, backup, and deletion must be explicit and auditable. Expired licenses do not automatically erase data.
- Never run destructive migrations or replace production data without a verified backup and a rollback plan.

## 3. Accounting: Sepidar-class workflow and parity target

The requirement is functional parity with the relevant Sepidar accounting workflows, integrated in LEADORA—not a claim that parity already exists. Build a documented feature-by-feature gap matrix against legally obtained product documentation and customer requirements before declaring completion. Do not copy proprietary source code or protected assets.

Accounting scope to assess and implement:
- Chart of accounts, accounting periods, opening balances, journals and balanced double-entry posting.
- Sales, purchase, returns, receipts, payments, expenses, cash/bank, receivables/payables, cheque lifecycle, tax/VAT, discounts, and settlement workflows.
- Inventory accounting integration: receipts, issues, transfers, physical dispatch, cost of goods sold, returns, and reconciliation.
- Fixed assets and depreciation; payroll/commissions integration where required.
- Persian calendar/date handling where required, configurable fiscal year, numbering, approval, closing/reopening controls, and immutable audit trail.
- Standard financial reports: journal, ledger, trial balance, profit and loss, balance sheet, cash/bank, receivables/payables aging, inventory valuation, and tax reports, with drill-down to source documents.
- CSV/Excel import with schema validation, duplicate protection, preview, error report, and rollback.
- Access controls and separation of duties for entry, approval, posting, and period close.
- Tenant-isolation tests, arithmetic invariants, reconciliation tests, migration tests, and end-to-end workflows.
- Integrations must be idempotent, auditable, and fail safely. No real tax/legal compliance claim until validated for the target jurisdiction by a qualified accountant.

## 4. Smart prospecting: two complementary modes

### Mode A — Automated discovery from user-provided sources
A company user may submit public website, online shop, app listing, public directory, catalog, or business text. LEADORA extracts business profile and target keywords, discovers potential customers/suppliers, deduplicates candidates, scores relevance, and presents evidence/source URL and confidence for human review. Approved candidates can be added to that company's CRM/pipeline.

### Mode B — User-authorized integrations
Provide an integration directory where an authorized company administrator can connect supported websites/apps/services through official APIs, OAuth, webhooks, or documented import methods. Show requested permissions, data fields, connection status, last sync, sync scope, and a disconnect/revoke control. Support scheduled sync only where the provider allows it.

Safety, privacy, and quality controls:
- Use only public information or data the company has authorized LEADORA to access.
- Do not bypass login, CAPTCHAs, access controls, paywalls, or platform restrictions; do not collect private messages or private account data without explicit, valid authorization and a permitted integration.
- Never ask users to paste passwords or session cookies into LEADORA. Use OAuth/API credentials stored securely, with least-privilege scopes and rotation/revocation support.
- Respect applicable terms, robots policies where relevant, privacy laws, and opt-out/do-not-contact requirements.
- Rate limits, SSRF/private-network defenses, redirect validation, payload limits, tenant isolation, provenance, deduplication, and audit logs are mandatory.
- Discovery must not send messages, make purchases, or contact leads automatically by default. Require human approval and a compliant outreach workflow.
- Clearly label inferred data and confidence; provide correction and deletion controls.

## 5. Release gates

Do not call the product commercially ready until:
1. Tenant-isolation tests pass for all modules and APIs.
2. Accounting parity matrix is reviewed and all agreed critical workflows pass acceptance tests.
3. License and annual-support lifecycle is tested end-to-end.
4. Prospecting mode A works without external search keys in its supported limited mode, and external search/integrations clearly report missing credentials or permissions.
5. Backups, restore drill, audit logs, secrets management, rate limits, and incident handling are verified.
6. Production deployment is confirmed to run the intended commit, with health checks and smoke tests after deployment.
7. A documented customer acceptance test is completed; a successful build alone is not sufficient.

## 6. Implementation sequence

1. Audit existing code and produce a module-by-module tenant-isolation matrix; fix any gaps first.
2. Implement license, subscription, annual support, renewals, and platform-owner billing/reporting.
3. Produce the Sepidar functional gap matrix; prioritize core accounting, posting, reports, fiscal periods, tax, and inventory integration.
4. Expand prospecting integrations using official/authorized connection flows and a provider capability matrix.
5. Add end-to-end tests, migration/rollback plans, observability, and release gates.
6. Deploy only when the deployment platform allows it; preserve the existing production service and persistent data.

## 7. Current known constraints

- Production Railway service has a persistent volume mounted at /data; preserve it and its database.
- A previous deployment attempt returned: "Deploys have been paused temporarily". Do not claim the latest source is live until deployment metadata confirms the deployed commit.
- The external search credential TAVILY_API_KEY was not present at last inspection; do not invent a credential or claim live external search works without a valid configured provider.
