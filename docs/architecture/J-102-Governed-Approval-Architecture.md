# J-102 — Governed Approval Architecture

## Purpose

This document defines Jason's approval architecture as implemented through the approval foundation, Microsoft Teams channel binding, JKD-001 reauthorization, immutable evidence, replay protection, and governed recovery path.

The enduring rule is simple: **approval transport is never authority**. Microsoft Teams, Microsoft Graph, Adaptive Cards, and authenticated Microsoft identity may carry or authenticate an approval interaction, but only Jason-controlled policy and identity boundaries may decide whether that interaction is authorized and whether execution may continue.

## Authority boundaries

### Central Orchestrator
The Central Orchestrator is the only component permitted to resume or retry capability execution. Agents, connectors, providers, channels, and approval adapters may return structured results or request named capabilities, but they may not invoke one another or resume execution directly.

### Provider-neutral approval service
Approval requests and responses are provider-neutral. The service validates request state, expiration, organization/client/capability scope, explicitly permitted approvers, and Jason-owned approver authority. A channel receipt or user interaction is evidence only until this service accepts it.

### Microsoft identity boundary
A Microsoft token is cryptographically verified against approved Microsoft OpenID/JWKS endpoints and exact tenant/audience/issuer/lifetime requirements. Successful verification creates only a verified Microsoft principal. It does not create a Jason identity or approver authority.

The verified Microsoft tenant and object identity must then bind to the expected Jason organization and Jason identity. User-editable Teams payload fields are never authentication evidence.

### JKD-001
An accepted approval is persisted as formal JKD-001 approval evidence and the original requester is re-evaluated through JKD-001. Execution may continue only when JKD-001 issues a fresh short-lived authority context for the exact organization, client, capability, mode, and principal scope.

**Approval accepted does not equal execution authority.**

## Dual binding for approved provider mutations

Approval-governed provider mutations require two distinct content bindings with different purposes.

### Intent fingerprint

The intent fingerprint binds the canonical semantic Jason action approved by governance: the authenticated principal, organization/client scope, canonical capability, and canonical arguments. It answers **what Jason action was approved** before provider-specific transformation.

Approval reuse with changed canonical arguments must fail before provider invocation. Approval binding, one-time approval consumption, and successful-retry idempotency remain separate controls.

### Execution-plan fingerprint

The execution-plan fingerprint binds **what concrete mutation is authorized to reach the selected provider** after provider selection, symbolic resolution, normalization, provider defaulting, and target resolution are complete. Where applicable it includes:

- principal ID;
- organization ID and client ID;
- canonical capability;
- selected provider ID;
- provider capability/operation;
- HTTP/action method;
- resource type and durable resource identifier/target;
- normalized provider-relative path;
- normalized final provider payload;
- material query/operation parameters; and
- symbolic-resolution evidence preserving both the human-readable symbolic value and resolved provider value.

The execution-plan binding deliberately excludes secret values, authentication/authorization headers, correlation IDs, dynamically discovered provider hostnames, and transport-only volatile data unless governance deliberately declares a specific value part of the authority boundary. Provider adapters may hold such transport state ephemerally, but it may not become persisted/audited plan fingerprint material.

Execution-plan material is a strict deterministic JSON authority object, not an arbitrary serialization surface. Mapping keys must be strings; values must be JSON primitives/objects/arrays with finite numeric values. Unsupported runtime objects are rejected rather than converted to strings. Provider adapters should expose only explicitly material authority fields. Credential, cookie, authorization, API-key, bearer-token, private-key, session, and equivalent transport-secret material must remain only in ephemeral provider-private prepared state and must never be copied into persisted plan/audit fields.

### Prepare, bind, independently re-prepare, verify

For an approval-governed mutation, the Central Orchestrator owns the final decision immediately before provider invocation:

1. validate the approved canonical intent;
2. resolve the governed provider;
3. have the provider adapter prepare a side-effect-free concrete execution plan, including required symbolic/provider metadata resolution;
4. bind and consume the approval against both the intent fingerprint and execution-plan fingerprint;
5. independently re-prepare/re-resolve the concrete execution plan immediately before provider invocation;
6. require the independently prepared plan to match the authorized execution-plan fingerprint exactly for all material authority fields; and
7. invoke only the verified prepared plan.

A changed provider, provider operation, target, symbolic mapping, material parameter, normalized path, or normalized payload must fail closed with zero provider writes. Re-resolution is permitted only when the resolved concrete plan is unchanged; changed provider metadata must never be silently accepted as equivalent authority.

A provider-specific adapter may supply normalized plan material, but it may not bypass the Central Orchestrator's final plan verification. An approval-governed mutation adapter that does not implement the required execution-plan contract must remain blocked/fail-closed rather than falling back to an unbound legacy invocation path.

### Provider mutation authority versus diagnostic resource flexibility

Provider selection for a mutation is part of the execution-plan authority boundary. This does not imply that an approved playbook must use one fixed device or evidence source for every diagnostic step. Read-only discovery and diagnostic resource flexibility inside an already-authorized client scope are separate from authorization to perform a concrete provider mutation.

A playbook may therefore inspect different permitted devices/evidence sources as its diagnostic rules allow while still requiring any resulting provider mutation to bind the selected provider, exact target, operation, and material payload.

## Approval lifecycle

1. The Central Orchestrator encounters a policy condition requiring approval.
2. A provider-neutral approval request is created with organization, request, correlation, client, capability, requester, expiration, approver policy, and immutable evidence references.
3. Request creation is recorded in the immutable approval audit chain before external delivery.
4. An organization-scoped channel target is resolved. Missing, disabled, cross-tenant, or ambiguous targets fail closed.
5. A channel adapter renders only the minimum non-secret metadata required for the approval interaction.
6. Microsoft Graph transports the message. Graph and Teams remain transport only.
7. On response, the Microsoft token is cryptographically verified and then bound to the Jason tenant and identity.
8. The provider-neutral approval service validates response status, expiry, authorized approver identity, scope, and Jason-owned approver authority.
9. Accepted approvals are persisted as immutable JKD-001 approval records. Exact duplicate persistence is idempotent; conflicting approval-ID reuse is rejected.
10. JKD-001 independently re-evaluates the original requester and issues a fresh authority context when allowed.
11. The approval continuation boundary verifies approval evidence and fresh authority, atomically consumes the continuation, and invokes only the Central Orchestrator.
12. The resulting orchestration state is appended to the approval audit chain.

Denied, expired, unauthorized, malformed, unbound, or cross-organization responses never resume execution.

## Replay and exactly-once safety

Approval evidence is append-once, but immutable approval records alone do not prevent an already-approved operation from being invoked twice. Jason therefore requires a separate durable one-time consumption boundary in addition to approval evidence.

Continuation-based approval flows use the durable continuation-consumption guard. The generic approval-governed execution path uses the governed-execution ledger to bind the approval ID, intent fingerprint, idempotency key, consumption state, execution/correlation identity, and completed result. Exact successful retries are deduplicated from that durable result rather than invoking the provider again.

Consumption is committed **before** provider invocation is permitted. An approval ID may therefore authorize one concrete execution path only. Consumption state survives process restart and remains scoped to the approved principal/organization/client/capability/arguments.

Execution-plan binding is an additional control, not a replacement for replay protection: it proves that the one permitted execution is still the same concrete provider mutation immediately before invocation.

If the process fails after consumption but before the provider outcome becomes known, Jason does not automatically release the approval and does not automatically repeat the operation. This is deliberate. A duplicate side effect is considered more dangerous than requiring explicit recovery.

**Consumed approval does not equal safe to retry. Exact successful retry deduplication does not authorize changed intent or a changed execution plan.**

## Governed recovery

An indeterminate continuation requires a new recovery decision. Recovery records are immutable and may record one of the following dispositions:

- `confirmed_completed`
- `confirmed_not_executed`
- `abandoned`
- `retry_authorized`

Every recovery decision is bound to organization, approval, request, correlation, capability, decision maker, reason, timestamp, and optional immutable evidence references.

A `retry_authorized` decision additionally requires a **fresh JKD-001 authority context**. That recovery authorization is itself consumed atomically before retry execution and may be used only once.

If a governed retry also becomes indeterminate, Jason fails closed again. A new explicit recovery decision and new authority are required.

## Audit and evidence

Approval lifecycle events are append-only and hash chained per approval. Significant events include request creation, delivery, authenticated response, accepted or denied decision, expiration, authorization rejection, JKD-001 reauthorization, orchestrator continuation, and processing failure.

Large evidence belongs in INF-013 artifact/evidence storage and is passed by immutable reference. Audit records carry references and integrity metadata rather than duplicating provider payloads or sensitive artifacts.

Audit is evidence only. Audit records never grant approval or execution authority.

## Microsoft Teams binding

Microsoft Teams is an optional communications channel behind the provider-neutral approval contracts. The Teams implementation currently relies on:

- organization-scoped Teams delivery targets;
- Microsoft Graph v1.0 message transport;
- client-credential token acquisition through the governed secret-provider boundary;
- canonical Microsoft OpenID/JWKS retrieval and token verification;
- Microsoft tenant/object-to-Jason organization/identity bindings.

The Teams binding may be replaced by another channel without changing Jason's approval authority model.

## Fail-closed invariants

Jason must stop approval processing or execution when any mandatory identity, tenant, policy, expiration, evidence, audit, authority, replay, or recovery prerequisite cannot be proven.

No component may infer authority from channel membership, message ownership, Microsoft authentication alone, provider success, delivery receipts, Adaptive Card fields, or prior execution state.

## Operational status

The backend approval architecture and approval replay/idempotency protection are implemented. The approval-replay production acceptance on 2026-09-23 proved one provider write for one approved `service.ticket.note.create` action and deduplication of the identical replay. The durable chronological evidence is recorded in `docs/sessions/2026-09-23.md`.

The execution-plan binding described above was implemented at commit `56b0e91fe376fb270ac521c5c1754bfa12aafdb5` with a focused 49/49 security suite. Follow-on isolated remediation on `fix/security-remediation-20260923` hardens deterministic secret-safe plan serialization and explicit provider method/path/target revalidation, and adapts Autotask ticket create plus internal-note create in addition to ticket update; the focused regression set is 36/36 PASS. Autotask procurement, Datto RMM component execution, Datto RMM site-variable mutation, Datto EDR scan execution, and Datto alert resolution remain unadapted and therefore intentionally fail closed under approval-bound execution-plan enforcement. The control was **not yet deployed to production** at the 2026-09-23 rollout safety check. Production remained on the approval-replay deployment revision `5f89f3af82081e75e97d66e523222e5564648163`; the planned XYZ acceptance mutation was therefore correctly stopped before approval/provider invocation. This remains pending complete mutation-adapter compatibility, production deployment, and bounded live acceptance, not a claim of production verification.

Live Microsoft/Teams approval-channel validation also remains an independent operational task and requires the Jason host, OpenBao-backed credential binding, Microsoft application configuration, organization-specific Team/channel targets, and a controlled end-to-end test approval.
