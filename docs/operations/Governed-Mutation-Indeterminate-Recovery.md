# Governed Mutation Indeterminate Recovery

**Status:** Active source-level recovery procedure; production execution remains subject to current deployed capability/authority state  
**Owner:** Jason Governance Authority / AOT Operations  
**Architecture authority:** `docs/architecture/J-102-Governed-Approval-Architecture.md`

## Purpose

Use this runbook when an approval-governed provider mutation has consumed its approval or recovery authorization but Jason cannot prove whether the provider side effect occurred. Typical causes include a process interruption after provider dispatch, a transport failure after a request may have reached the provider, or post-mutation readback failure.

The governing safety rule is: **unknown outcome means no automatic retry**. A duplicate side effect is more dangerous than stopping for evidence and explicit recovery.

This runbook is provider-neutral. Provider-specific evidence may differ, but the authority, replay, execution-plan, audit, and stop rules do not.

## Trigger

Enter indeterminate recovery when all of the following are true:

1. the operation was consequential/provider-mutating;
2. its one-time approval or recovery execution authorization was consumed or provider invocation may have begun; and
3. Jason cannot prove from durable evidence whether the intended mutation completed.

Examples include:

- provider POST/PATCH/PUT was dispatched and the connection failed before a trustworthy response;
- provider returned success but required readback could not be completed;
- Jason/runtime restarted between provider invocation and durable completion recording;
- an asynchronous provider action was accepted but durable job/action identity or final state cannot be verified.

Do **not** use this process for a plan mismatch or authorization rejection that proved `provider_invoked=false`; those events require no provider-side reconciliation because the mutation was stopped before invocation.

## Immediate containment

1. Do not rerun the original request.
2. Do not delete or reset the original approval/continuation/recovery consumption claim.
3. Do not change the original governed-execution ledger row back to `reserved`.
4. Do not bypass the Central Orchestrator or invoke the provider directly.
5. Preserve the original approval ID or recovery ID, execution ID, correlation ID, intent fingerprint, execution-plan fingerprint, selected provider, target identifier, operation/path, and available audit/evidence references.
6. Use read-only provider capabilities to establish the actual provider state whenever possible.

## Read-only reconciliation evidence

Collect only the evidence necessary to determine whether the authorized mutation happened. Prefer durable provider identifiers and state over assumptions based on transport errors.

Useful evidence may include:

- Autotask durable object/note/ticket ID plus exact field readback;
- Datto RMM job UID, alert state, site-variable metadata, endpoint state, or activity history;
- Datto EDR agent scan state/history and provider task ID when available;
- Microsoft Teams provider message ID or stored conversation/message evidence;
- provider audit/activity history showing the exact target and operation;
- Jason audit entries for intent and execution-plan fingerprints, provider invocation, verification, and failure stage.

Never copy credentials, access tokens, secret site-variable values, authorization headers, private keys, or raw secret-bearing request state into recovery evidence.

## Recovery dispositions

Record exactly one immutable recovery decision for the investigation:

| Disposition | Required conclusion | Retry effect |
| --- | --- | --- |
| `confirmed_completed` | Evidence proves the authorized provider mutation completed. | No retry. Reconcile Jason/ticket state from verified provider state. |
| `confirmed_not_executed` | Evidence proves the provider mutation did not occur. | No automatic retry. A separate `retry_authorized` decision is still required before execution. |
| `abandoned` | The operator intentionally ends recovery without retry. | No retry through this recovery decision. |
| `retry_authorized` | Evidence and human authority explicitly permit one new retry. | One retry may proceed only through the guarded flow below. |

If evidence cannot distinguish completed from not executed, the operation remains indeterminate. Do not select `retry_authorized` merely because a retry would be convenient.

## Guarded retry procedure

A `retry_authorized` decision requires all of the following:

1. Record a new immutable recovery record with a unique `recovery_id`, original approval ID, organization, request ID, correlation ID, capability, decision maker, reason, and immutable evidence references.
2. Obtain a **fresh JKD-001 authority context** for the exact organization/request/capability scope.
3. Require the retry request to match the recovery record's organization, request ID, correlation ID, capability, and exact fresh authority context.
4. Atomically consume the `recovery_id` through the durable recovery retry guard **before** invoking the Central Orchestrator.
5. Route only through the Central Orchestrator. A recovery retry with externally guarded approval authority is still required to perform side-effect-free plan preparation, independently re-prepare, and require an exact execution-plan fingerprint match before provider invocation.
6. Use the same provider mutation contract as an ordinary approved action. Provider, target, operation, path, normalized payload/material parameters, and symbolic resolution must not change silently during recovery.
7. Perform at most one provider invocation for the consumed recovery authorization.
8. Complete normal post-mutation provider readback/verification.
9. Record the orchestration outcome and recovery ID in approval/audit evidence.

If the retry itself becomes indeterminate, its recovery authorization remains consumed. Start a **new** recovery investigation and, if justified, create a new recovery decision and fresh authority context. Never release or reuse the consumed recovery ID.

## Execution-plan and deadline rules

Recovery never weakens the normal mutation boundary:

- externally guarded approval/recovery continuations receive the same dual execution-plan preparation and exact re-prepare match as approval-ID-backed MCP actions;
- a changed provider, target, operation, method/path, payload, material parameter, symbolic resolution, or secret commitment fails closed before provider invocation;
- provider-private credentials and transport details remain outside persisted execution-plan material;
- the resolved provider `maximum_execution_seconds` is one shared absolute provider-action deadline across first preparation, independent re-preparation, and invocation; nested connector timeouts may tighten but may not reset or extend it.

## Provider-specific notes

### Autotask

Prefer exact durable object readback. For creates, verify the provider-assigned ID and expected identifying fields. For updates, verify every authorized changed field. For internal notes, verify note ID, content/visibility, and requester attribution where required. Do not create a second note/ticket merely because the original response was lost.

### Datto RMM component execution

Search/read activity or job history for the exact endpoint/component and correlation window. If a matching quick job exists, recover its job UID and follow the normal job/result verification path rather than launching another job.

### Datto RMM alert resolution

Read the exact alert UID and endpoint UID. `resolved=true` is evidence that another resolve POST is unnecessary; treat the state as completed/reconciled if the evidence supports the original action.

### Datto RMM site variables

Use metadata/readback without disclosing the secret value. The execution plan binds secret-bearing values by cryptographic commitment; recovery evidence must never disclose or persist the raw value.

### Datto EDR scan

Read exact agent/device scan state/history. Respect in-progress and minimum scan-interval controls during recovery; recovery is not authority to bypass rate/safety guards.

### Microsoft Teams proactive send

Use the provider message ID or other trustworthy message/conversation evidence when available. Do not resend solely because the gateway response was lost if delivery may already have occurred.

## Stop conditions

Stop and fail closed if any of the following cannot be proven:

- exact organization/client scope;
- original approval/recovery identity;
- exact request/correlation/capability scope;
- provider and target identity;
- trustworthy evidence of provider state sufficient for the selected disposition;
- fresh JKD-001 authority for a retry;
- durable one-time recovery retry consumption;
- Central Orchestrator execution-plan binding;
- audit/evidence persistence required by the action.

Stop if completing recovery would require deleting a replay claim, resetting a consumed approval, broadening credentials, changing the target, using direct provider access, or suppressing a plan mismatch.

## Completion criteria

Recovery is complete only when one of these states is durably evidenced:

- `confirmed_completed` with provider state reconciled;
- `confirmed_not_executed` with no retry requested;
- `abandoned`; or
- one `retry_authorized` execution completed through the one-time recovery guard, Central Orchestrator dual plan binding, provider invocation, and required readback.

The original indeterminate execution history remains preserved. Recovery records supplement it; they never rewrite it.

## Current implementation references

- recovery record/ledger: `implementation/orchestrator/approval_recovery.py`
- one-time recovery retry guard/executor: `implementation/orchestrator/approval_recovery_retry.py`
- ordinary approval continuation guard: `implementation/orchestrator/approval_continuation_guard.py`
- Central Orchestrator plan binding: `implementation/orchestrator/service.py`
- concrete execution-plan contract: `implementation/orchestrator/execution_plan.py`
- architecture: `docs/architecture/J-102-Governed-Approval-Architecture.md`

This runbook does not itself authorize a recovery or provider mutation.
