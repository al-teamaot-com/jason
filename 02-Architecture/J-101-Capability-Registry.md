# J-101 — Jason Capability Registry

## Purpose

This document defines the authoritative set of core capabilities Jason requires in order to operate. It defines what Jason must be able to do without prescribing any product, provider, platform, model, or implementation.

Capabilities are enduring architectural requirements. Implementations are replaceable and may provide one or more capabilities through governed connector contracts.

## Registry Rules

1. Every capability shall have a unique identifier.
2. Every implementation shall declare which capabilities it provides.
3. No implementation may redefine the purpose or controls of a capability.
4. Capability use shall be governed by Policy and recorded by Audit when significant.
5. Capabilities may depend on other capabilities, but implementations shall not communicate directly with one another outside Orchestration.
6. A capability may be added, changed, or retired only through architectural review.

## Core Capabilities

### CAP-001 — Reasoning

**Purpose:** Analyze information and produce structured conclusions, recommendations, classifications, or decisions.

**Consumers:** Orchestration and authorized Jason functions.

**Required controls:** Policy-governed, auditable, provider-independent, bounded by authorized context.

**Inputs:** Authorized context, task instructions, evidence, constraints.

**Outputs:** Structured result, recommendation, classification, explanation, or request for additional capability.

**Dependencies:** Context Management, Knowledge Retrieval, Policy Evaluation, Audit Recording.

**Status:** Required.

### CAP-002 — Orchestration

**Purpose:** Coordinate work, route capability requests, transfer authorized context, manage execution state, and assemble final results.

**Consumers:** All authorized Jason interactions.

**Required controls:** Central routing, permission enforcement, timeout handling, retry control, escalation, isolation, and auditability.

**Inputs:** Request, identity, context, policy result, capability requirements.

**Outputs:** Routed work, execution state, consolidated result, escalation, or controlled failure.

**Dependencies:** Identity Resolution, Policy Evaluation, Audit Recording, Monitoring.

**Status:** Required.

### CAP-003 — Identity Resolution

**Purpose:** Resolve people, organizations, systems, services, and acting principals into durable Jason identities.

**Consumers:** Orchestration, Policy, Audit, Communications, Approval.

**Required controls:** Source attribution, confidence indication, tenant separation, authorization boundaries, and ambiguity handling.

**Inputs:** Identity claims, identifiers, provider records, organizational context.

**Outputs:** Resolved identity, unresolved identity, candidate identities, or identity conflict.

**Dependencies:** External-System Interaction, Policy Evaluation, Audit Recording.

**Status:** Required.

### CAP-004 — Context Management

**Purpose:** Maintain and deliver the minimum authorized information required to perform work consistently.

**Consumers:** Orchestration and authorized capabilities.

**Required controls:** Least-context access, purpose limitation, tenant isolation, provenance, retention control, and expiration.

**Inputs:** Request context, identity context, prior state, policy constraints, referenced artifacts.

**Outputs:** Authorized context package, context reference, or context denial.

**Dependencies:** Identity Resolution, Policy Evaluation, Secure Storage, Audit Recording.

**Status:** Required.

### CAP-005 — Knowledge Retrieval

**Purpose:** Locate and return authoritative knowledge, evidence, records, and artifacts relevant to an authorized request.

**Consumers:** Reasoning, Orchestration, Policy, Communications, Reporting.

**Required controls:** Source attribution, access control, freshness indication, confidence handling, and tenant isolation.

**Inputs:** Query, identity, context, scope, source constraints.

**Outputs:** Knowledge result, evidence reference, source citation, or no-result determination.

**Dependencies:** Identity Resolution, Policy Evaluation, Secure Storage, External-System Interaction, Audit Recording.

**Status:** Required.

### CAP-006 — Policy Evaluation

**Purpose:** Determine whether a requested action, information use, or decision is permitted and what controls apply.

**Consumers:** All capabilities through Orchestration.

**Required controls:** Fail-closed behavior, explainable outcomes, versioned rules, conflict handling, approval routing, and auditability.

**Inputs:** Requested action, identity, context, applicable rules, risk, and scope.

**Outputs:** Allow, deny, require approval, require modification, or escalate.

**Dependencies:** Identity Resolution, Context Management, Knowledge Retrieval, Audit Recording.

**Status:** Required.

### CAP-007 — Approval

**Purpose:** Obtain and validate required human authorization before controlled actions proceed.

**Consumers:** Orchestration and Policy Evaluation.

**Required controls:** Approver verification, scope binding, expiration, non-reuse, separation of duties, and auditability.

**Inputs:** Approval request, proposed action, affected scope, required authority, expiration.

**Outputs:** Approved, denied, expired, withdrawn, or escalated.

**Dependencies:** Identity Resolution, Policy Evaluation, Communications, Audit Recording.

**Status:** Required.

### CAP-008 — Audit Recording

**Purpose:** Create durable records of significant requests, decisions, actions, approvals, failures, evidence, and outcomes.

**Consumers:** All Jason components through governed interfaces.

**Required controls:** Integrity, timestamps, identity attribution, correlation, retention, tamper evidence, and independent reviewability.

**Inputs:** Audit event, actor, action, policy result, evidence references, execution result.

**Outputs:** Durable audit record and correlation reference.

**Dependencies:** Identity Resolution, Secure Storage.

**Status:** Required.

### CAP-009 — Communication

**Purpose:** Exchange governed information with people and external systems.

**Consumers:** Orchestration, Approval, Monitoring, Reporting, authorized business functions.

**Required controls:** Recipient validation, channel authorization, content policy, tenant isolation, delivery tracking, and auditability.

**Inputs:** Message intent, recipients, content, context, delivery requirements.

**Outputs:** Delivered message, delivery status, response, or controlled failure.

**Dependencies:** Identity Resolution, Policy Evaluation, External-System Interaction, Audit Recording.

**Status:** Required.

### CAP-010 — Monitoring

**Purpose:** Observe the health, availability, performance, and policy state of Jason and its dependencies.

**Consumers:** Orchestration, Governance, Operations, Reporting.

**Required controls:** Health normalization, threshold governance, failure detection, alert suppression, escalation, and auditability.

**Inputs:** Health signals, execution telemetry, dependency status, policy state.

**Outputs:** Health state, alert, degradation notice, recovery notice, or escalation.

**Dependencies:** External-System Interaction, Communication, Audit Recording.

**Status:** Required.

### CAP-011 — Scheduling

**Purpose:** Initiate authorized work at a defined time, cadence, or governed condition.

**Consumers:** Orchestration and authorized business functions.

**Required controls:** Time-zone handling, recurrence control, authorization, cancellation, duplicate prevention, and auditability.

**Inputs:** Task reference, schedule, identity, scope, policy constraints.

**Outputs:** Scheduled execution request, schedule state, missed-run result, or cancellation.

**Dependencies:** Policy Evaluation, Orchestration, Audit Recording, Monitoring.

**Status:** Required.

### CAP-012 — Secure Storage

**Purpose:** Preserve Jason state, artifacts, evidence, configuration, and references with appropriate protection and lifecycle controls.

**Consumers:** Context Management, Knowledge Retrieval, Audit Recording, Orchestration, authorized capabilities.

**Required controls:** Access control, encryption, tenant isolation, integrity, backup, retention, deletion, recovery, and provenance.

**Inputs:** Data, artifact, metadata, owner, classification, retention requirements.

**Outputs:** Durable reference, retrieval result, version, or controlled failure.

**Dependencies:** Identity Resolution, Policy Evaluation, Audit Recording, Monitoring.

**Status:** Required.

### CAP-013 — External-System Interaction

**Purpose:** Read from and act upon external systems through governed, replaceable connector implementations.

**Consumers:** Orchestration and authorized capabilities.

**Required controls:** Connector contract compliance, authentication, least privilege, operation allowlists, rate handling, failure normalization, tenant isolation, and auditability.

**Inputs:** Capability request, target scope, authorized identity, parameters, policy result.

**Outputs:** Normalized result, external reference, controlled failure, or escalation.

**Dependencies:** Identity Resolution, Policy Evaluation, Audit Recording, Monitoring.

**Status:** Required.

## Capability Status Values

- **Required:** Every conforming Jason implementation must provide the capability.
- **Optional:** The capability may be provided without changing Jason's core identity.
- **Deprecated:** The capability remains temporarily supported but shall not be used for new work.
- **Retired:** The capability is no longer part of Jason.

## Conformance

A Jason implementation conforms to this registry only when:

1. Every required capability is available through an approved implementation.
2. Each implementation declares the capabilities it provides.
3. Capability requests are routed through Orchestration.
4. Policy is evaluated before controlled actions.
5. Significant capability use is recorded by Audit.
6. Failure of one implementation does not redefine the capability or bypass its controls.

## Definition of Completion

This registry is complete when it defines the minimum capabilities required for Jason to perform governed work while allowing all providers and implementations to remain replaceable.
