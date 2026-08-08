# JKD-001 — Identity and Authority Runtime Foundation

## Status

Production-hardening implementation foundation.

## Purpose

Implement the executable JKD-001 Identity and Authority Service so ingress paths such as OpenClaw receive a real, scoped, short-lived authority decision and downstream orchestration can require the issued execution context.

## Constitutional role

This service is a kernel authority boundary. Authentication alone never permits action. The service decides whether the authenticated principal may request a named capability for the exact organization/client scope and requested mode.

It does not invoke providers, capabilities, agents, or workflows.

## Implemented contracts

The runtime defines:

- canonical identity records;
- scoped authority grants;
- formal approval records;
- permission levels: observe, recommend, request_approval, execute, administer;
- authority requests;
- five-result authority decisions: allowed, allowed_limited, approval_required, denied, indeterminate;
- short-lived immutable execution contexts;
- durable SQLite-backed pilot storage for identities, grants, approvals, issued contexts, revocation state, and authority-decision audit;
- execution-context validation for exact correlation/principal/organization/client/capability/mode scope;
- explicit context revocation.

## Evaluation rules

The service fails closed when:

- the principal identity cannot be resolved;
- the identity is inactive;
- organization scope differs from the identity organization;
- no active grant matches the exact capability and client scope;
- a requested mode exceeds the available grant and cannot be safely limited;
- a required approval is absent, expired, belongs to another request, capability, organization, client, or requester.

An organization-wide grant is not silently interpreted from a missing client ID. Grant and request client scopes must match exactly, including `None` only when the explicitly modeled request is itself organization/internal scoped.

## Durable authority state

`SQLiteIdentityAuthorityStore` is the local production-pilot persistence boundary. The database is created with owner-only permissions and retains:

- canonical identities;
- authority grants;
- approval records;
- issued execution contexts;
- revocation timestamp/reason;
- sanitized authority decision audit records.

This SQLite implementation is replaceable behind repository/validator contracts. Callers do not receive direct storage access.

## Execution context validation

Every governed context is bound to:

- correlation ID;
- principal ID;
- organization ID;
- exact client scope;
- capability;
- maximum permission mode;
- expiry.

A context fails validation when it is missing, expired, revoked, reused across scope/capability/correlation boundaries, or used for a mode above its authority ceiling.

## Orchestrator enforcement

`CentralOrchestrator` supports `require_authority_context=True`. In that mode:

1. an authority context ID is mandatory;
2. the configured context enforcer validates it before capability resolution;
3. any validation failure terminates the request before provider selection or invocation;
4. the authority context ID is included in correlated orchestration audit metadata.

`JKD001OrchestrationContextEnforcer` adapts the kernel context validator to this generic orchestrator boundary.

Legacy/non-production callers remain compatible while enforcement is disabled. Production ingress must enable enforcement.

## OpenClaw handoff

OpenClaw's `JasonAuthorityEvaluator` now calls JKD-001 using a structured `AuthorityRequest`. Only an allowed decision with an issued execution context can produce a dispatchable context ID.

`OpenClawOrchestratorDispatcher` consumes that issued context ID and places it on the real `OrchestrationRequest`. It no longer succeeds solely because a caller supplied an `authority_allowed` assertion.

OpenClaw still cannot self-assert approval: `approval_present` remains false until a future governed approval-record integration supplies verified state.

## Validation

Dedicated CI verifies:

1. allowed requests issue short-lived execution contexts;
2. cross-client access fails closed;
3. requested authority cannot exceed the grant ceiling;
4. approval-required requests stop without a formal approval record;
5. exact formal approval permits the governed request;
6. durable context storage survives outside request memory;
7. context revocation immediately fails validation;
8. cross-scope context reuse is denied;
9. required context failure happens before capability resolution;
10. OpenClaw cannot dispatch without a context actually issued by JKD-001.

## Remaining production work

1. select the production database path, backup/retention policy, and operating-system ownership on the Jason host;
2. add governed administrative commands for identity/grant/approval lifecycle instead of direct database access;
3. add explicit context-revocation audit events and retention cleanup for expired contexts;
4. deploy the enforced orchestrator/OpenClaw composition on Jason;
5. provision the OpenClaw Ed25519 machine identity and run the fully synthetic signed ingress test.
