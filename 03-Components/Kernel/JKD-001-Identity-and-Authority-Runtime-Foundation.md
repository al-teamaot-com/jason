# JKD-001 — Identity and Authority Runtime Foundation

## Status

Draft implementation foundation.

## Purpose

Implement the first executable slice of the approved JKD-001 Identity and Authority Service so callers such as OpenClaw can receive a real, scoped, short-lived authority decision instead of relying on placeholder authorization logic.

## Constitutional role

This service is a kernel authority boundary. Authentication alone never permits action. The service decides whether the authenticated principal may request a named capability for the exact organization/client scope and requested mode.

It does not invoke providers, capabilities, agents, or workflows.

## Implemented contracts

The runtime foundation defines:

- canonical identity records;
- scoped authority grants;
- formal approval records;
- permission levels: observe, recommend, request_approval, execute, administer;
- authority requests;
- five-result authority decisions: allowed, allowed_limited, approval_required, denied, indeterminate;
- short-lived immutable execution contexts.

## Evaluation rules

The service fails closed when:

- the principal identity cannot be resolved;
- the identity is inactive;
- organization scope differs from the identity organization;
- no active grant matches the exact capability and client scope;
- a requested mode exceeds the available grant and cannot be safely limited;
- a required approval is absent, expired, belongs to another request, capability, organization, client, or requester.

An organization-wide grant is not silently interpreted from a missing client ID. Grant and request client scopes must match exactly, including `None` only when the explicitly modeled request is itself organization/internal scoped.

## Limited authority

If the request exceeds the grant but the grant still permits at least `recommend`, the service may return `allowed_limited` with a maximum mode. This never upgrades authority and does not permit execution beyond that ceiling.

## Approval binding

Approval is a formal record. A valid approval must match:

- approval ID;
- originating request ID;
- capability;
- organization;
- client scope;
- requesting principal;
- approved status;
- non-expired lifetime.

Free-form chat text, requested mode, or an OpenClaw payload flag cannot substitute for this record.

## Execution context

Allowed and safely limited outcomes receive a short-lived execution context containing:

- context ID;
- correlation ID;
- principal;
- organization/client scope;
- capability;
- requested and maximum modes;
- outcome;
- matched authority grants;
- authentication assurance;
- issue and expiry timestamps.

Default context lifetime is five minutes.

## Current storage boundary

The first implementation uses repository protocols with in-memory reference repositories so evaluation semantics can be validated independently of storage technology.

Before production deployment, identity, grants, approvals, and issued-context validation must be bound to governed durable storage. Storage must preserve auditability and revocation semantics without giving callers direct write access to authority records.

## Validation

Dedicated CI verifies:

1. allowed requests issue short-lived execution contexts;
2. cross-client access fails closed;
3. requested authority cannot exceed the grant ceiling;
4. approval-required requests stop without a formal approval record;
5. valid exact-scope approval permits the governed request;
6. wrong/expired approval fails closed;
7. missing identity returns indeterminate rather than guessing.

## Next work

1. add durable identity/grant/approval repositories;
2. add execution-context validation/revocation;
3. add authority-decision audit events;
4. bind OpenClaw `JasonAuthorityEvaluator` to this service using the structured decision/context rather than a string-only placeholder;
5. bind the Central Orchestrator to require the issued execution context for downstream capability execution.
