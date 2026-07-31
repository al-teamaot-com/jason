# Project Jason Architecture Blueprint

**Version:** 1.0  
**Status:** Foundational  
**Owner:** Atlantic Office Technologies  
**Governance:** Project Jason Constitution and approved governing policies

## 1. Mission

Project Jason is an AI-governed operations platform for Atlantic Office Technologies. It exists to improve service quality, consistency, security, efficiency, compliance, and client experience through trusted information, governed automation, institutional knowledge, and continuous operational improvement.

Jason assists people; it does not replace human accountability.

## 2. Prime Directive

> Improve Atlantic Office Technologies by enabling people to make better decisions through trusted information, governed automation, and continuous operational improvement.

## 3. Constitutional Principles

### 3.1 Constitution First

No capability may be implemented unless it complies with the Project Jason Constitution and approved governing policies.

### 3.2 Integrate Before Innovate

Jason shall prefer and leverage existing platform capabilities before creating custom functionality.

Priority order:

1. Autotask
2. IT Glue
3. Datto RMM
4. Microsoft platforms
5. Other approved vendor platforms and APIs
6. Custom Jason functionality

Custom capabilities must include a business justification, review interval, owner, and retirement criteria.

### 3.3 Central Orchestration

Agents must never invoke or communicate with other agents directly. All coordination must pass through the central orchestration layer.

The orchestrator owns:

- routing
- permissions
- context transfer
- policy gates
- approvals
- retries
- timeouts
- escalation
- audit logging
- final response assembly

Agents may only return structured results or request a named capability from the orchestrator. Large artifacts and evidence are stored centrally and passed by reference.

### 3.4 Human Authority

Risk determines required approval. Jason may observe, recommend, and perform approved low-risk actions, but accountable human authority remains in control.

### 3.5 Evidence Before Action

Recommendations require evidence. Automation requires verification. AI opinion alone is never sufficient justification for an operational action.

### 3.6 Data Before AI

Jason shall prefer, in order:

1. deterministic data
2. business and governance rules
3. verified historical evidence
4. Decision Memory
5. AI reasoning

### 3.7 Transparency and Auditability

Every material recommendation or action must be able to answer:

- What happened?
- Why did it happen?
- What evidence was used?
- Which policy applied?
- Who approved it?
- What action was taken?
- Was the outcome verified?
- Can the decision be reproduced?

### 3.8 Confidence and Uncertainty

Jason shall represent uncertainty explicitly. Unknown, missing, conflicting, and stale information must not be treated as verified fact.

### 3.9 Continuous Improvement

Jason continuously evaluates and improves documentation, monitoring, automation, workflows, AI usage, integrations, and operational practices.

### 3.10 Measurable Value

Every capability must improve at least one of the following:

- quality
- security
- cost
- efficiency
- client experience
- compliance
- dependability
- manageability
- expandability

A capability that no longer provides measurable value should be reviewed for retirement.

### 3.11 No Black Boxes

Every major subsystem shall expose its operational state through Operations Intelligence. No subsystem may operate as an unobservable black box.

### 3.12 Living Documentation

Jason shall compare documented state, observed state, and intended state; identify drift; measure confidence; recommend corrections; and preserve an auditable history of changes.

### 3.13 Client Context Over Universal Rules

Jason shall distinguish among:

- observed configuration
- recommended practice
- client-approved policy
- compliance requirements
- approved exceptions

Differences are not errors by default. They are governed decisions that must be documented, justified, approved where required, and periodically reviewed.

## 4. Operating Philosophy

### 4.1 People Before Technology

Technology exists to serve clients, employees, and business relationships.

### 4.2 Simplicity Over Complexity

Every feature creates maintenance obligations. Jason should simplify, reuse, and retire before expanding custom functionality.

### 4.3 Explainability

Jason must explain recommendations using evidence, policy, history, documentation, and business rules rather than asserting that an AI model decided.

### 4.4 Respect Existing Investments

Jason amplifies AOT's existing investments in Autotask, Datto RMM, IT Glue, Microsoft, Duo, RocketCyber, and other approved platforms.

### 4.5 Dependability, Manageability, Expandability

When tradeoffs are required, priorities are:

1. dependability
2. manageability
3. expandability

## 5. Architecture Overview

```text
                           Jason Constitution
                                   |
                      Governance - Policy - Audit
                                   |
        +--------------------------+--------------------------+
        |                                                     |
 Central Orchestration                               Operations Intelligence
        |                                                     |
        |                                            Dashboards and Reporting
        |
 +------+------+---------+---------+----------+----------+----------+
 |      |      |         |         |          |          |          |
Decision Model Platform Monitor   Usage     Knowledge Automation Compliance
Memory  Router Intel.   Intel.    Ledger    Steward   Engine     Engine
 |                 |       |         |          |          |
 +-----------------+-------+---------+----------+----------+
                           |
                 Evidence, Event, and Analytics Store
```

## 6. Core Services

### 6.1 Central Orchestration

Coordinates all workflows and enforces the no-agent-to-agent rule.

### 6.2 Governance and Policy Engine

Evaluates authority, permissions, risk, policy, client constraints, compliance requirements, and approval needs before execution.

### 6.3 Event Bus

All major subsystems publish standardized events so activity can be correlated, measured, audited, and visualized.

### 6.4 Evidence Store

Stores diagnostics, logs, outputs, approvals, verification artifacts, and references to large supporting evidence.

### 6.5 Operations Intelligence

Transforms events and metrics into actionable dashboards, reports, trends, alerts, and explanations. Dashboards consume the analytics layer rather than repeatedly querying production systems live.

### 6.6 Model Gateway and Policy Router

Agents request named capabilities rather than selecting providers or models. The router selects an approved model based on policy, risk, cost, availability, data sensitivity, and observed performance.

### 6.7 Model Usage Ledger

Records provider, model, workflow, client, ticket, tokens, reasoning usage, latency, retries, fallbacks, cost, success, and source authority for each AI invocation.

### 6.8 Decision Memory

Stores verified operational decisions, applicability conditions, approved actions, verification requirements, expiration, exclusions, ownership, and success history. It does not cache unverified AI responses.

### 6.9 Knowledge Steward

Maintains authoritative technical knowledge from vendor documentation, SDKs, release notes, KBs, approved examples, and other governed sources.

### 6.10 Platform Intelligence

Tracks vendor changes, known issues, deprecations, API changes, outages, and opportunities to simplify Jason by using new platform capabilities.

### 6.11 Monitor Intelligence

Evaluates monitoring quality, recurrence, false positives, technician effort, diagnostic quality, automation opportunities, operational cost, and risk value. It may recommend changes but shall not silently alter production monitoring.

### 6.12 Client Information Steward

Uses Autotask and IT Glue as primary systems of record while validating completeness, accuracy, freshness, confidence, ownership, and review dates. It identifies missing information and supports periodic confirmation without becoming a competing documentation platform.

### 6.13 Operational Knowledge Graph

Maintains governed relationships among clients, locations, users, devices, networks, applications, contracts, SLAs, policies, monitors, documentation, incidents, and business dependencies. Source values remain owned by their systems of record.

### 6.14 Technology Stewardship

A designated Technology Steward monitors dependent platforms for new capabilities, deprecations, API changes, security impacts, and opportunities to simplify or retire custom Jason components.

## 7. Major Functional Domains

- Service Operations
- Endpoint Operations
- Microsoft Operations
- Security Operations
- Compliance Operations
- Documentation Operations
- Client Governance
- Automation Operations
- Platform and Product Intelligence

## 8. Operations Intelligence and Dashboards

Initial dashboard families:

- Executive
- Service Manager
- Technician
- NOC and RMM Operations
- SOC and Security
- Compliance
- Client Health
- Documentation Health
- Client Information Steward
- AI Operations
- Model Usage and Cost
- Platform Health
- Monitor Health
- Automation Health
- Decision Memory

Each major subsystem must publish enough standardized state to answer:

1. What is happening?
2. Why is it happening?
3. What should be done about it?

Grafana or another approved existing platform should be preferred over creating a custom dashboard engine.

## 9. Data Ownership

| System | Authoritative ownership |
|---|---|
| Autotask | Companies, contacts, contracts, tickets, service records, business fields, and approved operational data already modeled there |
| IT Glue | Technical documentation, SOPs, flexible assets, diagrams, configurations, passwords, and structured client documentation |
| Datto RMM | Endpoint inventory, monitoring state, device telemetry, policies, jobs, and remediation execution |
| Microsoft | Identity, licensing, tenant configuration, messaging, collaboration, and security state exposed by approved APIs |
| Other vendor platforms | Live operational state they generate and authoritatively maintain |
| Jason | Governance, intelligence, evidence, metrics, confidence, relationships, derived knowledge, and verified Decision Memory |

Jason references systems of record and must not duplicate their authoritative data without an approved architectural exception.

## 10. Client Governance and Information Maintenance

Jason shall evaluate client information through three distinct lenses:

### 10.1 Existing Position

What is currently documented or observed in Autotask, IT Glue, Datto RMM, Microsoft, and other approved systems?

### 10.2 Recommended Baseline

What is recommended based on business type, operational needs, risk, insurance obligations, and applicable frameworks such as CMMC, NIST SP 800-171, HIPAA, FTC Safeguards Rule, CJIS, PCI DSS, or other requirements?

### 10.3 Client Decision

What has the client actually approved, including business justification, exceptions, compensating controls, approver, and review date?

A print shop and a DoD contractor may appropriately make different decisions. Jason's role is to provide context-aware recommendations and govern documented deviations, not enforce a universal one-size-fits-all configuration.

Client information maintenance should include:

- confirmation that required fields exist
- periodic review of whether needs have changed
- identification of unanswered governance questions
- source and confidence metadata
- owner and last-confirmed date
- next-review date
- conflict and drift detection
- targeted confirmation rather than oversized questionnaires

## 11. Decision Hierarchy

Every material decision follows this order:

1. Is there an applicable law, regulation, contract, constitutional rule, or approved policy?
2. Is there deterministic evidence?
3. Is there verified historical knowledge?
4. Is there an applicable Decision Memory entry?
5. Is AI reasoning necessary?
6. Is human approval required?
7. How will the outcome be verified?

## 12. Governed Automation Maturity

- **Level 0 - Observe:** collect and report
- **Level 1 - Recommend:** provide evidence-backed guidance
- **Level 2 - Low-risk automation:** execute pre-approved, reversible actions
- **Level 3 - Managed automation:** execute within defined policy and verification controls
- **Level 4 - Human approval:** require explicit authorization before execution

Jason earns autonomy through evidence, successful verification, auditability, and policy compliance.

## 13. Jason Autonomous Remediation Framework

1. Triage
2. Assisted remediation
3. Low-risk automation
4. Verification
5. Documentation
6. Client follow-up
7. Learning
8. Automation promotion

Remediation success, underlying condition health, and source-alert clearance must be tracked separately.

## 14. Architecture Review

Before a new major capability is accepted, the Jason Architecture Review Board or designated governing authority must answer:

1. Does the capability already exist in an approved platform?
2. Does it comply with the Constitution and governing policies?
3. What business problem does it solve?
4. What measurable value will it provide?
5. What evidence supports the need?
6. What are the security, privacy, compliance, and client-separation implications?
7. What data does it read, derive, or own?
8. Which systems of record does it integrate with?
9. Which Core Services does it use?
10. What approvals and authority levels apply?
11. How will success and failure be measured?
12. How will it be verified, rolled back, supported, reviewed, and retired?

## 15. Architecture-First Workflow

Before implementation of a major capability:

1. Confirm constitutional alignment.
2. Identify its location in the Architecture Blueprint.
3. Identify required Core Services and systems of record.
4. Define measurable business value.
5. Define governance, evidence, verification, rollback, review, and retirement requirements.

A capability that cannot answer these questions is not ready to be built.

## 16. Implementation Phases

### Phase 1 - Foundation

- Constitution
- governance and policy engine
- central orchestration
- event bus
- evidence store
- model gateway

### Phase 2 - Intelligence

- Decision Memory
- Model Usage Ledger
- Platform Intelligence
- Knowledge Steward
- Operational Knowledge Graph foundations

### Phase 3 - Operations Intelligence

- Datto RMM alert ingestion
- Monitor Intelligence
- Client Information Steward structure
- analytics store
- initial Grafana dashboards

### Phase 4 - Governed Autonomous Operations

- governed remediation
- verification
- rollback
- approval workflows
- automation promotion

### Phase 5 - Continuous Improvement

- predictive analytics
- monitor and workflow optimization
- client governance reviews
- technology stewardship
- capability retirement and simplification

## 17. Success Metrics

Jason is measured by business and operational outcomes, including:

- reduced ticket resolution time
- reduced repeat incidents
- fewer false-positive alerts
- improved documentation completeness and confidence
- increased automation success
- reduced avoidable AI cost
- improved client satisfaction
- improved technician satisfaction
- improved security and compliance posture
- increased platform dependability and manageability

AI activity volume is not itself a success metric.

## 18. Architectural Milestone

This document establishes **Milestone 1: Architectural Foundation** for Project Jason.

Future capabilities must conform to this blueprint, the Project Jason Constitution, and all approved governing policies. Changes to foundational principles must be versioned, reviewed, approved, and preserved in the repository history.