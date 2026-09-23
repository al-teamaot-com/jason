# ADR-0007 — Central Execution Provider Registry

**Status:** Accepted

## Context

Jason requires a consistent way to describe every execution provider that may participate in governed work.

Without a central registry, provider identity, health, approval, capability support, classification support, regional limits, pricing linkage, and stewardship metadata would be duplicated across connectors, agents, interfaces, workflows, and policy code.

That duplication would make provider selection inconsistent and would allow external systems to influence policy indirectly.

## Decision

Jason will maintain a centralized, provider-neutral Execution Provider Registry under JKD-005.

The registry is authoritative for provider identity and normalized provider metadata.

The Execution Policy Engine uses registry records as candidate inputs but remains authoritative for execution decisions.

Provider adapters remain responsible for provider-specific authentication, transport, requests, responses, and error handling.

The Kernel owns provider identity.

Providers never own Kernel policy.

## Consequences

### Positive

- provider selection becomes consistent;
- OpenClaw and other interfaces remain policy-neutral;
- health and approval are separate;
- pricing remains versioned and external;
- governance metadata is mandatory;
- providers can be added or retired without changing Kernel policy contracts;
- historical provider IDs remain interpretable.

### Negative

- provider metadata requires stewardship;
- health updates require an operational source;
- capability and provider registries must remain synchronized;
- stale records may reduce selection quality;
- provider retirement requires controlled migration.

## Rejected Alternatives

### Hardcode providers in the Execution Policy Engine

Rejected because it couples policy to vendor identity and makes replacement difficult.

### Let OpenClaw or another interface select providers

Rejected because interfaces are not authorities.

### Store provider metadata only inside connectors

Rejected because connector-local metadata cannot support centralized comparison and policy.

### Automatically trust discovered providers

Rejected because technical discovery does not establish approval, authority, data-handling permission, or business justification.

### Store credentials in the provider registry

Rejected because credentials belong in the Secrets Broker and provider identity boundary.

## Review Triggers

Review this decision when:

- provider metadata becomes insufficient for safe selection;
- a shared platform can replace custom registry behavior;
- capability and provider identity become tightly coupled;
- provider discovery can be safely governed;
- persistence requirements change;
- health or approval semantics become ambiguous.
