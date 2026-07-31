# Jason Deployment System

**Version:** 1.0  
**Status:** Foundational  
**Milestone:** 2 - Deployment Architecture  
**Owner:** Atlantic Office Technologies  
**Governance:** Project Jason Constitution, Architecture Blueprint, and approved governing policies

## 1. Purpose

The Jason Deployment System (JDS) defines how Jason is installed, upgraded, verified, promoted, rolled back, and audited.

OpenClaw or a similar conversational application may act as the operator interface, but it must not improvise deployment commands. Deployment work must be performed by approved, version-controlled, deterministic artifacts through a governed deployment capability.

## 2. Constitutional Deployment Doctrine

> Jason shall never be deployed by AI improvisation.

All deployments must originate from approved, version-controlled, deterministic deployment artifacts that are verifiable, repeatable, auditable, and reversible.

Additional rules:

1. Agents do not execute arbitrary privileged shell commands.
2. Agents request named deployment capabilities through central orchestration.
3. The deployment runner executes only approved workflows and artifacts.
4. Material changes require a deployment plan and risk-based approval.
5. A deployment is not complete until acceptance testing succeeds.
6. Failed required checks trigger a governed stop or rollback.
7. Every deployment produces an evidence package and audit record.
8. The same release artifact is promoted between environments; it is not rebuilt differently for each environment.

## 3. Architecture

```text
Human Approver
      |
      v
OpenClaw or Approved Operator Interface
      |
      v
Central Orchestrator
      |
      v
Jason Deployment API / Named Capability
      |
      v
Jason Deployment Runner
      |
      +-- Bootstrap
      +-- Preflight
      +-- Deployment Planner
      +-- Approval Gate
      +-- Apply
      +-- Migration Manager
      +-- Health Verification
      +-- Jason Acceptance Test
      +-- Evidence Collector
      +-- Rollback Manager
      |
      v
Approved Ubuntu Host and Jason Services
```

OpenClaw provides the conversational experience. The orchestrator controls routing, policy, authorization, context, approvals, evidence, retries, timeouts, escalation, and final reporting. The deployment runner performs deterministic system changes.

## 4. Separation of Authority

### 4.1 Operator Interface

OpenClaw or another approved interface may:

- request deployment status
- run approved preflight checks
- request a deployment plan
- request deployment of an approved release
- display proposed changes, risks, and evidence
- request approval from an authorized person
- request rollback through a named capability
- report acceptance-test and health results

It may not:

- invent deployment procedures
- execute unrestricted root commands
- modify deployment artifacts during execution
- bypass approval or policy gates
- select an unapproved release
- suppress failed checks or evidence

### 4.2 Deployment Runner

The deployment runner is a dedicated service account and controlled execution environment. It may execute only approved entry points, such as:

```text
/usr/local/bin/jason-bootstrap
/usr/local/bin/jason-plan
/usr/local/bin/jason-deploy
/usr/local/bin/jason-verify
/usr/local/bin/jason-rollback
/usr/local/bin/jason-status
```

Any sudo authorization must be limited to approved commands and arguments where practical. Unrestricted `sudo`, `sudo bash`, and arbitrary command execution are prohibited for the operator-facing agent.

### 4.3 Human Authority

Risk determines approval requirements. Production deployments, privileged changes, destructive migrations, security-control changes, and irreversible operations require explicit approval by an authorized human.

## 5. Deployment Technology Model

The initial preferred implementation is:

- **GitHub:** source, release history, review, and approved tags
- **Ansible:** declarative Ubuntu host configuration
- **Docker Compose or another approved container orchestrator:** Jason application services
- **Signed or checksum-verified release artifacts:** integrity and provenance
- **Dedicated secrets provider:** credentials and integration secrets
- **Central evidence and audit store:** deployment records and acceptance results
- **OpenClaw skill/capability:** governed operator interface

The shell layer should remain thin. Shell scripts may bootstrap prerequisites and invoke declarative tooling, but must not become an opaque monolithic installer.

## 6. Repository Structure

Recommended structure:

```text
jason/
|-- deploy/
|   |-- bootstrap.sh
|   |-- preflight.sh
|   |-- plan.sh
|   |-- deploy.sh
|   |-- verify.sh
|   |-- rollback.sh
|   `-- uninstall.sh
|-- ansible/
|   |-- inventory/
|   |-- playbooks/
|   `-- roles/
|-- compose/
|   |-- compose.yaml
|   `-- compose.production.yaml
|-- config/
|   |-- defaults.yaml
|   |-- schemas/
|   `-- policy/
|-- migrations/
|-- acceptance/
|-- tests/
`-- releases/
```

## 7. Deployment Lifecycle

### 7.1 Bootstrap

Bootstrap prepares a supported Ubuntu host and installs only the approved foundational prerequisites.

Typical bootstrap activities:

- validate supported Ubuntu release
- install Git and approved package dependencies
- install and configure the container runtime
- install Ansible or the approved configuration engine
- create the Jason service account and groups
- create controlled directories
- configure logging and time synchronization
- install certificate trust and secret-provider client
- install the deployment runner entry points
- register deployment status and audit endpoints

Bootstrap must not grant production integration permissions or silently configure client systems.

### 7.2 Preflight

Before any material change, JDS validates:

- operating-system support
- CPU, memory, storage, and filesystem capacity
- DNS, time, and network health
- OpenClaw or operator-interface health
- container runtime health
- required port availability
- release authenticity and integrity
- required secrets and certificates
- compatibility with the installed Jason version
- backup or snapshot readiness
- migration and rollback availability
- policy and approval requirements

Preflight is read-only unless an explicitly approved repair capability is invoked.

### 7.3 Deployment Plan

The planner produces a human-readable and machine-readable plan containing:

- release and source commit
- target environment and host
- services to add, update, restart, or remove
- configuration changes
- database migrations
- expected downtime
- integration and permission changes
- risk classification
- approval requirements
- rollback method
- verification tests
- unresolved warnings or blockers

No material deployment begins without an approved plan.

### 7.4 Approval

The governance engine verifies that the approver has authority for the target environment and risk level. Approval records include identity, timestamp, plan digest, release digest, scope, conditions, and expiration.

Approval of one plan does not authorize a materially changed plan.

### 7.5 Apply

The deployment runner performs only the actions contained in the approved plan. Typical actions include:

- applying host configuration through Ansible
- retrieving approved container images
- validating signatures or checksums
- applying environment-specific configuration
- starting infrastructure dependencies
- applying governed database migrations
- starting or updating Jason services
- registering approved capabilities with OpenClaw
- enabling logging, metrics, and health checks

### 7.6 Verification

Verification confirms more than process or container status. It must validate service behavior, policy enforcement, event flow, evidence recording, integration boundaries, and security assumptions.

### 7.7 Acceptance

A release is accepted only when all required Jason Acceptance Test checks pass or an authorized exception is documented and approved.

### 7.8 Evidence and Closure

JDS records:

- approved plan
- approver and authority
- release and artifact digests
- exact runner version
- host and environment
- start and end times
- commands or playbooks invoked
- configuration and migration results
- health and acceptance-test results
- warnings, exceptions, retries, and rollback activity
- final disposition

## 8. Jason Acceptance Test

The Jason Acceptance Test (JAT) proves that a deployment is operational and governed.

Initial required tests:

1. Central orchestration accepts and completes a synthetic request.
2. The governance engine blocks an unauthorized action.
3. An authorized low-risk test action follows the expected approval policy.
4. An audit event can be written and retrieved.
5. Evidence can be stored and referenced.
6. The Model Gateway can route a test request to an approved model or approved mock.
7. Decision Memory is reachable and enforces its trust rules.
8. The event bus publishes and delivers a synthetic event.
9. Operations Intelligence receives test metrics.
10. Development integrations use mocks or read-only permissions unless separately approved.
11. No unexpected privileged process, open port, or outbound connection is detected.
12. Rollback readiness is confirmed.

JAT results become part of the permanent deployment evidence package.

## 9. Release Promotion

The standard promotion path is:

```text
Development -> Test -> Pilot -> Production
```

Promotion rules:

- the release artifact remains identical between environments
- environment configuration is separate, versioned, validated, and access controlled
- required test evidence follows the release
- each promotion has an environment-specific plan and approval
- unresolved production blockers prevent promotion
- Pilot scope must be explicit and reversible

## 10. Rollback

Rollback is a first-class deployment capability, not an afterthought.

A rollback plan must define:

- previous known-good release
- compatible configuration
- data and schema compatibility
- migration reversal or restoration method
- workflow quiescing procedure
- integration safety state
- verification steps after restoration

On a qualifying failure, JDS should:

1. stop new workflow execution safely
2. preserve failure evidence
3. restore the previous approved application release
4. restore compatible configuration and data where required
5. rerun health and acceptance checks
6. notify the operator and approver
7. create an auditable incident or change record

A rollback must never erase the evidence of the failed deployment.

## 11. Upgrades

An upgrade follows the same governed lifecycle as a first deployment:

1. verify approved release
2. assess compatibility
3. produce deployment plan
4. identify migrations and risk
5. obtain required approval
6. deploy deterministically
7. run verification and JAT
8. promote or roll back
9. preserve evidence

The conversational instruction may be simple:

> Deploy approved Jason release 3.1 to Development.

The implementation must remain deterministic and policy controlled.

## 12. Named Deployment Capabilities

Initial capability contract:

```text
jason.deployment.status
jason.deployment.preflight
jason.deployment.plan
jason.deployment.apply
jason.deployment.verify
jason.deployment.rollback
jason.deployment.evidence.get
```

Example request:

```json
{
  "capability": "jason.deployment.apply",
  "environment": "development",
  "release": "v0.1.0",
  "change_ticket": null,
  "approval_required": true
}
```

Agents may request these capabilities but may not directly invoke one another or bypass central orchestration.

## 13. Initial Implementation Sequence

The first practical build should proceed in this order:

1. Define supported Ubuntu baseline and host requirements.
2. Create the deployment service account and restricted command model.
3. Build a reviewed bootstrap script.
4. Create Ansible roles for deterministic host configuration.
5. Create the initial Docker Compose service layout.
6. Implement preflight and deployment-plan generation.
7. Implement release checksum or signature validation.
8. Implement health verification and the first JAT suite.
9. Implement evidence-package generation.
10. Implement rollback to a previous known-good release.
11. Expose deployment operations as named orchestrator capabilities.
12. Add the OpenClaw operator skill only after the runner is functional and tested.
13. Add GitHub Actions later for packaging, testing, signing, and release publication.

## 14. Architecture Review Requirements

Before JDS implementation is promoted beyond development, the Jason Architecture Review Board or designated governing authority must approve:

- deployment threat model
- trust boundaries
- service-account and sudo design
- secrets handling
- release integrity controls
- migration policy
- rollback guarantees and limitations
- evidence retention
- environment separation
- production approval roles
- disaster-recovery procedure
- retirement criteria for custom deployment components

## 15. Success Criteria

JDS is successful when:

- a clean supported Ubuntu host can be deployed reproducibly
- repeated deployment of the same release is idempotent
- unauthorized deployment actions are blocked
- every production change has an approved plan and evidence
- acceptance tests reliably detect unhealthy deployments
- a known-good release can be restored within the approved recovery objective
- operator convenience does not require unrestricted agent privileges
- deployment complexity remains understandable and maintainable

## 16. Milestone Declaration

This document establishes **Milestone 2: Deployment Architecture** for Project Jason.

From this milestone forward, every Jason capability must have a defined, governed path from approved source to deployed service. Deployment convenience may be conversational, but deployment execution must remain deterministic, controlled, verifiable, auditable, and reversible.
