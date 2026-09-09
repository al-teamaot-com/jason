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

Approval evidence is append-once, but immutable approval records alone do not prevent an already-approved operation from being invoked twice. Jason therefore uses a separate durable continuation-consumption claim.

The claim is written **before** orchestration invocation. An approval ID may therefore trigger the continuation path only once. Claims survive process restart and are organization-bound.

If the process fails after the claim but before the execution outcome becomes known, Jason does not automatically release the claim and does not automatically repeat the operation. This is deliberate. A duplicate side effect is considered more dangerous than requiring explicit recovery.

**Consumed continuation does not equal safe to retry.**

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

The backend approval architecture is implemented and repository-validated. Live Microsoft/Teams deployment validation remains an operational task and requires the Jason host, OpenBao-backed credential binding, Microsoft application configuration, organization-specific Team/channel targets, and a controlled end-to-end test approval.