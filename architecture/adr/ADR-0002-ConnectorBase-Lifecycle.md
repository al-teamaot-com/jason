# ADR-0002: Use a Shared Connector Lifecycle

**Status:** Accepted  
**Decision date:** 2026-08-03

## Context

Initial connectors repeated capability authorization, secret resolution, request auditing, transport execution, and result construction.

## Decision

Use `ConnectorBase` to implement the shared read-connector lifecycle.

Providers prepare their own requests but reuse the shared lifecycle for:

- capability checks;
- logical secret resolution;
- requested and completed audit events;
- transport execution;
- structured results.

## Consequences

Provider connectors become smaller and remain focused on provider-specific behavior.

Shared lifecycle changes can affect multiple providers and therefore require regression testing.
