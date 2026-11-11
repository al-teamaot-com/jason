# PMv4 native task observer — source-only preproduction

## Change and scope
The isolated `tools/pmv4_native_task_observer.py` library calls the **existing**
OpenClaw native `tasks show <exact UUID> --json` read interface. It supplies
fresh task-ledger evidence for `native_task_terminal_evidence`, the existing
PMv4 reconciliation function. It does not add a scheduler, provider client,
second task database, approval store, Workboard updater or new runtime service.

The CLI must be selected by trusted runtime configuration using a pinned
absolute path, not a card or requester value. The caller provides a **fresh**
native Workboard card from its governed context; this library never treats
card text as authority. The caller must also independently re-read the card,
PMV3 action/approval state and current receipt before considering action.
Use the established governed executor only, never invoke a provider or
`execute_cycle` from the observer.

## Acceptance evidence
- Eight offline unit tests: terminal failure, succeeded/reconcile, active/
  lost/mismatched task, invalid UUID and command injection, CLI path rejection,
  timeout/exit error, malformed/oversize JSON and side-effect absence.
- Existing 20 Workboard reconciliation tests passed alongside the observer tests.
- An authenticated live subscription-backed Workboard interruption/recovery
  **has not** been tested by this addition; no launch, restart or provider action.
- Never interpret `TERMINATED` as permission to retry or completion.
  `succeeded` requires reconcile and independent acceptance.
  Missing or discrepant facts remain `HOLD`.

## Remaining integration dependencies
1. Confirm exact OpenClaw CLI path and permissions in an *isolated* runtime
   environment; this host shell did not expose `openclaw` on PATH.
2. Obtain a trusted fresh native Workboard card, query exact native task run,
   and independently inspect ledger provenance before using evidence.
3. Re-read protected PMV3 authority, receipts, claim and retry budget at use
   time; no blanket replay, mutable allowlist or stale authority.
4. Demonstrate a real subscription-authenticated failed-agent run safely
   recovering one idempotent read-only task using the existing governed worker;
   hold every uncertain non-idempotent action.
5. Independently verify completion, Workboard state reconciliation, ticket
   Core preservation and component-scoped rollback before any production move.

## Explicit safety boundary
No production service, gateway, configuration, scheduler, repository main,
ticket worker, freeze, root breaker, secrets or provider was changed. This
is not a production readiness claim, replacement of the existing work engine,
or authorization to bypass Teams/Owner release requirements.

## Read-only integration extension
`assess_native_stale_recovery(card, pmv3_state, authorized_readonly_actions=...)`
now queries the exact native ledger once and feeds the fresh matching record
directly into the **existing** `assess_governed_stale_recovery` pure decision
function. It returns only `HOLD`, `RECONCILE`, or a
`GOVERNED_ENGINE_CANDIDATE` advisory; it never executes a provider action.
Two additional tests cover this handoff: a synthetic authorized idempotent
candidate with immutable input states, and nonterminal/unavailable/mismatched
ledger results held without execution. The integration is still source-only.
