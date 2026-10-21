# LEADORA Dispatch Manifest and Settlement Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an auditable, tenant-isolated dispatch manifest and distributor settlement workflow on top of LEADORA's existing sales, stock, treasury, and double-entry ledger, without replacing existing records.

**Architecture:** Extend the existing `app/distribution_erp.py` router and its SQLite schema additively. Use existing `dist_sales`, `dist_sale_lines`, `dist_deliveries`, `dist_customer_receipts`, `dist_cash_moves`, `dist_journals`, and tenant-scoped audit conventions where appropriate; introduce new manifest records only where existing tables cannot represent dispatch handoff and distributor settlement. Keep external bank transfer execution out of scope.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, pytest, FastAPI TestClient, existing GitHub Actions CI.

## Global Constraints

- Preserve the existing LEADORA app structure, production database, and tenant data. Use additive `CREATE TABLE IF NOT EXISTS` migrations only; never reset or replace the persistent database.
- Every query and mutation must be scoped to the authenticated `tenant_id`; an ID from another tenant must behave as not found.
- Reuse existing sales and accounting records. Do not create a second invoice or duplicate revenue journal when creating a manifest or settling a distributor.
- Money must use the existing integer-minor-unit/Decimal helpers (`minor`, `money`), never binary float for currency arithmetic.
- Every irreversible state transition must be auditable, tenant-scoped, and safe against duplicate submission.
- No real bank transfer, payment execution, or live bank synchronization is part of this milestone.
- Do not merge or deploy automatically. Work on a feature branch, run focused tests and the repository CI suite, and report the exact verified state.

---

## Task 1: Add dispatch manifests for posted invoices

**Files:**
- Modify: `app/distribution_erp.py` — additive schema, Pydantic request models, and dispatch endpoints
- Modify: `tests/test_distribution_erp.py` — isolated temporary-DB API tests

**Interfaces:**
- Add `POST /api/distribution/dispatch/manifests` consuming a request with `manifest_no`, `dispatch_date`, `distributor_name`, and invoice allocations. Each allocation contains `order_id`, `cash_amount`, `check_amount`, and `credit_amount`.
- Add `GET /api/distribution/dispatch/manifests` returning the current tenant's manifests and totals.
- Add `GET /api/distribution/dispatch/manifests/{manifest_id}` returning header, invoice allocations, and summary totals.
- New schema should store manifest header and invoice allocations with unique `(tenant_id, manifest_no)` and unique invoice allocation per manifest. An invoice may be allocated to at most one active manifest in this milestone.
- For each invoice allocation, the sum of cash, check, and credit allocation must equal the posted invoice's outstanding amount at handoff. All allocations must be nonnegative, and invoice/order must belong to the same tenant and be in `POSTED` or `DELIVERED` status.
- Manifest creation must not change stock, post revenue again, or create a new invoice. Reject duplicate manifest number, repeated invoice IDs in one request, already assigned invoices, cancelled/draft invoices, and amounts that do not reconcile.

- [ ] **Step 1: Add failing focused tests**

Add tests for:
1. A manifest with two posted invoices is created and returns correct invoice count, total, and cash/check/credit totals.
2. A duplicate manifest number returns HTTP 409 and does not add another manifest.
3. A draft invoice, cross-tenant invoice, repeated invoice ID, already-assigned invoice, negative allocation, or allocation total mismatch is rejected with a stable 4xx response.
4. Creating a manifest leaves stock, existing sales count, existing revenue journals, and invoice totals unchanged.
5. List/detail endpoints expose only the requesting tenant's manifests.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m pytest -q tests/test_distribution_erp.py -k manifest`

Expected: new tests fail because the manifest API/schema is not yet implemented; existing tests remain unchanged.

- [ ] **Step 3: Implement the minimum behavior**

Add `dist_dispatch_manifests` and `dist_dispatch_manifest_lines` using `CREATE TABLE IF NOT EXISTS`. Add Pydantic models with explicit nonnegative Decimal allocation fields. Implement create/list/detail endpoints with tenant-scoped SQL and a single SQLite transaction for validation plus inserts. Calculate invoice outstanding from existing posted invoice total and receipts; reject an allocation if it no longer matches the outstanding balance at creation. Add an audit event on successful creation only.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m pytest -q tests/test_distribution_erp.py -k manifest`

Expected: all manifest-focused tests pass, including tenant isolation and no duplicate journal/stock mutation.

- [ ] **Step 5: Run affected integration checks**

Run: `python -m pytest -q tests/test_distribution_erp.py tests/test_licensing_banking.py`

Expected: all existing distribution and tenant/banking regression tests pass.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add app/distribution_erp.py tests/test_distribution_erp.py
git commit -m "feat: add tenant-scoped dispatch manifests"
```

---

## Task 2: Record distributor settlement against manifest allocations

**Files:**
- Modify: `app/distribution_erp.py` — settlement schema, request model, and endpoints
- Modify: `tests/test_distribution_erp.py` — settlement scenarios

**Interfaces:**
- Add `POST /api/distribution/dispatch/manifests/{manifest_id}/settlements` accepting settlement date and invoice-level actuals: cash received, checks received, credit remaining, and an optional reference/note.
- Add `GET /api/distribution/dispatch/manifests/{manifest_id}/settlements` returning settlement history and outstanding differences.
- Settlement records are append-only; corrections are separate records, not silent edits.
- Customer collection and distributor remittance are separate accounting events. On customer collection, cash collected by the distributor debits a dedicated `cash-in-distributor` clearing asset (recommended account code `1010`) and credits accounts receivable; checks debit a separate pending-check asset (recommended `1020`) and credit accounts receivable; uncollected credit remains in accounts receivable. Neither cash held by the distributor nor a pending check may be reported as cleared company bank/cash. Add `POST /api/distribution/dispatch/manifests/{manifest_id}/remittances` to record cash actually handed to the company: it must reference a tenant-owned `dist_cash_accounts` code, debit company cash/bank, and credit cash-in-distributor. Transfer of physical checks into company custody records custody/status only; it does not mark them cleared or increase cash/bank. Never trigger a real bank transfer.
- The sum of cash received, check received, and credit remaining must reconcile to the allocated invoice amount, adjusted only by a separately approved return/credit-note flow. Since returns are outside this milestone, do not accept an unapproved return offset.
- Repeated submission with the same idempotency key must return the original result; a conflicting reuse of the key must return HTTP 409.

- [ ] **Step 1: Add failing focused tests**

Test:
1. Exact cash settlement creates one receipt/treasury movement and one balanced settlement journal, and reduces the outstanding settlement amount.
2. Check settlement is visible as pending and does not increase cash/bank balance.
3. Remaining customer credit is preserved as outstanding; it is not marked collected.
4. Settlement total mismatch, unknown cash account, cross-tenant manifest, and invalid date are rejected without partial writes.
5. A repeated idempotency key creates no duplicate receipt, cash movement, or journal; conflicting payload reuse returns 409.
6. A second settlement cannot exceed the remaining unsettled allocation.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m pytest -q tests/test_distribution_erp.py -k settlement`

Expected: new settlement tests fail before implementation.

- [ ] **Step 3: Implement the minimum behavior**

Add append-only collection, check-instrument, and remittance tables with tenant-scoped foreign references, idempotency key uniqueness, and audit events. Ensure tenant ledger accounts `1010` (cash held by distributor) and `1020` (pending checks) are created safely and are not mislabeled as company bank/cash. Use one SQLite transaction for each collection/remittance and its accounting effects. Reuse the existing `post` helper only after confirming source type/source ID uniqueness behavior; otherwise add a unique source identity before posting. Pending checks must have a dedicated status and never be included in cleared cash totals. Preserve existing customer-receipt semantics rather than writing to them twice.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m pytest -q tests/test_distribution_erp.py -k settlement`

Expected: all settlement tests pass and failed transactions leave no partial settlement, cash movement, or journal.

- [ ] **Step 5: Run affected integration checks**

Run: `python -m pytest -q tests/test_distribution_erp.py tests/test_finance.py`

Expected: distribution and existing finance-contract tests pass without changing current finance behavior.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add app/distribution_erp.py tests/test_distribution_erp.py
git commit -m "feat: record auditable distributor settlements"
```

---

## Task 3: Verify end-to-end invariants and document API behavior

**Files:**
- Modify: `tests/test_distribution_erp.py` — end-to-end integration scenario
- Modify: `README.md` or the existing Persian operations guide, choosing the established documentation location after checking the repository — endpoint scope and limitations

**Interfaces:**
- End-to-end scenario uses existing `POST /api/distribution/sales`, `POST /api/distribution/sales/{id}/post`, the new manifest endpoints, and the new settlement endpoint.
- Existing `GET /api/distribution/reports/trial-balance`, `GET /api/distribution/treasury/accounts`, and `GET /api/distribution/reports/receivables` remain compatible.

- [ ] **Step 1: Add failing end-to-end assertions**

Create a sale, post it, create a manifest, settle a cash/check/credit split, then assert: one sale invoice, one manifest allocation, correct pending check and remaining credit, correct cleared cash, balanced trial balance, no duplicated revenue journal, and no cross-tenant visibility.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m pytest -q tests/test_distribution_erp.py -k dispatch_flow`

Expected: the scenario fails until all new workflow endpoints and invariants work together.

- [ ] **Step 3: Implement only necessary integration corrections**

Correct transaction boundaries, source IDs, tenant filters, and aggregate calculations exposed by the test. Do not add automatic bank transfer, live bank integration, unapproved returns, payroll, marketing automation, or broad unrelated refactors in this milestone.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m pytest -q tests/test_distribution_erp.py -k dispatch_flow`

Expected: the full workflow passes with balanced accounting and no duplicated stock/revenue/collection effects; distributor-held cash is separate from company cash/bank, and pending checks remain uncleared.

- [ ] **Step 5: Run repository verification**

Run: `python -m compileall -q app && python -m pytest -q`

Expected: compile succeeds and the full test suite passes. GitHub Actions additionally runs browser JavaScript checks, manifest validation, Docker Compose validation, and Docker image build.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add tests/test_distribution_erp.py README.md
git commit -m "test: verify dispatch settlement workflow"
```

## Explicitly deferred to separate plans

- Sales/warehouse return authorization, inspection, credit notes, and stock re-entry.
- Full double-entry account configuration and fiscal reporting audit beyond existing capabilities.
- HR/payroll and commission rules.
- AI marketing channel integrations and external messaging.
- Frontend screens for manifests and distributor settlement.
- Live bank feeds, payment rails, and real money transfers.

## Unresolved externally observable decisions

1. **Currency rounding:** the existing ERP stores amounts in hundredths. This plan retains that behavior; confirm whether every tenant currency should use two fractional digits or whether currency-specific precision is required before multi-currency support.
2. **Distributor identity:** this first milestone uses a tenant-owned distributor display name because the current schema does not expose a verified distributor/employee directory interface. Before payroll/commission integration, replace or map it to a dedicated tenant-scoped distributor ID.
3. **Check handling:** checks are pending instruments and do not count as cleared cash. Endorsement, deposit, bounce, and clearance lifecycle are a separate follow-on plan. Cash collected by the distributor and cash remitted to the company are separate accounting events.
4. **Return handling:** returns cannot be netted against a manifest settlement until the separate approved return/credit-note workflow exists.
