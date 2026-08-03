# Jason Integration SDK Provider Development Guide

**Name:** Jason Integration SDK  
**Abbreviation:** JIS  
**Status:** Active engineering guidance  
**Owner:** Jason Architecture Authority  
**Applies to:** All external platform integrations developed for Project Jason

## 1. Purpose

The Jason Integration SDK (JIS) is the standard integration framework for external systems connected to Project Jason.

JIS provides a single, governed implementation path for provider integrations. It ensures that providers follow consistent patterns for:

- authentication;
- authorization;
- secret resolution;
- transport;
- operation routing;
- audit logging;
- error handling;
- testing;
- production validation;
- read and mutation controls;
- user-interface access.

JIS exists to reduce unnecessary duplication, improve maintainability, preserve governance boundaries, and make providers behave consistently without erasing legitimate provider-specific behavior.

## 2. Scope

This guide defines how Jason providers and shared integration infrastructure are designed, implemented, tested, validated, and maintained.

It does not replace:

- the Jason Constitution;
- provider-specific specifications;
- capability specifications;
- deployment procedures;
- security policies;
- vendor documentation.

Where requirements conflict, the Jason Constitution and approved architecture decisions take precedence.

## 3. Architectural Placement

User Interfaces  
CLI / Platform API / Teams / OpenClaw / n8n

↓

Jason orchestration and authority

↓

Jason Integration SDK (JIS)

↓

JIS Providers

↓

External Platforms

Interfaces must not bypass JIS to communicate directly with external providers.

Agents must not invoke providers directly. Provider use must flow through Jason's orchestration, authority, policy, approval, audit, and routing boundaries.

## 4. Terminology

### Provider

A provider is the JIS implementation for one external platform, such as:

- Autotask;
- IT Glue;
- Datto RMM;
- Microsoft Graph;
- Duo;
- n8n.

A platform may contain many entity types and operations. Those entities are not separate integrations.

### Connector

A connector is the provider component that translates an authorized Jason capability into a provider request and returns a structured result.

### Operation Registry

An operation registry is a declarative mapping between named Jason capabilities and provider operations.

It should describe behavior such as:

- HTTP method;
- path template;
- required path arguments;
- query-parameter mappings;
- optional arguments.

### Generic Entity Gateway

A generic entity gateway provides shared operations across approved entity or resource types when the provider API supports a consistent model.

Preferred generic read capabilities are:

- `<provider>.entity.describe`
- `<provider>.entity.get`
- `<provider>.entity.query`

Equivalent terminology may be used where a provider's API does not support this model cleanly.

### Capability

A capability is a named and registered action available to Jason. Capabilities remain subject to authority, policy, scope, audit, and approval controls.

## 5. JIS Engineering Principles

### 5.1 Provider-neutral infrastructure

Shared integration infrastructure should be provider-neutral by default.

Examples include:

- connector lifecycle handling;
- secret resolution interfaces;
- audit interfaces;
- transport interfaces;
- mutation authority;
- retry behavior;
- pagination support;
- rate-limit handling;
- testing utilities;
- CLI and API integration helpers.

Provider-specific code should be limited to behavior genuinely required by that platform.

### 5.2 Generalize on evidence

Do not introduce abstractions only for hypothetical future needs.

Preferred sequence:

1. Build the first implementation cleanly.
2. Observe a repeated need in another implementation.
3. Identify the genuinely shared behavior.
4. Extract the shared behavior into JIS.
5. Preserve provider-specific exceptions where appropriate.

A unique business capability does not need to improve future integrations.

The working distinction is:

> Generalize infrastructure. Specialize capabilities.

### 5.3 Configuration before repetitive code

Prefer explicit declarative configuration over repeated routing logic when it improves clarity.

Examples include:

- operation registries;
- capability catalogs;
- approved entity allow-lists;
- provider metadata;
- field mappings.

Configuration must remain understandable and reviewable. Avoid hidden reflection, unnecessary metaprogramming, or other mechanisms that make request behavior difficult to trace.

### 5.4 Governed by design

Every provider interaction must use Jason's governance boundaries.

At minimum, this includes the applicable controls for:

- named capability registration;
- identity and authority;
- client and organization scope;
- secrets resolution;
- audit correlation;
- provider request execution;
- safe error handling;
- mutation approval;
- idempotency;
- verification and rollback planning.

Governance is part of the execution path, not an optional wrapper.

### 5.5 One implementation path

All Jason interfaces must consume the same JIS provider implementation.

This includes:

- Jason CLI;
- Jason Platform API;
- Teams;
- OpenClaw;
- n8n;
- future web or mobile interfaces.

An interface must not build a second direct integration with the provider.

### 5.6 Explicit provider boundaries

Provider-specific behavior remains inside its provider package.

Examples include:

- Autotask zone discovery;
- IT Glue JSON:API conventions;
- Microsoft Graph authentication;
- Datto RMM endpoint structure;
- vendor-specific pagination or rate limits.

Shared code must not accumulate knowledge of provider credential fields, URLs, or entity names unless that knowledge is part of an explicitly approved shared contract.

### 5.7 Fail closed

Unknown capabilities, entities, operations, arguments, identities, scopes, and approval states must fail closed.

Generic entity gateways must use explicit allow-lists or equivalent governed discovery. User-supplied entity names must never provide unrestricted access to arbitrary provider endpoints.

### 5.8 Production validation

A provider is not considered operationally complete until it has been validated against an authorized real environment.

Unit tests alone are not sufficient.

Production validation should confirm, as applicable:

- authentication;
- least-privilege access;
- secret retrieval;
- endpoint discovery;
- request execution;
- response handling;
- provider permissions;
- audit behavior;
- safe failure behavior;
- absence of secret disclosure.

Production validation must not display or commit secret values.

### 5.9 Backward compatibility

Adding a provider should not require modifications to unrelated existing providers.

Changes to shared JIS infrastructure should preserve existing provider behavior unless an intentional breaking change has been reviewed and approved.

### 5.10 Small incremental changes

JIS should evolve through small, reviewable pull requests.

Each pull request should:

- solve one defined concern;
- declare its scope;
- identify out-of-scope work;
- preserve behavior when practical;
- include automated tests;
- pass repository validation;
- receive production validation when appropriate.

Large rewrites should be avoided when an incremental migration is practical.

### 5.11 Integrate before inventing

Before implementing custom platform behavior, verify whether the provider or an existing approved open-source project already supplies the required capability.

Custom code should have:

- a clear business justification;
- an identified owner;
- a review interval;
- retirement criteria where appropriate.

### 5.12 Provider exceptions are allowed

A provider may require unique behavior that does not fit a generic abstraction.

Such behavior is acceptable when it:

- reflects a real provider requirement;
- remains isolated to that provider;
- does not weaken Jason governance;
- is tested;
- is documented in the provider specification.

JIS must not force false uniformity where providers are genuinely different.

## 6. Standard Provider Development Lifecycle

### Phase 1: Discovery and justification

Before implementation:

1. Confirm the business requirement.
2. Review the provider's current official API and supported authentication methods.
3. Search the repository and approved open-source projects for reusable implementations.
4. Identify existing platform capabilities that may eliminate custom development.
5. Define the first narrow, useful read-only capability.
6. Identify required permissions and data scope.

### Phase 2: Provider foundation

Create or confirm:

- the provider package;
- `ConnectorBase` inheritance;
- provider name;
- logical secret name;
- approved capabilities;
- provider-specific authentication and headers;
- provider-specific endpoint or discovery behavior;
- safe transport behavior;
- audit correlation.

The connector must not embed raw credentials.

### Phase 3: Secret and identity provisioning

Define:

- the logical secret contract;
- approved secret fields;
- the least-privilege provider identity;
- the least-privilege secret-store identity;
- credential file ownership and permissions;
- token lifetime and use limits where supported;
- rotation and expiration requirements.

Read and write identities should remain separate when practical.

### Phase 4: Operation registry

Create a declarative operation registry when multiple operations share a consistent routing pattern.

The registry should include only what is needed to describe provider operations clearly.

Hard-coded conditional routing should be removed when the registry provides a simpler and more reviewable model.

### Phase 5: Generic entity gateway

Implement generic entity operations when the provider supports a consistent entity model.

Use an explicit approved entity catalog.

Do not expose arbitrary path construction.

Keep entity-specific capabilities when:

- the operation cannot be represented safely by the generic gateway;
- the provider requires a special endpoint;
- the business capability requires additional validation;
- the result needs specialized handling.

### Phase 6: Automated testing

Testing should cover:

- capability authorization;
- secret resolution contract;
- operation routing;
- required and optional arguments;
- malformed arguments;
- approved and unapproved entities;
- request preparation;
- audit events;
- response handling;
- safe provider failures;
- mutation authority where applicable.

Shared JIS infrastructure requires focused shared tests in addition to provider tests.

### Phase 7: Production validation

Perform a controlled read-only validation before write enablement.

Validate a known record and at least one query or collection operation where supported.

Confirm that:

- credentials are not displayed;
- audit details exclude secrets;
- access is limited to expected entities;
- provider permissions match the intended scope;
- failures are controlled and understandable.

### Phase 8: User interfaces

After the provider path is proven:

1. Add CLI access where operationally useful.
2. Add Jason Platform API access.
3. Add other interfaces only through the same JIS implementation.
4. Provide human-readable output and machine-readable output where appropriate.

The Platform API must remain a thin interface over orchestrated JIS capabilities. It must not become a second provider integration.

### Phase 9: Mutation enablement

Write support is a separate governed phase.

It should reuse the read infrastructure but add:

- a separate restricted write identity where practical;
- mutation policies;
- business reason requirements;
- approval requirements;
- argument digest binding;
- idempotency;
- current-state verification;
- mutation planning;
- execution controls;
- result verification;
- rollback or compensating-action guidance;
- mutation audit events.

Read access does not imply write authority.

### Phase 10: Completion and maintenance

Before declaring a provider complete:

- register capabilities;
- update provider documentation;
- record production-validation evidence;
- confirm tests and CI;
- review the Provider Development Guide for needed changes;
- define the provider owner;
- define the vendor-change review cadence;
- document known limitations and exceptions.

## 7. Provider Package Expectations

A mature provider will generally contain:

- `implementation/connectors/<provider>/__init__.py`
- `implementation/connectors/<provider>/connector.py`
- `implementation/connectors/<provider>/operations.py`
- `implementation/connectors/<provider>/mutations.py`

Additional files may be introduced for real provider needs such as:

- metadata;
- pagination;
- field translation;
- webhook handling;
- health checks;
- provider-specific schemas.

Files should be added because the provider requires them, not merely to match another provider's directory shape.

## 8. Provider Specification Expectations

Each mature provider should have a provider specification covering:

- purpose;
- authentication;
- logical secrets;
- least-privilege identities;
- supported capabilities;
- approved entities;
- operation registry;
- provider-specific behavior;
- pagination and rate limits;
- read/write boundaries;
- known limitations;
- production-validation process;
- vendor documentation references;
- Technology Steward review requirements.

## 9. Definition of Done

A provider or material JIS change is complete when the applicable items below are satisfied:

- [ ] Scope and success criteria are defined.
- [ ] Out-of-scope items are identified.
- [ ] Named capabilities are registered.
- [ ] Provider credentials use logical secret names.
- [ ] Least-privilege identity is established.
- [ ] Connector uses shared JIS lifecycle infrastructure.
- [ ] Provider-specific behavior remains isolated.
- [ ] Operation registry exists where appropriate.
- [ ] Generic entity gateway exists where appropriate.
- [ ] Entity and operation access fails closed.
- [ ] Automated tests pass.
- [ ] Full regression tests pass.
- [ ] Repository and security checks pass.
- [ ] Production validation is complete when applicable.
- [ ] No credentials or tokens appear in source, output, audit, or tests.
- [ ] Provider documentation is updated.
- [ ] The Provider Development Guide was reviewed for possible updates.
- [ ] Changes are merged through an approved pull request.

## 10. Architectural Placement Decision

Use the following guidance when deciding where a requirement belongs:

| Requirement scope | Destination |
|---|---|
| Core Jason philosophy, authority, or governance | Jason Constitution |
| Shared integration infrastructure | Jason Integration SDK |
| Provider-specific behavior | Provider Specification |
| Business workflow or outcome | Jason Capability |
| Deployment and operational procedure | Operations documentation |
| Future improvement not required for current delivery | Backlog |

## 11. Change Discipline

Before expanding the scope of an active pull request, ask:

> Does this change unblock or correctly complete the current pull request?

If yes, include it.

If no, record it in the backlog and continue the current work.

Architecture improvements that materially prevent duplication or an incorrect implementation path may be addressed immediately, but they must replace the prior plan rather than accumulate as unlimited additional scope.

## 12. Review Questions

Every JIS review should consider:

1. Is this shared infrastructure or provider-specific behavior?
2. Is the abstraction supported by demonstrated repetition?
3. Does the implementation fail closed?
4. Can the full provider request be traced clearly?
5. Does any interface bypass JIS?
6. Are identity and secret permissions least privilege?
7. Are read and write authority separated appropriately?
8. Are audit records useful without exposing sensitive data?
9. Has production behavior been validated?
10. Does the Provider Development Guide need to change?

## 13. Knowledge Preservation Principle

> No implementation is complete until it is understandable by a competent engineer who did not write it.

Documentation, tests, architecture records, and operational guidance are part of delivery rather than optional work performed after implementation.

## 14. Guiding Statement

> JIS provides one governed integration path for Jason while allowing each provider and each business capability to remain as specialized as the real requirement demands.

Shared infrastructure should become more reusable as demonstrated patterns emerge. Unique capabilities should remain focused on delivering their intended business outcomes.
