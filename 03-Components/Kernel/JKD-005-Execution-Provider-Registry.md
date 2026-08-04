# JKD-005 — Execution Provider Registry

**Status:** Proposed foundation design
**Owner:** Jason Architecture Authority
**Applies to:** All execution providers considered by the Execution Policy Engine

## 1. Purpose

The Execution Provider Registry is the authoritative inventory of execution providers that Jason may consider when planning governed work.

The registry answers:

> Which approved providers are available to execute this capability under the required policy, data-handling, cost, quality, and health constraints?

The registry does not execute work. It supplies normalized provider metadata to the Execution Policy Engine and orchestrator.

## 2. Governing Principle

The Kernel owns provider identity.

Providers never own Kernel policy.

An external platform, model, workflow, connector, agent, or human operator may describe its capabilities and health, but it may not:

- authorize itself;
- approve itself;
- select itself;
- change tenant scope;
- elevate its data-handling permission;
- increase its own budget;
- bypass the Execution Policy Engine;
- redefine Jason policy.

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

The provider registry supplies candidate providers.

The Execution Policy Engine determines whether and how a candidate may be used.

## 4. Provider-Neutral Design

Jason does not hardcode OpenAI, Ollama, OpenClaw, Microsoft Graph, PowerShell, Datto, IT Glue, or a human technician into Kernel decision logic.

Each is represented by a normalized execution-provider record when it participates in governed execution.

Provider-specific authentication, transport, API behavior, and error handling remain inside the appropriate adapter or connector.

## 5. Provider Types

The initial provider types are:

- `hosted_ai`;
- `local_ai`;
- `deterministic`;
- `workflow`;
- `human`;
- `external_connector`.

Provider type describes the execution path. It does not grant permission.

## 6. Provider Identity

Every provider has an immutable provider ID.

Example:

```yaml
provider_id: openai-primary
display_name: OpenAI Primary
provider_type: hosted_ai
```

Rules:

- provider IDs are immutable;
- provider IDs are unique;
- display names may change;
- retired IDs are not reused;
- aliases must resolve to one immutable provider ID;
- provider records contain no secrets.

## 7. Provider Record

A provider record includes:

```yaml
provider:
  provider_id: openai-primary
  display_name: OpenAI Primary
  provider_type: hosted_ai
  lifecycle_status: available
  health_status: healthy
  approval_status: approved
  execution_modes:
    - hosted_ai
  capabilities:
    - ticket.summary
    - ticket.classification
  supported_classifications:
    - public
    - internal
    - confidential
  regions:
    - us
  limits:
    maximum_context_tokens: 128000
    maximum_output_tokens: 16000
    maximum_concurrent_executions: 20
  features:
    tools: true
    vision: true
    streaming: true
    structured_output: true
  pricing_profile_id: openai-primary-default
  stewardship:
    technology_steward: technology-steward
    business_justification: Approved hosted reasoning provider
    review_interval_days: 90
    last_reviewed_at: "2026-08-04T00:00:00Z"
    retirement_criteria:
      - provider no longer approved
      - replacement provides equivalent capability at lower total cost
  metadata: {}
```

## 8. Lifecycle Status

Lifecycle states are:

- `planned`;
- `available`;
- `deprecated`;
- `retired`.

### Planned

The provider is documented but not selectable.

### Available

The provider may be considered when approval, health, capability, and policy requirements are satisfied.

### Deprecated

The provider remains temporarily selectable only when policy explicitly allows it and a migration plan exists.

### Retired

The provider is not selectable.

Retired provider records remain available for historical interpretation and audit.

## 9. Health Status

Health states are:

- `healthy`;
- `warning`;
- `unavailable`;
- `maintenance`;
- `unknown`.

Health is operational state, not approval.

A provider may be approved but unavailable.

A provider may be healthy but blocked.

Health may be updated more frequently than governance metadata.

Unknown health must fail closed or require policy-defined degraded behavior.

## 10. Approval Status

Approval states are:

- `approved`;
- `pilot`;
- `blocked`;
- `retired`.

### Approved

The provider may be selected within policy.

### Pilot

The provider may be selected only for explicitly approved capabilities, clients, environments, or operators.

### Blocked

The provider must not be selected.

### Retired

The provider is permanently removed from active selection.

## 11. Supported Capabilities

The provider record contains capability identifiers that the provider can technically execute.

Capability support does not by itself authorize execution.

The Capability Registry remains authoritative for:

- capability identity;
- capability contract;
- risk;
- required evidence;
- allowed execution modes;
- approval requirements;
- output schema;
- verification requirements.

## 12. Data Classifications

The registry records the classifications a provider may process under its approved configuration.

Initial classifications may include:

- `public`;
- `internal`;
- `confidential`;
- `restricted`.

A classification match is necessary but not sufficient. Tenant-specific and client-specific policy may impose stricter limits.

## 13. Regions and Data Handling

Provider records may declare approved regions.

The registry does not assume that a provider processes data only in the declared region. Regional claims require Technology Steward verification against current vendor terms and implementation settings.

Unknown regional behavior must be visible and must not be treated as approved.

## 14. Limits

Provider limits may include:

- maximum context tokens;
- maximum input tokens;
- maximum output tokens;
- maximum concurrent executions;
- maximum requests per minute;
- maximum executions per client;
- maximum execution duration.

Limits are planning inputs. They do not replace runtime enforcement.

## 15. Feature Metadata

Initial feature metadata includes:

- tool use;
- vision;
- audio;
- streaming;
- structured output;
- function calling;
- batch execution;
- stateful sessions.

Features describe provider capability. They do not imply that every capability may use them.

## 16. Pricing Linkage

Provider records reference a pricing profile by ID.

Pricing values remain in the versioned Pricing Registry defined by JKD-004.

Provider records must not duplicate live pricing values.

Unknown or stale pricing must be visible to the Execution Policy Engine.

## 17. Credentials and Secrets

The registry must never contain:

- API keys;
- passwords;
- access tokens;
- refresh tokens;
- private keys;
- certificate private material;
- client secrets;
- bearer tokens.

Provider records may reference logical secret names or identity profiles only when needed for adapter configuration.

Credential resolution remains the responsibility of the Secrets Broker and provider adapter.

## 18. Governance Metadata

Every available provider requires:

- Technology Steward;
- business justification;
- review interval;
- last review date;
- retirement criteria;
- authoritative vendor-change sources;
- owner for operational health;
- owner for approval decisions.

Missing governance metadata prevents production approval.

## 19. Registry Operations

The initial registry supports:

- register provider;
- retrieve provider by immutable ID;
- list providers;
- find candidates by capability;
- filter by execution mode;
- filter by classification;
- filter by approval;
- filter by lifecycle;
- filter by health;
- update health;
- update governance metadata;
- deprecate provider;
- retire provider.

Provider deletion is not part of the initial contract.

## 20. Candidate Eligibility

A provider is eligible for consideration only when:

- lifecycle is `available`, or policy explicitly allows `deprecated`;
- approval is `approved`, or the request satisfies a governed pilot boundary;
- health is `healthy`, or policy explicitly allows `warning`;
- capability is supported;
- execution mode is allowed;
- data classification is supported;
- required region is supported;
- provider limits can satisfy the request;
- pricing state is acceptable;
- tenant and client policy permit use.

Eligibility does not guarantee selection.

## 21. Immutable and Mutable Fields

### Immutable

- provider ID;
- original provider type;
- creation timestamp.

### Mutable through governed change

- display name;
- capabilities;
- classifications;
- regions;
- limits;
- features;
- pricing profile linkage;
- health;
- approval;
- lifecycle;
- stewardship metadata.

Material changes require audit.

## 22. Audit Requirements

Audit events include:

- provider registered;
- provider metadata changed;
- health changed;
- approval changed;
- lifecycle changed;
- capability support changed;
- classification support changed;
- pricing linkage changed;
- provider considered;
- provider excluded;
- provider selected.

Audit must record actor, timestamp, correlation ID, reason, old state, and new state when applicable.

Audit must not contain secrets.

## 23. Provider Discovery

The initial implementation does not support uncontrolled automatic discovery.

Future discovery may propose provider records, but proposed records remain `planned` and unapproved until reviewed.

No provider becomes selectable merely because an endpoint, MCP server, model, or connector was discovered.

## 24. OpenClaw Boundary

OpenClaw may appear in the registry only as a governed execution provider or interface adapter.

OpenClaw does not:

- own the provider registry;
- select providers;
- approve providers;
- assign tenant scope;
- bypass JKD-004;
- call other agents directly;
- call connectors directly outside the orchestrator.

## 25. Technology Steward Review

The Technology Steward reviews:

- vendor capabilities;
- pricing changes;
- model and API deprecations;
- data-handling terms;
- regional processing;
- security posture;
- operational reliability;
- replacement opportunities;
- opportunities to retire custom code;
- business justification;
- retirement criteria.

## 26. Initial Implementation Scope

The first implementation includes:

- provider-neutral contracts;
- immutable provider IDs;
- lifecycle, health, and approval models;
- in-memory registry;
- candidate filtering;
- governed health updates;
- governed lifecycle updates;
- duplicate protection;
- focused Kernel tests;
- no live provider calls;
- no dynamic provider discovery;
- no persistence;
- no credentials.

## 27. Completion Criteria

JKD-005 is ready for production implementation when:

- provider contracts are approved;
- lifecycle states are approved;
- approval states are approved;
- health states are approved;
- governance metadata is mandatory;
- pricing linkage is defined;
- capability linkage is defined;
- audit requirements are defined;
- initial tests are approved;
- the design passes architectural review.
