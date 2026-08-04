# ADR-0008 — Central Capability Registry

**Status:** Accepted

## Context

Jason requires a deterministic and provider-neutral way to identify the
capabilities that may be requested, governed, planned, executed, and audited.

Without a central Capability Registry, capability identity, contracts,
risk, authority, evidence requirements, execution constraints, ownership,
lifecycle, and stewardship metadata would be duplicated across
orchestration, providers, connectors, workflows, interfaces, and policy
code.

That duplication would create several risks:

- providers could redefine capability meaning;
- interfaces could invoke implementation-specific operations directly;
- capability contracts could drift between implementations;
- policy evaluation could depend on vendor terminology;
- retired or deprecated capabilities could remain silently usable;
- planners could select technically available work that is not approved;
- audit records could lose the stable identity of the requested function.

Jason already distinguishes enduring capabilities from replaceable
implementations. The architecture therefore requires an authoritative
Kernel-owned registry of capability identity and normalized capability
metadata.

The project currently uses two related forms of capability identification:

1. architectural capability IDs such as `CAP-001`, defined by
   `02-Architecture/J-101-Capability-Registry.md`; and
2. invokable canonical capability names such as
   `governance.action.evaluate`, defined by the Jason Capability Catalog.

These identifiers serve different purposes and must not be conflated.

Architectural capability IDs describe enduring classes of functionality
required by Jason.

Invokable capability names identify versioned contracts that may be
requested through Orchestration.

## Decision

Jason will maintain a centralized, provider-neutral Capability Registry
under JKD-006.

The registry is authoritative for invokable capability identity and
normalized capability metadata.

Each registered capability will have:

- an immutable canonical capability name;
- a versioned contract identity;
- lifecycle state;
- business purpose;
- owner;
- risk and data classification;
- permitted execution modes;
- authority and approval requirements;
- input and output schema references;
- evidence and verification requirements;
- dependency declarations;
- idempotency, timeout, and retry behavior;
- tenant and client isolation requirements;
- failure behavior;
- stewardship metadata;
- deprecation and retirement criteria.

The Capability Registry will reference the applicable architectural
capability IDs where useful, but it will not replace
`J-101 — Jason Capability Registry`.

The Capability Registry will not:

- execute work;
- select an execution provider;
- authorize a request;
- evaluate policy;
- obtain approval;
- store secrets;
- inspect provider implementations dynamically;
- allow providers to create or redefine Kernel capability identity.

The Execution Provider Registry may declare that a provider technically
supports a registered capability.

The Execution Policy Engine remains authoritative for whether and how the
capability may be executed.

Orchestration remains responsible for routing capability requests,
transferring authorized context, managing state, and assembling results.

The Kernel owns capability identity.

Providers implement capabilities but do not define them.

## Consequences

### Positive

- capability requests use stable canonical identifiers;
- providers remain replaceable;
- orchestration remains independent of vendor APIs;
- policy can evaluate normalized capability metadata;
- planners can discover governed capabilities deterministically;
- capability contracts can be versioned and validated;
- lifecycle and deprecation behavior become explicit;
- provider and capability responsibilities remain separate;
- audit records retain stable capability identity;
- capability ownership and stewardship become enforceable.

### Negative

- capability metadata requires continuing stewardship;
- capability and provider registries must remain synchronized;
- schema compatibility requires explicit version management;
- duplicate or overlapping capabilities require architectural review;
- registry persistence will eventually be required;
- migrations must preserve historical capability identity.

## Rejected Alternatives

### Use provider capability strings as the authoritative catalog

Rejected because providers must not define Kernel identity, policy,
contracts, or authority.

### Hardcode capabilities in Orchestration

Rejected because orchestration coordinates work and should not become the
authoritative catalog of business and platform functions.

### Derive capabilities automatically from connector methods

Rejected because technical methods do not establish approval, governance,
risk, evidence, contract stability, or business justification.

### Use only architectural IDs such as `CAP-001`

Rejected because architectural capability classes do not uniquely identify
the versioned operations requested during runtime.

### Store capability definitions only in documentation

Rejected because runtime validation, deterministic discovery, planning,
policy evaluation, and testing require a machine-readable Kernel model.

### Combine the Capability Registry and Execution Provider Registry

Rejected because capability identity and provider identity evolve
independently.

A capability may have many providers.

A provider may implement many capabilities.

Neither should redefine the other.

## Review Triggers

Review this decision when:

- capability metadata becomes insufficient for policy or planning;
- architectural capability IDs and invokable names become ambiguous;
- schema-version handling requires a dedicated contract registry;
- persistence requirements change;
- a dependable approved platform can replace custom registry behavior;
- capability and provider synchronization becomes unreliable;
- dynamic discovery can be governed without transferring authority;
- lifecycle or deprecation semantics become unclear.
