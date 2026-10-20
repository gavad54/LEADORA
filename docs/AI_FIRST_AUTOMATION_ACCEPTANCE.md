# LEADORA AI-First Automation: Acceptance Contract

## Product objective
LEADORA is intended to redesign and execute business operations with AI agents and deterministic automation, not merely digitize existing manual work. The target is maximum safe automation of repeatable work, with people handling genuine exceptions, accountable approvals, relationship-sensitive work, and physical tasks.

## Non-negotiable truthfulness
This document is an implementation contract, not evidence that the capabilities are already live. A workflow counts as automated only when the application performs the action through a verified integration or deterministic application code and records the outcome. A model response, draft, recommendation, or queued task does not count as execution.

## Automation scope
1. Lead operations: deduplicate, validate, enrich only from permitted connected sources, score, prioritize, and assign leads.
2. Sales operations: use approved catalog and price data, prepare offers, schedule consent-compliant follow-ups, and update CRM state from verified outcomes.
3. Order operations: validate customer, items, quantity, pricing, delivery details, credit policy, and explicit customer confirmation before creating a confirmed order.
4. Warehouse and distribution: use live inventory, reserve stock transactionally, generate pick lists, plan delivery, and update delivery only from connected carrier or verified proof-of-delivery events.
5. Finance operations (optional separately entitled module): match invoice/order/payment records, detect discrepancies, calculate balances from authoritative records, and route exceptions. Never infer payment receipt from a chat message.
6. Management: calculate operational KPIs from event data, detect bottlenecks, produce forecasts with confidence/limitations, and propose or execute only policy-authorized actions.
7. Administration: eliminate duplicate entry, repetitive status checks, routine report preparation, and manual handoffs where a reliable integration exists.

## Autonomy policy
- Level 0 — observe: read and summarize authorized data.
- Level 1 — prepare: create drafts or recommendations; no external side effects.
- Level 2 — execute bounded reversible actions: only with verified inputs, explicit permissions, idempotency, audit logging, and rollback/retry behavior.
- Level 3 — execute consequential actions: disabled by default; requires a specifically approved policy and integration. Human approval remains required for external commitments, out-of-policy discounts, credit decisions, confirmed customer orders where confirmation is absent, dispatch commitments, refunds, payment posting, and sensitive data exports.
- Escalate on missing/conflicting/stale data, low confidence, policy violations, repeated failures, customer disputes, or any unsupported external action.
- Never state that a message was sent, an order confirmed, stock reserved, goods dispatched/delivered, or payment settled unless the relevant system confirms it.

## Workflow requirements
- Event-driven, end-to-end workflow from lead to qualified lead, customer communication, offer, customer-confirmed order, picking, dispatch, delivery, invoice matching, and settlement.
- Each stage has explicit entry/exit criteria, owner/agent, timeout/SLA, retry policy, exception route, and audit event.
- Connectors must be real and health-checked; a missing connector must produce an honest blocked state, not a simulated success.
- Use idempotency keys and transaction-safe inventory/order updates to prevent duplicates.
- Enforce tenant isolation, role-based permissions, consent, data minimization, and secret handling server-side.
- Keep an operator override and a recoverable failure queue.

## Required measurement
Capture a baseline before deployment and calculate results from actual event timestamps and task records. Dashboard metrics:
- automation rate = eligible tasks completed end-to-end without human execution / all eligible completed tasks;
- human touch rate = workflows requiring manual intervention / all workflows;
- active human minutes per order and per qualified lead;
- elapsed cycle time by stage;
- exception and retry rates;
- data quality and confirmed-action error rates;
- operating cost per completed order, including model/API and integration costs;
- saved hours = baseline human minutes for comparable work minus observed human minutes, normalized by volume and complexity.
Do not label task automation rate as workforce/headcount reduction. Headcount impact is a separate organizational outcome and cannot be inferred from a pilot alone.

## Initial acceptance gates
- Every workflow action has a traceable audit record and current status.
- Tenant-isolation tests pass for every new endpoint.
- Duplicate requests do not create duplicate orders, tasks, or external side effects.
- No unverified inventory, pricing, delivery, or payment state is represented as fact.
- Human approval gates cannot be bypassed by the model or client.
- Integration outage and timeout tests produce safe retries or explicit blocked/exception states.
- Tests cover missing data, stale data, invalid permissions, model outage, and downstream API failure.
- A release is accepted only after automated tests and a live smoke test pass.

## Rollout sequence
1. Map current tasks and record baseline time, volume, error rate, and costs.
2. Automate low-risk internal tasks and instrumentation first.
3. Connect authoritative catalog, CRM, inventory, order, carrier, and payment systems one by one; test each connector independently.
4. Run in shadow mode, compare agent actions with verified outcomes, then enable bounded execution by policy.
5. Expand autonomy only when measured quality, reliability, cost, and exception handling meet pre-agreed thresholds.
6. Publish a before/after report. Do not claim a percentage of workforce reduction without measured human-hours data.

## Release status
This contract defines acceptance criteria. It does not claim that all integrations, AI credentials, autonomous workflows, or the target automation rate are currently enabled in production.
