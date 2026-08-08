# J-119 — Event Model

**Status:** Draft Foundation Model  
**Artifact Type:** Canonical Model  
**Owner:** Jason Architecture Authority  
**Applies To:** Every governed observation, occurrence, state change, action, decision, communication, alert, request, workflow, provider signal, and audit-producing capability in Jason

## 1. Purpose

The Event Model defines how Jason represents that something happened.

An event is not merely a log line, webhook, ticket update, alert, audit record, orchestration message, or provider notification. Those are sources that may report, describe, or provide evidence for an event. Jason needs a provider-neutral event model so it can reason consistently across Autotask, Datto RMM, IT Glue, Microsoft, security platforms, human activity, orchestration, and future capabilities without allowing any provider's schema to become the business model.

Jason must be able to answer:

1. What happened?
2. When did it happen?
3. When and how did Jason learn about it?
4. Who or what acted, observed, requested, decided, or was affected?
5. Which organization, tenant, object, relationship, state, or capability does it concern?
6. What evidence supports the event statement?
7. Is the event reported, inferred, corroborated, verified, disputed, corrected, or superseded?
8. What other events caused, preceded, followed, correlated with, or resulted from it?
9. Does the event describe authority, or merely record that an authority-related action was claimed or observed?
10. Can the event be trusted strongly enough to support a decision while preserving tenant, policy, and evidence boundaries?

## 2. Scope

This model defines:

- the distinction between a canonical Jason event and source evidence about an event;
- the minimum common event record;
- event identity, organization context, participants, subjects, timing, provenance, classification, verification, and evidence;
- occurrence time, observation time, ingestion time, and recording time;
- correlation, causation, sequence, and consequence semantics;
- state-change and relationship-change event semantics;
- event immutability and correction rules;
- cross-provider event normalization;
- event relationships to J-116 State, J-117 Object, J-118 Relationship, and J-120 Organizational models;
- compatibility with orchestration audit events and INF-013 artifact/evidence references;
- requirements for introducing new event classes and types.

This model does not prescribe an event bus, queue, database, stream processor, SIEM, webhook framework, or storage provider. Implementations may use different technologies when they preserve the canonical meaning and governance defined here.

## 3. Foundational Principles

### 3.1 Model the occurrence, not the provider message

A provider message is evidence that something may have happened. It is not automatically the canonical event.

Examples:

- a Datto RMM alert may report that a device crossed a threshold;
- a Microsoft audit record may report that an identity changed a setting;
- an Autotask ticket update may report that work status changed;
- an orchestration lifecycle record may report that Jason invoked a capability.

Each source retains its own evidence identity and provenance. Jason may normalize one or more source records into a canonical event only through a governed interpretation boundary.

### 3.2 Events are immutable occurrence records

Once recorded, the material assertion of an event must not be silently rewritten. New evidence may change confidence or interpretation, but corrections and supersession must remain visible and attributable.

If a previously recorded event is materially wrong, Jason records the correction through a new governed record and explicit relationship rather than erasing historical evidence.

### 3.3 Event time has multiple meanings

Jason must not collapse all timestamps into one field. At minimum it must distinguish when the occurrence happened from when it was observed or received.

### 3.4 Observation is not proof

A webhook, alert, log, user statement, API response, or model inference is a source observation. Jason must preserve the difference between reported evidence and a verified canonical fact.

### 3.5 Events do not create authority by themselves

An event stating that an approval occurred does not independently prove that the approving actor possessed valid authority. Authority must still resolve through J-118 relationships, identity, policy, scope, and effective time.

Likewise, observing that an administrator performed an action does not prove that the action was authorized.

### 3.6 Tenant and organization boundaries remain authoritative

Shared infrastructure, correlated identifiers, provider links, or cross-tenant telemetry must never cause events to merge organizational context or grant access across boundaries.

### 3.7 Evidence remains by reference

Large payloads, attachments, transcripts, provider exports, reports, screenshots, and raw event bodies should be stored through the INF-013 artifact/evidence boundary and referenced from the event record rather than copied into every event representation.

### 3.8 Use a small canonical vocabulary

Jason should maintain a bounded set of canonical event classes and allow governed subtypes. Provider-specific event names map into that vocabulary rather than multiplying the canonical model.

## 4. Canonical Event Record

Every material governed event must support the following concepts.

### 4.1 Identity and boundary

- canonical event identifier;
- schema/model version;
- organization identifier;
- tenant or environment context where applicable;
- canonical event class;
- canonical event type or governed subtype;
- human-readable event meaning.

### 4.2 Participants and subjects

- actor or initiating principal where known;
- observing principal or capability where relevant;
- affected or subject object identifiers;
- related organization, person, identity, asset, service, work item, agreement, policy, capability, or other canonical objects;
- related canonical relationship identifiers where the event concerns a relationship.

Unknown actors or subjects must remain explicitly unknown rather than fabricated from naming similarity or provider ownership.

### 4.3 Timing

- `occurred_at` — best supported time the business occurrence happened;
- `observed_at` — time a source or observer detected or reported it;
- `ingested_at` — time Jason accepted the source observation into a governed boundary;
- `recorded_at` — time the canonical event record was created;
- source timezone or timestamp precision where relevant;
- uncertainty or bounded time range when exact occurrence time is not known.

These timestamps may be identical, but implementations must not assume they are.

### 4.4 Provenance and evidence

- source provider or source system where applicable;
- source resource/reference identifier;
- source event/message identifier where available;
- source capability and operation;
- source correlation identifier;
- evidence/artifact references;
- transformation or normalization version;
- recording capability or authority;
- confidence and verification state;
- classification and handling restrictions.

### 4.5 Context and meaning

- current interpretation or event statement;
- relevant before-state and after-state references where applicable;
- relevant relationship references;
- related request, decision, approval, work item, incident, change, alert, communication, or workflow references;
- policy or agreement context when material;
- scope and limitations on the interpretation.

### 4.6 Correlation and consequence

- correlation identifiers;
- parent or containing event where applicable;
- causal predecessor where verified or explicitly claimed;
- resulting/consequence event references;
- sequence membership where order is material;
- superseding or corrective event references.

Correlation must not be represented as causation without evidence.

## 5. Canonical Event Classes

The canonical event vocabulary should remain small. Initial classes are:

### 5.1 Observation

Records that an object, condition, signal, fact, or claim was observed or reported.

Examples include monitoring detections, provider alerts, discovered resources, user reports, and health observations.

An Observation does not itself prove the observed condition is true.

### 5.2 Request

Records that a person, identity, organization, system, or governed capability expressed a request for work, information, approval, or change.

A Request event does not itself authorize execution.

### 5.3 Action

Records that an actor, provider, capability, or governed process performed or attempted an action.

Action subtypes must preserve attempted, started, completed, failed, denied, cancelled, and rolled-back meanings when they matter.

### 5.4 State Change

Records a material change between J-116 state representations for a governed object.

A State Change event should reference the affected object and the before/after state facts rather than inventing a parallel status model.

### 5.5 Relationship Change

Records creation, verification, activation, suspension, expiration, revocation, dispute, correction, or supersession of a J-118 relationship.

The event records that the relationship changed; the relationship record remains the canonical relationship authority.

### 5.6 Decision

Records that a governed decision was made, including approval, denial, escalation, exception, classification, or disposition.

A Decision event must identify the decision record or authority chain when the decision can affect execution rights, obligations, risk, or client impact.

### 5.7 Communication

Records a material communication occurrence such as a message, notification, acknowledgement, escalation, or client-facing update.

Message bodies and large transcripts should normally remain artifact/evidence references rather than duplicated event payloads.

### 5.8 Evidence

Records the creation, collection, verification, preservation, challenge, or retirement of evidence.

Evidence events do not replace the evidence artifact or evidence relationship itself.

### 5.9 Lifecycle

Records lifecycle progression for governed workflows, capabilities, jobs, cases, incidents, changes, or orchestration executions when that lifecycle is materially useful outside the source system.

Provider-specific workflow states must map to canonical lifecycle meaning rather than becoming new event classes.

## 6. Source Observation Versus Canonical Event

Jason must preserve two layers:

1. **Source observation/evidence** — what a provider, person, device, system, model, connector, or capability reported.
2. **Canonical event** — Jason's governed, provider-neutral interpretation that a material occurrence happened.

A source observation may remain unpromoted when:

- organization scope is ambiguous;
- object identity cannot be resolved;
- evidence is incomplete;
- the source is untrusted or disputed;
- the apparent event duplicates a stronger existing record;
- the interpretation would require unsupported inference.

Multiple source observations may support one canonical event. One provider record may also describe multiple business events and therefore yield more than one canonical event when the meanings are distinct.

Promotion must preserve the original evidence references and the transformation or interpretation path.

## 7. Event Verification

Event verification uses an epistemic dimension separate from the event's business class.

Initial verification states include:

- Unknown
- Reported
- Observed
- Inferred
- Corroborated
- Verified
- Disputed
- Rejected
- Corrected
- Superseded

A completed Action event may still be only Reported if the only evidence is a provider message. A historical event may remain Verified even after the affected object has moved through later states.

Verification changes must be attributable and auditable. They must not silently rewrite the original source evidence.

## 8. State Changes

J-119 does not define object state. J-116 does.

A State Change event should identify:

- the affected canonical object;
- the state dimension or dimensions that materially changed;
- before-state reference or supported prior value;
- after-state reference or supported resulting value;
- actor or mechanism causing the change when known;
- evidence for the change;
- authority context when the change was intentional and governed;
- occurrence and observation times.

An event may report a state change without proving causation. For example, an alert may show that a service became unavailable without proving what caused the outage.

## 9. Relationship Changes

J-119 does not define relationship meaning. J-118 does.

A Relationship Change event should reference the canonical relationship and describe the material occurrence, such as:

- relationship proposed;
- relationship discovered;
- relationship corroborated;
- relationship verified;
- relationship activated;
- relationship disputed;
- relationship suspended;
- relationship revoked;
- relationship expired;
- relationship superseded.

The event may provide historical sequencing and causation context, but the current governed relationship state belongs to J-118.

## 10. Correlation, Causation, and Sequence

Jason must distinguish:

- **correlated with** — events share meaningful context or identifiers;
- **preceded by / followed by** — temporal or ordered relationship;
- **caused by** — supported causal relationship;
- **resulted in** — supported consequence relationship;
- **part of** — event belongs to a broader incident, request, workflow, execution, or business occurrence;
- **duplicate of** — two observations or event records describe the same occurrence;
- **corrects / supersedes** — later governed record changes the accepted interpretation while preserving history.

A shared ticket ID, device ID, user identity, timestamp window, or correlation ID is not sufficient by itself to assert causation.

## 11. Provider and Connector Mapping

Provider adapters may emit source observations using provider-native schemas internally, but the Central Orchestrator and governed normalization capabilities control promotion into canonical events.

Examples:

- Microsoft audit activity may map to Action, State Change, Decision, or Relationship Change depending on business meaning.
- Datto RMM monitoring may map to Observation and later to State Change if the condition is verified.
- Autotask ticket history may map to Request, Communication, Action, State Change, or Decision.
- RocketCyber or other security findings may map initially to Observation, not automatically to Incident or verified compromise.
- IT Glue modifications may map to Action and State Change while the knowledge/document object remains governed separately.

Provider adapters must not communicate directly with other providers to establish event truth. Cross-provider corroboration is coordinated through the Central Orchestrator and governed capabilities.

## 12. Relationship to Orchestration Audit Events

ORCH-002 established a durable append-only orchestration event store. Those orchestration lifecycle records remain authoritative evidence of what the Central Orchestrator recorded about an execution.

They are not automatically the canonical business Event Model.

J-119 must allow a governed mapping where an orchestration event has material business meaning, while preserving separation between:

- orchestration implementation history;
- audit/evidence records;
- canonical business events.

For example, `orchestration.capability.completed` proves that Jason recorded a capability completion under its orchestration contract. It does not automatically prove that the external provider reached the intended business state. Provider-state evidence or subsequent verification may still be required.

## 13. Event Immutability and Correction

Material event records are append-only in meaning.

Corrections must:

1. identify the original event;
2. preserve the original record and evidence;
3. state what interpretation is being corrected;
4. identify the correcting authority or capability;
5. provide supporting evidence;
6. create an explicit `corrects` or `supersedes` relationship;
7. update derived views without erasing historical reconstruction.

This preserves evidence-before-assertion and allows Jason to explain what it believed, what changed, and why.

## 14. Security, Privacy, and Classification

Event records may contain operational metadata that is itself sensitive even when the large evidence payload is stored separately.

Every implementation must preserve:

- organization and tenant isolation;
- least-privilege retrieval;
- sensitivity/classification labels;
- purpose and policy restrictions where required;
- retention and evidence-preservation requirements;
- redaction or minimization for communication and analytics surfaces;
- prohibition on secret values in event metadata when a secret reference can be used instead.

Cross-tenant correlation must fail closed unless an explicit governed relationship and authority permit it.

## 15. Events and Execution Authority

Events are evidence and history, not autonomous permission.

No event may by itself authorize:

- a provider mutation;
- remediation;
- credential use;
- cross-tenant access;
- communication to a client;
- deletion;
- rollback;
- workflow replay;
- retry of an interrupted action.

Those decisions remain subject to identity, relationships, policy, capability registration, approvals, execution policy, current-state verification, and the Central Orchestrator.

## 16. Minimum Conformance Rules

An implementation conforms to J-119 only when it:

1. preserves organization/tenant context;
2. distinguishes provider/source observations from canonical events;
3. preserves immutable event identity;
4. distinguishes occurrence, observation, ingestion, and recording time where available;
5. records provenance and evidence references;
6. does not manufacture unknown actors, objects, relationships, or causal links;
7. distinguishes correlation from causation;
8. uses J-116 for state meaning rather than inventing a parallel status model;
9. uses J-118 for relationship meaning rather than embedding ad hoc links;
10. preserves J-120 organization boundaries;
11. uses artifact/evidence references for large payloads;
12. keeps event history append-only in material meaning;
13. makes corrections and supersession explicit;
14. does not treat an event as execution authority;
15. keeps provider-specific event names behind governed mapping boundaries.

## 17. Questions For Foundation Review

Before this model is promoted from Draft Foundation Model to Approved Foundation Model, the Architecture Authority should validate at least these questions:

1. Is `Evidence` best retained as an event class, or should evidence lifecycle occurrences be represented under Action/Lifecycle with evidence relationships?
2. Should `Lifecycle` remain a top-level class or be expressed entirely as State Change events?
3. Which event verification states should be canonical versus implementation-specific subtypes?
4. What minimum event fields are mandatory for every event versus conditionally required?
5. Should causal relationships be represented directly on the event record, exclusively through J-118 relationships, or both with J-118 remaining authoritative?
6. How should time uncertainty and provider clock skew be represented canonically?
7. Which orchestration lifecycle records should be eligible for promotion into business events, if any?
8. What deduplication rules are safe enough to prevent duplicate canonical events without suppressing distinct occurrences?

## 18. Current Decision

J-119 is the active canonical-model workstream.

The immediate objective is to review and refine this Draft Foundation Model until the event vocabulary, common event record, evidence boundary, time semantics, and relationship to orchestration are strong enough to become an approved dependency for future provider integration, cross-provider intelligence, operational memory, and governed automation.
