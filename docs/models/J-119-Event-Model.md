# J-119 — Event Model

**Status:** Approved Foundation Model  
**Artifact Type:** Canonical Model  
**Owner:** Jason Architecture Authority  
**Applies To:** Every governed occurrence, observation, action, communication, state change, relationship change, provider signal, and audit-producing capability in Jason

## 1. Purpose

The Event Model defines how Jason represents that something happened.

A canonical Jason event is a provider-neutral occurrence record. A webhook, audit entry, log line, ticket update, alert, orchestration record, or provider message may provide evidence that an event occurred, but none of those source records automatically becomes the canonical business event.

Jason must be able to answer:

1. What happened?
2. When did it happen, and how certain is that time?
3. When and how did Jason learn about it?
4. Who or what acted, observed, or was affected?
5. Which organization, tenant, object, state, relationship, or capability does it concern?
6. What evidence supports the occurrence?
7. How strongly is the occurrence verified?
8. Which governed relationships connect it to other events or objects?
9. Was an authority-related action merely observed, or was valid authority independently established?
10. Can the event be relied upon for reasoning without violating tenant, policy, evidence, or execution boundaries?

## 2. Scope

This model defines:

- the distinction between source observations/evidence and canonical events;
- the common canonical event record;
- event identity, organization context, participants, subjects, timing, provenance, classification, verification, and evidence;
- occurrence, observation, ingestion, and recording time;
- event classes for occurrence meaning;
- state-change and relationship-change event semantics;
- event immutability, correction, and supersession;
- event-to-event linkage through J-118 relationships;
- cross-provider normalization;
- compatibility with J-116 State, J-117 Object, J-118 Relationship, J-120 Organizational models, ORCH-002 audit history, and INF-013 artifact/evidence references.

This model does not prescribe an event bus, queue, database, SIEM, stream processor, webhook framework, or storage provider.

## 3. Foundational Principles

### 3.1 Model the occurrence, not the source message

Provider-native messages remain source observations or evidence. Canonical promotion requires governed interpretation with preserved provenance.

### 3.2 Events do not replace canonical objects

J-117 remains authoritative for canonical objects such as Request, Decision, Approval, Evidence, Work Item, Incident, Change, Alert, Policy, and Capability.

J-119 records occurrences involving those objects. It does not create parallel Request, Decision, Approval, or Evidence object definitions.

### 3.3 Events are immutable in material meaning

A recorded event is not silently rewritten. Corrections, supersession, changed interpretation, and changed verification posture remain attributable and auditable.

### 3.4 Event time has multiple meanings

Occurrence time, observation time, ingestion time, and recording time are distinct concepts. Exact time must not be fabricated when the source only supports a range or approximate timestamp.

### 3.5 Observation is not proof

A source observation may remain reported, inferred, disputed, stale, or otherwise insufficient to establish a verified canonical event.

### 3.6 Events do not create authority

An event stating that an approval, administrative action, or change occurred does not independently prove that the actor possessed valid authority. Authority still resolves through identity, J-118 relationships, policy, scope, approval objects, and effective time.

### 3.7 Tenant boundaries remain authoritative

Shared infrastructure, correlated identifiers, provider links, or telemetry must never merge tenant context or grant cross-tenant access.

### 3.8 Evidence remains by reference

Large payloads, attachments, exports, transcripts, screenshots, reports, and raw provider bodies belong behind the INF-013 artifact/evidence boundary and are referenced from the event.

### 3.9 Relationships remain governed by J-118

Causation, correction, supersession, duplication, sequencing, containment, and consequence are relationships between events or other objects. J-118 remains authoritative for their governed meaning.

J-119 may carry correlation keys and relationship references, but it must not create a competing relationship model.

## 4. Common Canonical Event Record

Every material canonical event must support the following.

### 4.1 Required fields

- canonical event identifier;
- schema/model version;
- organization identifier;
- tenant or governed shared-context identifier;
- canonical event class;
- human-readable event meaning;
- `recorded_at`;
- source/provenance reference;
- recording capability or authority;
- verification state;
- classification/handling context.

### 4.2 Conditionally required fields

When available or materially relevant, the event must also support:

- canonical event subtype;
- actor or initiating principal;
- observing principal or capability;
- affected/subject object references;
- related canonical object references;
- related canonical relationship references;
- `occurred_at`;
- `observed_at`;
- `ingested_at`;
- time precision, uncertainty, or bounded occurrence interval;
- source provider/system;
- source resource/event/message identifier;
- source capability and operation;
- source correlation identifier;
- evidence/artifact references;
- normalization/transformation version;
- before-state and after-state references;
- policy, agreement, approval, or authority context;
- J-118 event-to-event relationship references.

Unknown values remain unknown. Implementations must not manufacture actors, objects, timestamps, authority, or causal links.

## 5. Canonical Event Classes

The canonical vocabulary is intentionally small.

### 5.1 Observation

Records that a condition, signal, fact, or claim was observed or reported.

Examples include monitoring detections, provider alerts, discovered resources, user reports, health observations, and model findings.

Observation does not itself establish truth.

### 5.2 Action

Records that an actor, capability, provider, or governed process attempted or performed an action.

Action subtypes may preserve attempted, started, completed, failed, denied, cancelled, rolled back, or verified meanings when operationally material.

An action involving a J-117 Request, Decision, Approval, Evidence, Change, Work Item, or other object references that object rather than redefining it.

### 5.3 State Change

Records a material transition in J-116 state for a governed object.

Lifecycle progression is represented through State Change rather than a separate top-level Lifecycle event class. J-116 remains authoritative for lifecycle, health, verification, attention, operational-condition, and execution-state meaning.

### 5.4 Relationship Change

Records a material occurrence involving a J-118 relationship, such as proposal, discovery, corroboration, verification, activation, dispute, suspension, revocation, expiration, correction, or supersession.

The relationship record remains authoritative for relationship meaning and current governed state.

### 5.5 Communication

Records a material communication occurrence such as a message, notification, acknowledgement, escalation, client-facing update, or response.

Communication content may reference J-117 Request, Decision, Approval, Knowledge, Evidence, Work Item, or other objects. Large message bodies and transcripts remain artifact/evidence references.

## 6. Source Observation Versus Canonical Event

Jason preserves two layers:

1. **Source observation/evidence** — what a provider, person, device, connector, model, or capability reported.
2. **Canonical event** — Jason's governed interpretation that a material business occurrence happened.

A source observation may remain unpromoted when:

- organization or tenant scope is ambiguous;
- canonical object identity cannot be resolved;
- evidence is incomplete;
- the source is untrusted, stale, or disputed;
- the observation duplicates a stronger existing occurrence;
- promotion would require unsupported inference.

Multiple source observations may support one canonical event. One source record may also contain multiple distinct business occurrences and therefore support multiple canonical events.

Promotion must preserve the original evidence reference and normalization path.

## 7. Event Verification

J-119 uses a compact event-specific epistemic vocabulary:

- **Reported** — a source asserts that the occurrence happened;
- **Inferred** — Jason derives the occurrence from indirect evidence;
- **Corroborated** — multiple independent or materially distinct evidence sources support the occurrence;
- **Verified** — sufficient authoritative evidence supports the occurrence for its governed use;
- **Disputed** — credible evidence conflicts with the occurrence or interpretation;
- **Rejected** — the occurrence or interpretation was evaluated and not accepted as canonical.

Correction and supersession are not verification states. They are governed J-118 relationships between records/events while the original event remains preserved.

Where no event verification can be established, implementations must represent that explicitly rather than treating absence of a value as verification.

## 8. Time Semantics

Canonical event time supports:

- `occurred_at` — best-supported occurrence time;
- `observed_at` — when a source detected or reported the occurrence;
- `ingested_at` — when Jason accepted the source observation into a governed boundary;
- `recorded_at` — when the canonical event was created.

When exact occurrence time is unavailable, the event may carry:

- earliest supported occurrence time;
- latest supported occurrence time;
- source precision;
- clock-skew or source-time uncertainty metadata.

Jason must not convert a low-precision or untrusted source timestamp into false precision.

## 9. State Changes

J-119 does not define state. J-116 does.

A State Change event should reference:

- the affected canonical object;
- the J-116 state dimension that changed;
- supported before-state and after-state values or references;
- actor or mechanism when known;
- evidence;
- authority context when intentional/governed;
- occurrence and observation times.

A state transition may be observed without its cause being known.

## 10. Relationship Changes and Event-to-Event Relationships

J-119 does not define relationship meaning. J-118 does.

Event-to-event concepts such as the following must be represented through governed J-118 relationships or governed subtypes of J-118 relationships:

- correlated with;
- preceded by / followed by;
- caused by / resulted in;
- part of / contains;
- duplicate of;
- corrects;
- supersedes.

Correlation identifiers may be stored directly for efficient grouping, but a correlation key is not proof of a canonical relationship and never proves causation.

## 11. Provider and Connector Mapping

Provider adapters may emit source observations using provider-native schemas internally. Promotion into canonical events occurs only through the Central Orchestrator or another explicitly governed normalization capability.

Examples:

- Microsoft audit activity may support Action, State Change, Relationship Change, or Communication events depending on business meaning;
- Datto RMM monitoring may begin as Observation and later support State Change if the condition is sufficiently verified;
- Autotask ticket history may support Communication, Action, or State Change events while Request, Decision, Approval, and Work Item remain J-117 objects;
- RocketCyber or other security findings begin as Observation unless separate governed criteria establish an Incident or another canonical object;
- IT Glue modifications may support Action and State Change events while Knowledge/Evidence objects remain governed separately.

Provider adapters must never communicate directly with other providers to establish event truth. Cross-provider corroboration is coordinated through the Central Orchestrator.

## 12. Orchestration Audit Events

ORCH-002 remains authoritative evidence of what the Central Orchestrator recorded about its own execution lifecycle.

An orchestration record is eligible for promotion into a canonical business event only when all of the following are true:

1. the record describes a material business occurrence, not merely internal plumbing;
2. organization/tenant context is resolved;
3. relevant canonical subjects can be identified;
4. provenance and original ORCH-002 evidence remain referenced;
5. promotion adds provider-neutral business meaning;
6. the resulting event does not overstate the external business outcome.

For example, `orchestration.capability.completed` proves that Jason recorded capability completion under its orchestration contract. It does not by itself prove that the external provider reached the desired business state.

## 13. Deduplication

Canonical deduplication must fail safe.

Two observations may be considered candidates for the same canonical occurrence only when a governed rule evaluates a combination of materially relevant evidence such as:

- organization/tenant;
- source event identity;
- canonical subject identity;
- canonical event class/subtype;
- occurrence-time window and source precision;
- provider correlation identifiers;
- event content fingerprint where appropriate.

No single shared identifier, timestamp, user, device, or correlation key is sufficient by itself to collapse events.

When uncertainty remains, preserve distinct records and relate them as possible duplicates rather than silently deleting or merging history.

## 14. Event Immutability and Correction

Material event records are append-only in meaning.

A correction must:

1. preserve the original event and evidence;
2. create the correcting event or governed record;
3. identify the correcting actor/capability and evidence;
4. establish an explicit J-118 `corrects` or `supersedes` relationship;
5. allow derived views to prefer the corrected interpretation without erasing historical reconstruction.

## 15. Security, Privacy, and Classification

Every implementation must preserve:

- organization and tenant isolation;
- least-privilege retrieval;
- classification and handling restrictions;
- purpose/policy restrictions when required;
- retention and evidence-preservation requirements;
- redaction/minimization for communication and analytics surfaces;
- secret references instead of secret values;
- fail-closed cross-tenant correlation unless explicitly governed and authorized.

## 16. Events and Execution Authority

Events are evidence and history, not autonomous permission.

No event by itself authorizes provider mutation, remediation, credential use, cross-tenant access, client communication, deletion, rollback, workflow replay, or retry.

Execution remains subject to identity, J-118 authority relationships, policy, capability registration, approvals, execution policy, current-state verification, and the Central Orchestrator.

## 17. Minimum Conformance Rules

An implementation conforms to J-119 only when it:

1. preserves organization and tenant context;
2. distinguishes source observations from canonical events;
3. preserves immutable canonical event identity;
4. uses J-117 objects rather than redefining Request, Decision, Approval, Evidence, or other canonical objects as event objects;
5. distinguishes occurrence, observation, ingestion, and recording time where applicable;
6. preserves provenance and evidence references;
7. does not manufacture actors, objects, timestamps, relationships, authority, or causal links;
8. uses J-116 for state meaning;
9. uses J-118 for relationship, causation, correction, supersession, duplication, and event-to-event linkage meaning;
10. preserves J-120 organization boundaries;
11. uses INF-013 references for large evidence payloads;
12. keeps material event history append-only;
13. uses the compact canonical event-class vocabulary unless a governed model revision establishes a new class;
14. does not treat an event as execution authority;
15. keeps provider-specific event names behind governed mapping boundaries;
16. preserves ORCH-002 as orchestration evidence rather than automatically promoting implementation history into business truth.

## 18. Approved Foundation Decision

J-119 is approved as the canonical Event Model foundation.

The architecture decisions are:

- Request, Decision, Approval, Evidence, and other business concepts remain J-117 objects; events record occurrences involving them.
- Lifecycle is not a separate top-level event class; lifecycle progression is represented through J-116 State Change.
- Canonical event classes are Observation, Action, State Change, Relationship Change, and Communication.
- Event verification uses Reported, Inferred, Corroborated, Verified, Disputed, and Rejected.
- Correction and supersession are J-118 relationships, not verification states.
- Event-to-event causation, sequence, containment, duplication, correction, and supersession are governed through J-118.
- Time uncertainty remains explicit and must not be converted into false precision.
- ORCH-002 records may be promoted only when they represent a material provider-neutral business occurrence and retain their original evidence reference.
- Deduplication must use governed multi-factor evidence and preserve separate records when confidence is insufficient.

J-119 is now suitable as an authoritative dependency for provider normalization, operational memory, cross-provider intelligence, evidence reasoning, and future governed automation.