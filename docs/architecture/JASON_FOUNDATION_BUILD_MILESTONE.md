# Project Jason Milestone 3: Foundation Build

**Version:** 1.0  
**Status:** Approved  
**Owner:** Atlantic Office Technologies  
**Governance:** Project Jason Constitution, Architecture Blueprint, and Jason Deployment System

## 1. Milestone Declaration

This document establishes **Milestone 3: Foundation Build**.

Milestone 3 transitions Project Jason from architecture definition into governed implementation. The first objective is not to connect every AOT platform. The first objective is to establish a secure, deterministic, observable, and replaceable foundation on which all later services depend.

## 2. Provider Independence Principle

> Jason shall depend on stable capability interfaces rather than vendor-specific implementations whenever practical. External platforms may be replaced without requiring changes to Jason business logic. Every infrastructure dependency must have documented replacement criteria, migration procedures, review intervals, and retirement criteria.

This principle applies to secrets management, model providers, databases, dashboards, orchestration tools, messaging systems, and external integrations.

Provider independence does not mean creating abstractions without need. Jason shall introduce an abstraction when it protects governance, portability, continuity, security, or measurable operational value.

## 3. Initial Foundation Sequence

The approved implementation order is:

1. OpenClaw operator interface — already installed
2. Jason Deployment Runner
3. OpenBao
4. Jason Secrets Broker
5. Governance Engine
6. Event Bus
7. Evidence Store
8. Model Gateway and Policy Router
9. Operational integrations

No operational connector may receive production credentials until the Secrets Broker, governance controls, audit path, and verification process are functioning.

## 4. OpenBao Decision

OpenBao is approved as Jason's initial self-hosted secrets provider.

OpenBao is an implementation choice, not a permanent architectural dependency. Jason services shall not call OpenBao directly unless an approved exception exists. Services request secrets through the Jason Secrets Broker.

### 4.1 Initial OpenBao Functions

The development deployment shall provide:

- TLS-protected API access
- integrated storage
- KV version 2 secrets engine
- AppRole or another approved workload-authentication method
- least-privilege path policies
- audit logging
- backup and restore procedures
- controlled initialization and unseal procedures
- health and readiness checks

### 4.2 Initial Secret Boundaries

Recommended development paths:

```text
secret/jason/development/runtime/*
secret/jason/development/integrations/*
secret/jason/development/deployment/*
secret/jason/shared/certificates/*
```

Recommended workload identities:

```text
jason-deployer
jason-runtime
jason-secrets-broker
jason-autotask-connector
jason-itglue-connector
jason-datto-connector
jason-model-router
jason-backup
```

Each identity receives access only to the minimum paths and operations required for its approved purpose.

## 5. Jason Secrets Broker

The Jason Secrets Broker is the provider-neutral interface between Jason services and the configured secrets platform.

```text
Jason Service
     |
     v
Jason Secrets Broker
     |
     v
Secrets Provider Adapter
     |
     +-- OpenBao Adapter
     +-- Future Provider Adapter
```

The broker must not become a second vault. It shall not persist plaintext secret values in its database, logs, evidence records, event stream, Decision Memory, or caches beyond the minimum in-process lifetime required to fulfill an authorized request.

### 5.1 Provider-Neutral Contract

The initial interface shall support:

- authenticate workload
- read secret
- read secret metadata
- create or update secret through a separately governed capability
- rotate secret
- revoke leased credential
- health check
- provider migration verification

### 5.2 Secret References

Jason business logic shall use provider-neutral references such as:

```text
secret://jason/development/autotask/api-secret
```

Provider-specific paths are resolved inside the configured adapter.

### 5.3 Named Capabilities

Initial governed capabilities:

```text
jason.secrets.health
jason.secrets.read
jason.secrets.metadata
jason.secrets.write
jason.secrets.rotate
jason.secrets.revoke
jason.secrets.audit
jason.secrets.migrate
jason.secrets.verify-migration
jason.secrets.cutover
jason.secrets.rollback-provider
```

Read access and write access must never be implied by the same permission. Rotation, migration, provider cutover, and deletion require explicit governance and approval appropriate to their risk.

### 5.4 Audit Evidence

The broker may record:

- secret reference
- provider name
- provider version identifier
- requesting workload
- requesting capability
- business purpose
- request identifier
- policy decision
- timestamp
- result
- lease identifier
- expiration time

The broker must never record:

- plaintext secret values
- root tokens
- unseal keys
- complete authorization headers
- AppRole SecretIDs
- private keys unless the Evidence Store itself is explicitly designed and approved for encrypted key custody

## 6. Replaceability and Future Connectors

The Secrets Broker shall support adapters so that a future provider can be evaluated and introduced without rewriting Jason services.

Every provider adapter must implement the same conformance tests, including:

- authentication
- authorized read
- denied read
- metadata retrieval
- health reporting
- audit event generation
- credential revocation when supported
- timeout behavior
- unavailable-provider behavior
- migration verification

A future provider may replace OpenBao only after:

1. business and technical justification
2. security and licensing review
3. conformance testing
4. migration rehearsal
5. rollback validation
6. human approval
7. evidence capture
8. successful pilot cutover

## 7. Universal Jason Service Contract

Every new Jason component must:

- be deployable as an independently versioned container
- run as a non-root workload unless an approved exception exists
- expose `/health`
- expose `/ready`
- expose `/metrics`
- expose `/version`
- emit structured logs
- publish standardized audit and operational events
- accept configuration separately from code
- obtain secrets through the Secrets Broker
- support graceful shutdown
- define backup, restore, upgrade, rollback, and retirement procedures

## 8. Initial Repository Structure

The foundation build should establish:

```text
ansible/
compose/
config/
deploy/
docs/
services/
  secrets-broker/
  governance/
  event-bus/
  evidence-store/
sdk/
  python/
tests/
  acceptance/
  conformance/
scripts/
```

Initial deployment artifacts:

```text
deploy/bootstrap.sh
deploy/preflight.sh
deploy/deploy.sh
deploy/verify.sh
deploy/rollback.sh
compose/compose.dev.yaml
config/development.example.yaml
```

Files containing actual secret values are prohibited from the repository.

## 9. First Deployable Release

The first target release is **Jason v0.0.1 — Foundation Skeleton**.

It is complete only when it can demonstrate:

1. deterministic deployment to the development environment
2. OpenBao health and audit logging
3. Secrets Broker health and readiness
4. provider-neutral secret reference resolution
5. an authorized test secret read
6. a denied unauthorized secret read
7. no secret leakage in logs or evidence
8. governance allow and deny decisions
9. audit and evidence retrieval
10. OpenClaw invocation of `jason.status`
11. successful rollback to the preceding known-good state
12. completion of the Jason Acceptance Test

No production write integration is included in v0.0.1.

## 10. Build Controls

OpenClaw may initiate approved build and deployment capabilities, inspect status, and present evidence. It must not invent deployment commands or receive unrestricted root shell authority.

Deployment actions must use reviewed, version-controlled artifacts through the Jason Deployment Runner.

All early external integrations shall be mock, sandbox, or read-only unless a separately reviewed capability explicitly authorizes otherwise.

## 11. Immediate Work Plan

### Phase 0 — Readiness

- capture Ubuntu and OpenClaw inventory
- verify repository access
- verify container runtime
- identify development host storage and backup location
- reserve service names, ports, and internal DNS names
- define TLS certificate approach

### Phase 1 — Deployment Foundation

- create repository structure
- create deterministic preflight
- create deployment service accounts
- establish restricted command wrappers
- create development Compose definition
- create verification and rollback framework

### Phase 2 — OpenBao

- deploy OpenBao in development
- initialize and unseal through a documented ceremony
- enable audit logging
- configure KV v2
- define policies and workload identities
- test backup and restore

### Phase 3 — Secrets Broker

- implement provider-neutral interface
- implement OpenBao adapter
- implement governance hooks
- implement structured audit evidence
- create provider conformance tests
- verify that secret values never enter logs or persistent evidence

### Phase 4 — Acceptance

- connect OpenClaw to approved status and health capabilities
- run the Jason Acceptance Test
- capture deployment evidence
- approve or reject v0.0.1 promotion

## 12. Milestone Exit Criteria

Milestone 3 is complete when the Jason development foundation can be deployed, verified, audited, backed up, restored, and rolled back using approved deterministic artifacts, and when a future secrets provider can be introduced through the adapter contract without changing consuming service business logic.
