# LEADORA — AI-first lead-to-cash operating model

## Product boundary
LEADORA is independent of ARIANA. It orchestrates customer acquisition, CRM, sales, warehouse, distribution and settlement. Accounting is optional and must never be a prerequisite for the core customer-discovery and sales product.

## Command hierarchy
1. AI Commander: routes tasks, prioritizes work, monitors SLAs, retries safe idempotent tasks, resolves conflicts and escalates exceptions.
2. Policy and permission guard: tenant isolation, role access, customer consent, price and discount limits, credit rules, privacy, audit trail and stop conditions. It can veto any agent.
3. Specialist agents: discovery, qualification, outreach, sales chat, offer builder, order guard, credit risk, inventory/procurement, warehouse, delivery, settlement/collections, retention, analytics and privacy/compliance.
4. Human approval queue: policy exceptions, credit changes, purchases, out-of-policy discounts, refunds/financial adjustments, dispatch exceptions, complaints and exports.
5. Connector adapters: permitted web/maps/directories, imports, messaging, catalog, inventory, optional ERP/accounting, courier, payment reconciliation and LLM provider.

## End-to-end process
Lead discovery → deduplication and qualification → consent-aware contact draft → need discovery → verified catalog and price retrieval → offer draft → explicit customer confirmation → stock and credit checks → pick/pack task → dispatch integration → proof of delivery → invoice/payment reconciliation → retention and analytics.
Every transition must have preconditions, evidence, tenant ID, timestamp, idempotency and an audit event. No message, order, shipment or payment is considered real without provider or customer evidence.

## Agent contract
Each task has tenant_id, task_id, trace_id, allowed data scope, policy snapshot, deadline and retry policy. Each agent returns structured status, evidence IDs, proposed action, confidence, risk, approval requirement and next agent. Missing or stale data means ask or escalate, never invent. Agent calls must be bounded and queued, not recursive and uncontrolled.

## Chatbot
Omnichannel gateway with brand and language settings, persistent history, consent, intent routing, retrieval from approved product/pricing/FAQ data, slot filling for product/variant/quantity/address/time/settlement preference, offer preview, explicit order confirmation, order status lookup, complaint handling, human handoff and analytics. Customer-facing chatbot is separated from internal employee copilot. If no live LLM or external provider is configured, safe fallback behavior must disclose that limitation.

## Human vs AI
AI can prepare deduplicated leads, score fit, draft communications, classify replies, answer approved FAQs, create reminders with consent, check authoritative inventory, prepare pick lists, propose routes, monitor SLAs, summarize receivables and flag churn.
Humans remain responsible for physical picking/packing, exceptions, disputes, credit decisions, purchases, refunds, legal/financial approvals, customer order confirmation and any action outside approved policy. A human approval record does not itself send a message or move money.

## Security and KPIs
Tenant isolation, RBAC, secrets outside source, encrypted transport, backups and restore tests, rate limits, idempotency keys, bounded retries, dead-letter handling, webhook signature validation, output-schema validation, prompt-injection boundaries, PII minimization and configurable retention.
KPIs: source yield, qualification rate, consented contact rate, response latency, lead-to-offer and offer-to-order conversion, order accuracy, fill rate, on-time delivery, proof-of-delivery rate, days sales outstanding, collection effectiveness, repeat purchase, churn, human handoff rate, AI containment and cost per converted customer.

## Implementation status
This change provides a persistent tenant-isolated agent registry, workflow state foundation, command-center summary, customer chat history, intent-routed fallback chatbot, human approval queue and audit events. It does not claim that live LLM, messaging, maps, courier, payment or accounting connectors are connected. Full autonomy requires authorized credentials, provider adapters and end-to-end integration tests.
