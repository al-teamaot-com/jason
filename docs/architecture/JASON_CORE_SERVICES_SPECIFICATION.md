# Jason Core Services Specification

Status: Approved foundational architecture
Version: 1.0

## 1. Purpose

The Jason Core Services Specification defines the mandatory platform contract for every Jason service. Its purpose is to make services secure, observable, governable, replaceable, independently deployable, and consistent across the platform.

Jason is an operating platform, not a loose collection of applications. Every component must conform to this specification unless a documented constitutional exception is approved.

## 2. Core principles

Every Jason service shall:

- have one clearly defined responsibility;
- expose a stable public contract;
- authenticate through approved platform identity mechanisms;
- retrieve secrets only through the Jason Secrets Broker;
- submit governed actions to the Jason Governance Engine;
- emit evidence for significant decisions and actions;
- use the Jason Event Bus for asynchronous coordination;
- fail safely and fail closed when trust, authorization, policy, or secret retrieval cannot be established;
- avoid duplicating capabilities already available in dependent platforms;
- document its business justification, owner, review interval, and retirement criteria;
- remain replaceable without requiring changes to unrelated business logic.

## 3. Platform integrity rule

No Jason component shall bypass the platform.

This includes the following mandatory rules:

- agents shall never invoke or communicate with other agents directly;
- all inter-agent coordination shall pass through the central orchestration layer;
- services shall not bypass identity, governance, secrets, evidence, or approved event-routing contracts;
- connectors shall not embed business policy;
- services shall not write directly to another service's datastore;
- services shall not retrieve secrets directly from OpenBao or another provider when an approved broker capability exists;
- vendor-specific APIs shall be hidden behind adapters whenever practical;
- artifacts and evidence shall be stored centrally and passed by reference when large or sensitive.

## 4. Mandatory service endpoints

Every service shall expose:

```text
GET /health
GET /ready
GET /version
GET /metrics
```

### 4.1 `/health`

Reports whether the process is alive and able to perform basic internal functions. It must not depend on every external system being available.

### 4.2 `/ready`

Reports whether the service is ready to accept work. It shall include required dependency status without exposing credentials or sensitive configuration.

### 4.3 `/version`

Returns the service version, build identifier, contract version, and deployment metadata needed for support and rollback.

### 4.4 `/metrics`

Exposes machine-readable operational metrics in the platform-approved format.

Optional endpoints may include:

```text
POST /reload
POST /validate
```

Any state-changing administrative endpoint requires explicit authorization and evidence generation.

## 5. Identity and trust

The Jason Identity Service establishes trust for:

- human operators;
- service identities;
- workload identities;
- machine identities;
- approved external systems.

Services shall not use shared passwords or shared static API keys for service-to-service authentication.

Approved mechanisms may include:

- mutual TLS;
- signed short-lived JWT workload identities;
- OpenBao AppRole during bootstrap or controlled transitional use;
- other mechanisms approved by governance.

Identity answers who or what is making the request. Authorization remains a governed decision.

## 6. Secrets

Services shall not permanently store passwords, API keys, access tokens, private keys, certificates, or encryption keys.

Secrets shall be requested from the Jason Secrets Broker using provider-neutral references, for example:

```text
secret://jason/development/autotask/api-secret
```

The Secrets Broker resolves the configured provider. OpenBao is the initial provider, not an architectural dependency.

Secrets must not appear in:

- source control;
- prompts;
- logs;
- evidence records;
- event payloads;
- health responses;
- exception traces;
- support bundles.

Secret access shall generate metadata-only audit evidence, including requesting identity, reference, purpose, timestamp, and outcome.

## 7. Governance

Before executing a governed action, a service shall request a decision from the Jason Governance Engine.

Supported outcomes include:

- allow;
- deny;
- require human approval;
- require additional evidence;
- escalate;
- defer pending an external condition.

Business services and connectors shall not implement independent policy decisions that conflict with or bypass the Governance Engine.

When governance is unavailable and the action is governed, the service shall fail closed.

## 8. Events and coordination

The Jason Event Bus provides asynchronous communication and decouples producers from consumers.

Services publish domain events and subscribe only to events required by their capability contracts. Event producers do not need to know which consumers process an event.

Every event shall include:

- event type;
- event schema version;
- event identifier;
- correlation identifier;
- causation identifier when applicable;
- producing identity and service;
- timestamp;
- tenant or client boundary where applicable;
- sensitivity classification;
- payload reference or bounded payload;
- retry and idempotency information where applicable.

Secret values are prohibited in events.

Synchronous service calls are permitted only through documented public interfaces and shall not create hidden coupling or bypass governance.

## 9. Evidence

Every significant action shall produce evidence sufficient to determine:

- who or what requested it;
- what capability was requested;
- which policy decision applied;
- what approvals were required and obtained;
- what action was attempted;
- what result occurred;
- when it occurred;
- how long it took;
- which version of the service performed it;
- which correlation ID links related events and actions.

Evidence shall never contain secret values.

Evidence records shall be append-oriented, integrity-protected, centrally searchable, and retained according to applicable AOT policy and client requirements.

## 10. Configuration

Configuration shall be explicit, versioned, validated, and reproducible.

Configuration precedence is:

1. service defaults;
2. environment-specific configuration;
3. Jason platform configuration;
4. governance-approved overrides.

Secrets are not configuration and shall not be stored in configuration files.

Runtime mutation is prohibited unless the service explicitly supports it through a governed and evidenced administrative capability.

## 11. Observability

Every service shall emit:

- structured logs;
- health and readiness state;
- operational metrics;
- version and build data;
- startup and shutdown records;
- dependency status without sensitive details;
- correlation identifiers.

Services should support distributed tracing when the platform tracing standard is introduced.

Logs shall be suitable for central collection and must preserve client and tenant boundaries.

## 12. Error handling and resilience

Services shall:

- fail closed when identity, authorization, governance, or required secret retrieval cannot be established;
- use bounded retries with backoff;
- implement timeouts for external dependencies;
- support idempotency for retried state-changing requests;
- avoid partial execution where practical;
- produce evidence for failed and denied actions;
- provide actionable but non-sensitive error messages;
- support controlled rollback or compensation when an action spans multiple systems.

## 13. Standard service declaration

Every service shall maintain a service declaration containing:

- service name and identifier;
- purpose;
- business justification;
- owner;
- lifecycle state;
- version;
- public capabilities;
- public interfaces;
- required dependencies;
- identity and authorization model;
- secret references required;
- governance requirements;
- evidence requirements;
- event publications and subscriptions;
- data classifications handled;
- tenant-boundary controls;
- health and readiness behavior;
- backup and recovery requirements;
- review interval;
- retirement criteria.

## 14. Core services

The initial core services are:

### 14.1 Jason Identity Service

Establishes workload, machine, service, and human trust. It does not store business-system credentials.

### 14.2 Jason Secrets Broker

Provides the provider-independent secrets capability. OpenBao is the initial adapter.

### 14.3 Jason Governance Engine

Evaluates policy and determines whether an action is allowed, denied, requires approval, or requires additional evidence.

### 14.4 Jason Evidence Store

Stores integrity-protected records of decisions, actions, approvals, deployments, and verification results without storing secrets.

### 14.5 Jason Event Bus

Provides governed asynchronous messaging and decoupled coordination.

## 15. Dependency and deployment order

Initial dependency order:

```text
Host and container platform
        |
        +-- OpenBao
        +-- Jason Identity Service
        +-- Jason Secrets Broker
        +-- Jason Event Bus
        +-- Jason Governance Engine
        +-- Jason Evidence Store
        +-- Platform services
        +-- Business connectors
        +-- AI capabilities
        +-- OpenClaw operator integration
```

The exact bootstrap sequence may use narrowly scoped temporary credentials, but all temporary bootstrap mechanisms must have documented removal criteria.

Circular dependencies are prohibited unless explicitly reviewed and approved.

## 16. Lifecycle

Every service progresses through:

1. proposed;
2. approved;
3. development;
4. testing;
5. production;
6. deprecated;
7. retired.

A service cannot enter production without:

- a completed service declaration;
- documented threat and failure analysis;
- tested health and readiness behavior;
- governance and evidence integration;
- backup and recovery documentation where stateful;
- rollback instructions;
- approved operational ownership.

## 17. Integrate before innovate

Before a new custom service or capability is approved, the owner shall document:

- whether an existing platform already provides the capability;
- why integration is insufficient;
- the business value of custom implementation;
- expected maintenance burden;
- review interval;
- retirement or replacement criteria.

The Technology Steward shall continuously monitor dependent platforms for new capabilities, deprecations, API changes, and opportunities to simplify or retire custom Jason functionality.

## 18. Exceptions

Exceptions require:

- written justification;
- identified risk;
- compensating controls;
- named approver;
- expiration or review date;
- evidence record;
- retirement plan.

Convenience, speed, or temporary implementation pressure alone is not sufficient justification for bypassing this specification.
