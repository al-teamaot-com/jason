# Historical Record — Platform Integrity “Article VII”

**Status:** Historical / Superseded as governing authority  
**Original status:** Approved constitutional article  
**Original title:** Article VII - Platform Integrity  
**Superseded by:** `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` for durable platform-integrity requirements  
**Current constitutional authority:** `docs/foundation/J-002-Constitution.md`  
**Preservation purpose:** Institutional evidence of the earlier approved platform-integrity intent and its former constitutional labeling.

## Reconciliation note

The original record called itself “Article VII,” but the current authoritative J-002 Constitution defines Article VII as **Knowledge as an Asset**. The historical numbering is therefore not current constitutional authority.

The durable platform-integrity requirements from this record were deliberately reviewed and preserved in J-405 at the standards layer. This archive preserves the original text below without treating it as a current constitutional article.

---

# Article VII - Platform Integrity

Status: Approved constitutional article

## 1. Purpose

Jason shall operate as a governed platform rather than a collection of independent applications.

All components shall interact through approved platform contracts that preserve security, auditability, maintainability, provider independence, client separation, and replaceability.

## 2. Platform authority

The Jason platform provides the authoritative contracts for:

- identity;
- authentication;
- authorization;
- secrets access;
- governance;
- orchestration;
- event routing;
- evidence collection;
- service discovery;
- configuration management;
- capability registration.

Individual components shall not duplicate, undermine, or bypass these responsibilities.

## 3. Platform contracts

Every Jason component shall communicate through approved, documented, versioned platform interfaces.

No component shall bypass a platform service for convenience, speed, or implementation simplicity unless a time-limited constitutional exception is explicitly approved, evidenced, and assigned retirement criteria.

## 4. Prohibited bypass

The following are prohibited:

- direct agent-to-agent invocation or communication;
- service-to-service authentication using shared credentials;
- direct retrieval of secrets from a vault provider when an approved broker capability exists;
- policy decisions implemented outside the Governance Engine;
- undocumented APIs or hidden execution paths;
- direct writes to another component's datastore;
- hard-coded credentials;
- secret values in prompts, logs, events, evidence, or source control;
- business policy embedded in vendor connectors;
- uncontrolled transfer of large artifacts or evidence between components;
- direct vendor API calls that bypass an approved Jason capability;
- cross-client context, evidence, credentials, or data transfer without explicit authorization and enforced separation.

## 5. Central orchestration

Agents shall never invoke or communicate with other agents directly.

Agents may only:

- return structured results to the central orchestrator; or
- request a named capability from the central orchestrator.

The orchestrator is responsible for:

- routing;
- permission enforcement;
- context minimization and transfer;
- policy gates;
- human approvals;
- retries and timeouts;
- escalation;
- correlation;
- audit and evidence coordination;
- final response assembly.

Large artifacts and supporting evidence shall be stored centrally and passed by governed reference.

## 6. Capability-based architecture

Platform functions shall be represented by stable named capabilities rather than implementation-specific calls.

Examples include:

```text
identity.workload.authenticate
identity.authorization.resolve
secrets.secret.read
secrets.secret.rotate
governance.action.evaluate
evidence.record.create
events.event.publish
orchestration.capability.invoke
deployment.release.deploy
models.response.generate
```

Consumers request intent. The platform resolves implementation.

## 7. Provider independence

Jason shall depend on stable capability interfaces rather than vendor-specific implementations whenever practical.

External platforms may be replaced without requiring changes to Jason business logic.

This principle applies to, among others:

- secrets providers;
- AI model providers;
- databases;
- message brokers;
- monitoring platforms;
- PSA, RMM, documentation, identity, and cloud ecosystems.

Provider independence does not require lowest-common-denominator design. Provider-specific features may be exposed through adapters when their use is justified, governed, and does not create unnecessary lock-in.

## 8. Integrate before innovate

Jason shall continuously evaluate and leverage improvements in dependent platforms rather than accumulate unnecessary custom functionality.

Every custom component and capability shall document:

- its business justification;
- why an existing platform capability is insufficient;
- its review interval;
- its maintenance owner;
- its retirement or replacement criteria.

The Technology Steward shall monitor core platforms for new capabilities, deprecations, API changes, security changes, and opportunities to simplify Jason.

## 9. Constitutional supremacy

When an optimization conflicts with governance, security, auditability, provider independence, client separation, or another constitutional requirement, the Constitution shall prevail.

Performance, convenience, cost savings, or delivery speed shall not weaken constitutional guarantees without a formally approved exception and compensating controls.

## 10. Enforcement

A component that cannot prove compliance with this article shall not be considered production-ready.

Material violations shall result in one or more of the following:

- denied execution;
- quarantine;
- removal of capability registration;
- rollback;
- incident review;
- corrective action;
- retirement of the offending implementation.
