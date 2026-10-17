# Reconciliation reporting contract (engineering draft)

This is a read-only presentation contract, **not a deployed notification service**.

Every checking-account reconciliation run produces a concise plain-English report for the account's authorized assigned reconciler. Governed read-only investigation and deterministic matching require no per-step human approvals; notifications are not permission requests.

The pure `orchestrator.finance_reconciliation_reporting` component receives explicit run facts (masked account, timezone-aware start/end, matched counts, steps, accounting-write declarations, stable exception references, and action owners), rejects inconsistent state, and formats results. It cannot access QuickBooks, issue a Teams message, or authorize accounting writes.

Explicit run states: `COMPLETED_NO_EXCEPTIONS`, `COMPLETED_WITH_EXCEPTIONS`, `PARTIAL_REVIEW_REQUIRED`, `BLOCKED_NOT_COMPLETED`. Solutrix #15904 remains partial until linked QBO BillPayment and funding account evidence are verified.

## Remaining integration and production gates

- Bind verified reconciliation facts from draft #692/#1331, and exact governed payment-read evidence from #1502, without duplicating matching logic.
- Resolve recipient identity from tenant/account assignment and existing central identity policy, not free-form caller role text. Reuse central notification service with idempotent delivery and confirmed send outcome.
- Maintain immutable per-step audit and protected evidence references; report delivery failure separately and escalate via configured fallback.
- Require explicit standing authorization or designated approval for any accounting write, bank movement, or balance adjustment; this report grants none.
- Demonstrate clean/no-prompt, self-resolved and unresolved exception, wrong-tenant, duplicate, timezone, failed delivery and real Solutrix acceptance.
- Do not deploy this component on draft PR merge or claim notifications were sent based solely on rendering.

Related: #1470, #1468.
