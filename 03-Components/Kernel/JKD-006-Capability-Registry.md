# JKD-006 — Capability Registry

**Status:** Proposed foundation design
**Owner:** Jason Architecture Authority
**Applies to:** All invokable capabilities requested through Jason Orchestration

## 1. Purpose

The Capability Registry is the authoritative inventory of governed capabilities that Jason may accept as requests.

The registry answers:

> What named capability exists, what contract and controls define it, and what must be true before an implementation may perform it?

The registry describes capabilities.

It does not execute them, authorize them, or select their providers.

## 2. Governing Principle

The Kernel owns capability identity.

Providers implement capabilities but do not define them.

An execution provider, connector, agent, model, workflow, interface, or external platform may declare technical support for a capability, but it may not:

- create Kernel capability identity;
- redefine a capability's purpose;
- change its contract;
- increase its authority;
- reduce its evidence requirements;
- remove its approval requirements;
- change its tenant or client boundaries;
- select itself as the implementation;
- bypass Orchestration;
- bypass the Execution Policy Engine.

## 3. Position in the Architecture

```text
Capability Request
    |
    v
Identity and Authority
    |
    v
Capability Registry
    |
    v
Execution Provider Registry
    |
    v
Execution Policy Engine
    |
    v
Execution Plan
    |
    v
Provider Adapter
```

The Capability Registry establishes what the requested function means and which controls apply.

The Execution Provider Registry identifies implementations that may technically support it.

The Execution Policy Engine determines whether and how it may be executed.

## 4. Relationship to Existing Capability Documents

Jason currently maintains several related artifacts.

### J-101 architectural capability registry

`02-Architecture/J-101-Capability-Registry.md` defines enduring classes of functionality required by Jason, such as:

- Reasoning;
- Orchestration;
- Identity Resolution;
- Policy Evaluation;
- Audit Recording;
- External-System Interaction.

These use identifiers such as `CAP-001`.

They define architectural requirements and do not necessarily represent individual runtime operations.

### Jason Capability Catalog

`docs/architecture/JASON_CAPABILITY_CATALOG.md` defines invokable canonical capability names such as:

```text
identity.workload.authenticate
secrets.secret.read
governance.action.evaluate
```

These names identify operations requested through Orchestration.

### Jason Capability Register

`06-Roadmaps/Jason-Capability-Register.md` records business capabilities, maturity stages, organizational outcomes, and planned vertical slices.

JKD-006 does not replace these documents.

It provides the machine-readable Kernel foundation needed to represent invokable capability definitions consistently.

## 5. Capability Naming

Invokable capability names use lowercase dot-separated identifiers:

```text
<domain>.<resource>.<action>
```

Examples:

```text
identity.workload.authenticate
governance.action.evaluate
autotask.ticket.create
evidence.record.query
```

Initial naming rules:

- names are immutable;
- names are unique;
- names use lowercase ASCII letters, digits, and dots;
- each segment begins and ends with a letter or digit;
- empty segments are prohibited;
- display names may change;
- retired names are not reused;
- aliases must resolve to one canonical capability name;
- vendor names are used only when the capability is intentionally vendor-specific;
- capability names describe intent rather than implementation mechanics.

## 6. Capability Version

Each capability has a version.

The initial foundation represents versions as immutable strings.

Recommended initial format:

```text
1.0
1.1
2.0
```

A capability name and version together identify a contract.

Rules:

- contract versions are immutable after registration;
- compatible changes require a documented versioning decision;
- breaking changes require a new major version;
- historical versions remain interpretable for audit;
- providers declare the capability versions they support;
- version compatibility must never be inferred silently.

The first implementation will not perform advanced semantic-version range resolution.

## 7. Capability Lifecycle

Initial lifecycle states are:

- `proposed`;
- `building`;
- `pilot`;
- `active`;
- `deprecated`;
- `suspended`;
- `retired`.

### Proposed

The capability is documented but not available for execution.

### Building

The capability is under implementation and is not generally available.

### Pilot

The capability may be used only within explicitly approved pilot scope.

### Active

The capability may be requested when identity, policy, provider, evidence, and approval requirements are satisfied.

### Deprecated

The capability remains temporarily available for controlled migration.

### Suspended

The capability is temporarily unavailable because of risk, control, quality, or operational concerns.

### Retired

The capability is no longer available for new work.

Retired records remain available for historical interpretation and audit.

## 8. Capability Record

The initial record includes:

- canonical capability name;
- version;
- display name;
- lifecycle status;
- business purpose;
- owner service;
- architectural capability ID references;
- risk level;
- data classifications;
- permitted execution modes;
- input and output schema references;
- invoking roles;
- approval requirements;
- evidence requirements;
- dependencies;
- idempotency behavior;
- timeout and retry constraints;
- tenant and client isolation requirements;
- failure behavior;
- stewardship metadata;
- deprecation and retirement criteria;
- optional metadata.

The Kernel contracts are authoritative for the current implementation.

## 9. Registry Operations

The initial registry supports:

- register capability;
- retrieve by canonical name and version;
- list all registered versions;
- resolve the current version;
- filter by lifecycle;
- filter by architectural capability ID;
- filter by permitted execution mode;
- filter by risk level;
- update lifecycle through a governed service operation.

Registered name-and-version pairs are immutable and may not be silently overwritten.

## 10. Current Version Resolution

The current version is the highest registered numeric dotted version that is `active`.

Pilot versions may be included only when pilot use is explicitly allowed.

Proposed, building, deprecated, suspended, and retired versions are not resolved as current by default.

Semantic-version ranges and prerelease labels are deferred.

## 11. Validation

Pilot and active capabilities must include:

- a business purpose;
- an owner service;
- at least one architectural capability ID;
- at least one permitted execution mode;
- at least one data classification;
- input and output schema references;
- at least one invoking role;
- explicit failure behavior;
- a positive timeout;
- at least one allowed attempt;
- stewardship metadata;
- evidence requirements when evidence is mandatory;
- approver classes when approval is required.

Invalid canonical names and self-dependencies are rejected.

## 12. Relationship to the Execution Provider Registry

The Capability Registry is authoritative for:

- capability identity;
- capability versions;
- contract references;
- lifecycle;
- risk;
- authority and approval metadata;
- evidence requirements;
- permitted execution modes;
- isolation requirements;
- failure behavior.

The Execution Provider Registry is authoritative for provider identity, health, approval, limits, features, regions, pricing linkage, and provider stewardship.

Provider capability declarations indicate technical support only.

They do not create capability identity or authorize execution.

## 13. Non-Responsibilities

The Capability Registry does not:

- authenticate identities;
- resolve authority;
- evaluate policy;
- obtain approval;
- select providers;
- execute capabilities;
- call external systems;
- manage secrets;
- store evidence;
- orchestrate dependencies;
- retry executions;
- validate full payload schemas;
- create capabilities through dynamic discovery.

## 14. Foundation Scope

The first implementation will include:

- immutable capability name and version identity;
- lifecycle, risk, and idempotency enums;
- approval, evidence, and stewardship metadata;
- capability contracts;
- in-memory registration and lookup;
- duplicate identity protection;
- deterministic listing;
- current-version resolution;
- lifecycle, architectural-ID, execution-mode, and risk filtering;
- governed lifecycle updates;
- pilot and active validation;
- focused Kernel tests.

The foundation will not include:

- persistence;
- full JSON Schema validation;
- aliases;
- circular-dependency detection;
- automatic provider synchronization;
- planner or orchestrator integration;
- Execution Policy Engine integration;
- audit persistence;
- dynamic discovery;
- live execution.

## 15. Acceptance Criteria

The foundation is acceptable when:

1. capability name and version identity are immutable;
2. duplicate name-and-version registration is rejected;
3. invalid canonical names are rejected;
4. current-version resolution is deterministic;
5. pilot and active records fail validation when governance metadata is incomplete;
6. self-dependencies are rejected;
7. lifecycle changes are explicit;
8. filtering is deterministic;
9. no provider, connector, credential, or execution logic is introduced;
10. tests pass independently of any live provider;
11. documentation and implementation remain aligned.

## 16. References

- `02-Architecture/J-101-Capability-Registry.md`
- `04-Standards/J-402-Capability-Definition-of-Done.md`
- `06-Roadmaps/Jason-Capability-Register.md`
- `docs/architecture/JASON_CAPABILITY_CATALOG.md`
- `03-Components/Kernel/JKD-004-Execution-Policy-Engine.md`
- `03-Components/Kernel/JKD-005-Execution-Provider-Registry.md`
- `architecture/adr/ADR-0008-Central-Capability-Registry.md`
