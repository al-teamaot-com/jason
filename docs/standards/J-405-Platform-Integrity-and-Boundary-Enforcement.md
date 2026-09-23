# J-405 — Platform Integrity and Boundary Enforcement

**Version:** 0.1  
**Status:** Proposed — effective when merged into the authoritative development branch  
**Owner:** Jason Architecture Authority  
**Authority:** Jason Constitution; J-100 Reference Architecture; J-404 Documentation Governance and Continuity  
**Scope:** Platform integrity, approved boundaries, prohibited bypasses, provider isolation, secrets handling, cross-client separation, and production-readiness enforcement  
**Canonical source:** Yes — governed engineering/platform-integrity standard  
**Historical source:** `docs/archive/governance/ARTICLE_VII_PLATFORM_INTEGRITY-Historical.md`

## Purpose

Jason shall operate as one governed platform rather than as a collection of independently authoritative applications, agents, connectors, or services.

This standard translates durable platform-integrity requirements from the historical Platform Integrity constitutional record into an enforceable standard beneath the current Jason Constitution. It does not create a new constitutional article and does not alter constitutional numbering.

## Constitutional basis

This standard implements and makes operational the current Constitution's requirements for:

- provider and implementation independence;
- integration before innovation;
- separation of responsibilities;
- central orchestration;
- auditability;
- stewardship;
- institutional memory;
- modularity and reversibility;
- trust; and
- authoritative operational state.

The Constitution remains higher authority. If this standard conflicts with the Constitution, the Constitution governs and this standard must be reconciled.

## Platform authority boundary

Jason's governed platform contracts own the boundaries for identity, authentication, authorization, secrets access, policy/governance evaluation, orchestration, event/evidence handling, capability/provider registration, configuration/state management, and other shared platform concerns assigned by canonical architecture.

A component, connector, capability implementation, model, agent, or external provider shall not silently duplicate, replace, bypass, or widen those responsibilities.

## Approved platform contracts

Material component-to-component interaction shall use approved, documented, versioned interfaces or capabilities appropriate to the boundary being crossed.

An implementation convenience is not sufficient reason to bypass a governed platform service.

Where a required platform boundary does not yet expose an adequate capability, the deficiency shall be addressed through normal architecture/governance work or through a formally approved, time-bounded exception. It shall not be solved by creating an undocumented side path.

## Prohibited bypasses

Unless an explicitly governed exception applies, the following are prohibited:

- direct agent-to-agent invocation or communication;
- coordination that bypasses the Central Orchestrator;
- service-to-service authentication using shared credentials when identity-specific workload authentication is available or required;
- direct retrieval of secrets from a vault/provider when an approved Jason secrets-broker capability owns that access path;
- policy or business-authority decisions embedded in provider connectors or implementation-specific adapters;
- undocumented APIs, hidden execution paths, or unregistered consequential capabilities;
- direct writes to another component's private datastore outside an approved contract;
- hard-coded credentials or secret material;
- secret values in prompts, logs, events, evidence, documentation, source control, or handoff material;
- uncontrolled copying of large artifacts or evidence between components when governed central storage/reference transfer is available;
- direct vendor API use that bypasses the approved Jason provider/capability boundary for that operation;
- cross-client transfer of context, evidence, credentials, or data without explicit authority and enforced separation; and
- silent repair or reconfiguration of production drift outside Jason's governed orchestration, approval, execution, verification, and audit path.

Provider implementations may of course call their external provider APIs as part of an approved capability/provider boundary. The prohibition is on callers bypassing that governed boundary, not on the provider implementation performing its assigned work.

## Central orchestration

Agents shall never invoke or communicate with other agents directly.

Agents may return structured results to the Central Orchestrator or request a named capability from it. The Central Orchestrator remains responsible for governed routing, permission enforcement, context transfer/minimization, policy gates, approvals, retries, timeouts, escalation, correlation, audit/evidence coordination, and final response assembly.

No connector, model, agent, or workflow may claim parallel orchestration authority merely because it has technical access to another system.

## Capability-based architecture

Platform functions shall be represented through stable named capabilities and governed resource/provider abstractions rather than implementation-specific calls whenever practical.

Consumers request intent. Governed resolution determines the eligible implementation.

A provider is an implementation of a capability, not the definition of that capability.

Provider-specific features may be exposed when justified, but they shall remain behind explicit governed boundaries and shall not create unnecessary lock-in or redefine Jason's provider-neutral architecture.

## Secrets and workload identity

Secrets shall be obtained only through approved secret-management boundaries and shall be represented in architecture, System Registry state, documentation, and audit evidence by governed references rather than secret values.

Shared long-lived credentials between Jason services should be avoided. Workload identity shall be specific, attributable, least-privileged, and replaceable where the supported platform permits it.

A component shall not broaden secret access merely to simplify integration or testing.

## Policy and business authority separation

Provider connectors and adapters shall implement provider mechanics, normalization, transport, and bounded provider-specific behavior. They shall not independently define business policy, human authority, client scope, approval sufficiency, or governance outcomes.

Technical access never creates business authority.

Policy and authority decisions shall be made through the governed identity, policy, approval, and orchestration layers designated by canonical architecture.

## Data, evidence, and client separation

Cross-client isolation is mandatory across context, evidence, credentials, provider responses, cached state, logs, model inputs/outputs, and operational artifacts.

Large evidence/artifacts should be stored centrally and passed by governed immutable reference rather than repeatedly copied through agents or components.

Evidence provenance and historical integrity shall be preserved. A lower-level component may collect evidence but may not rewrite historical evidence to make a later outcome appear compliant.

## Integrate before innovate

Before creating a custom component, connector behavior, workflow-specific service, or capability, Jason shall evaluate whether an approved existing platform already provides the required function.

Every custom component or capability shall have, as applicable:

- a documented business justification;
- a record of why an existing approved capability is insufficient;
- a named steward or maintenance owner;
- a review interval or review trigger; and
- retirement/replacement criteria.

The Technology Steward role shall monitor core dependent platforms for new capabilities, deprecations, API/security changes, and opportunities to simplify or retire Jason-specific implementation.

## Exception governance

A temporary bypass of a platform-integrity rule requires explicit approval under Jason's normal authority and governance model.

The exception record must identify:

- the exact requirement being excepted;
- business/technical justification;
- affected clients, systems, and capabilities;
- risk and compensating controls;
- approving authority;
- start and expiration/review date;
- evidence and audit requirements; and
- retirement/remediation criteria.

An exception shall not silently become the permanent architecture.

## Production-readiness enforcement

A component or capability that cannot demonstrate compliance with its applicable platform-integrity boundaries shall not be promoted as production-ready.

Material violations may require one or more governed responses, including:

- denied execution;
- capability/provider suspension or quarantine;
- removal from eligible provider/capability resolution;
- rollback;
- incident or architectural review;
- corrective action; or
- retirement/replacement of the offending implementation.

Such enforcement remains subject to identity, authority, policy, orchestration, evidence, and audit controls. This standard does not itself authorize an automated remediation action.

## Verification expectations

Platform-integrity verification should be expressed through deterministic tests, policy checks, capability/provider metadata, System Registry verification, deployment controls, static analysis, runtime evidence, and bounded operational proofs where appropriate.

At minimum, applicable verification should be capable of detecting:

- direct coordination paths outside Central Orchestrator;
- unregistered or undocumented consequential execution paths;
- secret leakage or hard-coded credentials;
- provider/business-policy coupling;
- cross-client boundary violations;
- unauthorized datastore or external-provider bypasses;
- missing exception expiry/retirement criteria; and
- production state that is asserted without registered verification evidence.

## Historical reconciliation

This standard supersedes the normative platform-integrity role previously claimed by the historical file named `ARTICLE_VII_PLATFORM_INTEGRITY.md`.

That historical record is retained under `docs/archive/governance/` as institutional evidence of the earlier approved intent. Its original label as “Article VII” is not part of the current Constitution and must not be used to renumber or reinterpret `docs/foundation/J-002-Constitution.md`.

The durable requirements were preserved here at the correct authority layer rather than silently discarded or forced into an incorrect constitutional article number.

## Change and retirement

Changes to this standard shall follow Jason's normal architecture/governance/documentation process and must remain consistent with the Constitution.

This standard may be superseded if its requirements are later incorporated into a clearer canonical governance/architecture owner, provided no durable platform-integrity requirement is lost and the historical reconciliation remains traceable.
