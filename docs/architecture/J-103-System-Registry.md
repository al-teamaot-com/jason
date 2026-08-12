# J-103 — Jason System Registry

## Purpose

The System Registry is Jason's authoritative, machine-readable record of operational topology and system state.

Its purpose is to ensure that Jason's production wiring can be understood, verified, supported, recovered, and changed without depending on the memory of a person, AI system, conversation, engineering session, or undocumented local practice.

This document implements Article XIX — Authoritative Operational State of the Jason Constitution.

## Constitutional Boundary

The System Registry is authoritative for operational description. It is not self-authorizing.

A registry record may describe a component, capability, provider, dependency, identity binding, governance gate, credential reference, deployment, or verification method. The existence of that record does not grant authority to create, invoke, modify, repair, disable, or retire the described resource.

All consequential changes continue to require identity-first authorization, applicable policy and governance, Central Orchestrator coordination, approval where required, execution through an authorized capability, verification, and audit evidence.

The System Registry shall never silently remediate drift.

## Registered Entity Types

The registry shall support at least the following durable entity types:

- `component` — a Jason service, subsystem, interface, or other operational building block
- `capability` — a named capability known to the Capability Registry
- `provider` — an implementation that provides one or more capabilities
- `resource` — an external or internal operational resource on which Jason depends
- `dependency` — a directed relationship between registered entities
- `identity_binding` — a governed mapping between an external identity and Jason identity/authority
- `governance_gate` — a policy, approval, or authority boundary applied to operational work
- `credential_reference` — a reference to an approved secret source; never a secret value
- `deployment` — an environment-specific realization of a registered component or provider
- `verification` — a defined method and evidence reference used to establish observed or verified state

The model may expand, but new entity types shall preserve the same governance, audit, versioning, verification, and no-secret requirements.

## State Model

The registry shall keep intended state separate from observation.

### Declared State

Declared state records how an entity is intended to exist or behave. Examples include expected provider, environment, endpoint class, dependency, identity binding, version, governance gate, health condition, or verification requirement.

Declared state is governed configuration and requires authorized change control.

### Observed State

Observed state records what an authoritative observer reports is actually present.

Every observation shall identify its source and observation time. An observation does not rewrite declared state.

### Verified State

Verified state is a conclusion supported by evidence that compares declared and observed state using a defined verification method.

At minimum, verification outcomes shall distinguish:

- `verified` — sufficient evidence indicates observed state satisfies declared state
- `drifted` — material observed state differs from declared state
- `unverified` — sufficient current evidence is unavailable
- `failed` — the verification method could not complete successfully or produced an invalid result

A stale observation shall not be represented as current verification.

## Operational Lifecycle

Registry entities shall have an explicit lifecycle. The baseline lifecycle is:

`proposed -> registered -> configured -> verified -> active -> deprecated -> retired`

An implementation may include additional safe states such as `suspended` or `failed`, but shall not bypass the requirement that production activation depends on registration and verification.

`active` means that the entity is approved for operational use under the applicable governance model. It does not mean that every dependent service is presently healthy.

## Minimum Registration Requirements

A production registry record shall identify, as applicable:

- stable registry identifier
- entity type
- human-readable name
- environment
- lifecycle status
- declared state
- relationships and dependencies
- ownership or stewardship
- authority or governance references
- verification method identifiers
- credential references where required
- evidence references where available
- source/version information
- creation and modification attribution

A record that cannot be verified shall not be represented as verified or active merely because an implementation is believed to work.

## Dependencies and Topology

Dependencies shall be represented as directed relationships rather than hidden in prose.

The registry shall permit both forward and reverse dependency reasoning so Jason can answer questions such as:

- What does this component depend on?
- What depends on this provider?
- Which capabilities are affected if this resource is unavailable?
- Which identity bindings and governance gates are traversed by this operational path?
- Which verification methods prove that a path is currently usable?

Large evidence artifacts shall be stored centrally and referenced rather than copied into registry records.

## Capability Registry Relationship

The System Registry and Capability Registry have separate responsibilities.

The Capability Registry defines *what Jason can do* and the governed contract for that capability.

The System Registry describes *how the currently declared operational system realizes and connects those capabilities*.

The System Registry may reference a Capability Registry identifier and version. It shall not redefine the capability contract.

## Central Orchestrator Relationship

The Central Orchestrator is the only authority for routing governed work between Jason components and capabilities.

The Orchestrator may query the System Registry to understand topology, dependencies, operational status, verification, and implementation relationships.

The Orchestrator shall not treat a registry entry as permission. Identity, policy, approval, tenant/client boundary, and capability authorization checks remain mandatory.

All remediation or topology-changing actions initiated because of registry drift shall return through the normal orchestration and governance path.

## Governed Query Surface

Jason shall expose operational-state knowledge through reusable, provider-neutral, read-only capabilities rather than through conversational memory, hard-coded workflow scripts, direct file access by agents, or bypasses around the Central Orchestrator.

The initial governed query surface is:

- `system.registry.search` — locate registered operational entities using grounded human-supplied selectors;
- `system.registry.read` — read one entity by durable System Registry resource identifier; and
- `system.registry.trace` — trace registered dependency relationships between two System Registry entities.

These capabilities are resolved and invoked through the normal Capability Registry, provider-resolution, identity, policy, authority, audit, and Central Orchestrator path. Their current deterministic internal provider is `system_registry`, whose authoritative source is the governed production registry plus append-only lifecycle history.

The query provider is evidence-producing only. It shall have no method to mutate declared state, append lifecycle events, repair drift, change production services, alter governance, or retrieve secret values.

Query responses may include registered dependencies, reverse dependents, effective lifecycle, verification status, authority references, evidence references, source version, and credential *references*. Secret material is prohibited.

Natural-language interpretation may determine what System Registry resource and facts the human is asking about, but it shall not invent topology, select an unregistered provider, or treat model output as authoritative evidence. Returned facts shall be grounded in deterministic System Registry data.

Ambiguous identity-like searches shall fail closed rather than silently selecting the first result. A durable `resource_id` is the authoritative identity for a specific registry entity.

The query surface does not change the constitutional authority boundary: the System Registry describes operational state; the Central Orchestrator governs work; and any mutation or remediation must return through normal authorization and governance.

## Monitoring and Observation

Monitoring systems and authorized providers may submit observations to the registry through governed interfaces.

Observation sources shall be attributable and scoped. Observed state shall not overwrite declared state.

The registry may calculate or expose drift status but shall not perform corrective execution.

## Identity and Change Authority

Changes to declared operational state shall identify an authenticated principal or authoritative governed system source.

A declared-state change shall carry enough metadata to establish:

- who or what proposed the change
- what changed
- why it changed
- what authority allowed the change
- when it changed
- the previous version
- the resulting version
- which verification is required afterward

Where policy requires approval or separation of duties, registry mutation shall not bypass it.

## Secret Management

Secret values are prohibited from the System Registry.

Credential records shall contain references only, such as an approved secret-provider identifier and logical secret name. They may record non-secret metadata such as required scope, owning provider, availability verification result, or rotation policy reference.

No registry query, generated documentation, topology view, or engineering handoff shall expose secret material.

## Evidence and Audit

Significant registry mutations and verification outcomes are auditable events.

Evidence should be sufficient to reconstruct why Jason believed a production path was valid at a given point in time.

The registry shall preserve or reference, according to policy:

- change events
- prior declared-state versions
- observation sources and timestamps
- verification outcomes
- evidence locations
- approvals and authority references
- relevant deployment or source versions

## Drift

Drift exists when authoritative observed state materially differs from declared state.

Drift detection shall produce a structured result. It may cause an alert, recommendation, escalation, or governed remediation request according to policy.

Drift itself is not authority to change a system.

If evidence is insufficient, the correct state is `unverified`, not an inferred success.

## Generated Operational Documentation

Human-readable operational documentation should be generated from registry truth wherever practical.

Examples include:

- current production topology
- capability-to-provider maps
- dependency matrices
- identity and governance paths
- deployment inventories
- current verification status
- recovery dependency views
- engineering/session handoffs

Generated documents are views of authoritative data. Editing a generated view shall not silently alter authoritative registry state.

## Recovery Requirement

A qualified future contributor with access to the Canon, Constitution, System Registry, referenced evidence, approved secret-management system, and required authority should be able to determine how production Jason is assembled and how each critical path is verified without reconstructing the system from conversation history.

## Initial Implementation Boundary

The first implementation shall provide:

1. a versioned machine-readable registry schema;
2. typed contracts for registered entities, declared state, observations, and verification status;
3. deterministic validation of registry records;
4. an in-memory repository suitable for orchestration integration and testing;
5. tests proving lifecycle, no-secret, declared/observed separation, dependency, and drift behavior.

Persistence, automated observers, visualization, handoff generation, and broader runtime integration may evolve incrementally without weakening the constitutional requirements above.
