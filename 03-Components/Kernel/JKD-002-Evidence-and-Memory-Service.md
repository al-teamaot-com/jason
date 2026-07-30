# JKD-002 — Evidence and Memory Service

**Status:** Draft for implementation  
**Version:** 0.1  
**Project:** Jason Kernel  
**Owner:** Jason Architecture Authority  
**Depends On:** JKD-001 Identity and Authority Service  
**Initial Consumer:** CAP-001 Professional Ticket Investigation

## 1. Purpose

The Evidence and Memory Service preserves what Jason observed, what sources support those observations, what conclusions were reached, what actions followed, and what outcomes were verified.

Its purpose is not to store conversations indiscriminately. Its purpose is to preserve trustworthy organizational memory.

The service must keep the following concepts distinct:

- source material;
- evidence;
- observation;
- hypothesis;
- inference;
- decision;
- recommendation;
- action;
- outcome;
- reusable knowledge.

Jason must never present an inference as though it were source evidence, or convert repeated statements into truth merely because they appeared more than once.

## 2. Core principles

### 2.1 Evidence before inference

Material conclusions must be traceable to evidence. When evidence is incomplete, Jason must reduce confidence, identify what is missing, and recommend the smallest useful next collection step.

### 2.2 Evidence is immutable

Once accepted, evidence content is not edited in place. Corrections, redactions, translations, summaries, normalized representations, and superseding records are stored as separate governed objects linked to the original.

### 2.3 Provenance remains attached

Every material item must retain where it came from, when it was collected, who or what collected it, the client and tenant context, and how its integrity was assessed.

### 2.4 Memory is not conversation history

Jason preserves durable facts, decisions, outcomes, and lessons. Raw conversational content is retained only when required by policy, audit, evidence, or operational need.

### 2.5 Tenant boundaries are mandatory

No retrieval, correlation, summarization, learning, or model context assembly may cross client boundaries without explicit authority and policy.

### 2.6 Knowledge is earned

An observation does not become reusable knowledge merely because a model produced a plausible explanation. Knowledge requires governed validation, confidence, scope, provenance, and an identified review or retirement condition.

### 2.7 Progressive disclosure

The service may preserve complete evidence while returning only the minimum information required by the authorized audience and purpose.

## 3. Responsibilities

The Evidence and Memory Service is responsible for:

- accepting source material and evidence references;
- calculating and recording integrity metadata;
- storing immutable evidence records;
- preserving collection and provider provenance;
- enforcing client, tenant, classification, and handling boundaries;
- recording observations separately from interpretations;
- linking evidence to tickets, assets, events, hypotheses, decisions, recommendations, actions, and outcomes;
- preserving investigation history and decision lineage;
- retrieving relevant prior cases and knowledge within authorized scope;
- producing bounded context packages for reasoning;
- recording verified outcomes and learning candidates;
- promoting approved learning candidates into governed knowledge;
- supporting retention, legal hold, redaction, archival, and defensible deletion;
- creating auditable records of access and material changes.

It is not responsible for:

- authenticating requesters;
- deciding whether a requester has authority;
- performing connector actions;
- choosing the final technical recommendation;
- independently promoting knowledge without the required governance;
- allowing one agent to communicate directly with another agent;
- serving as an unrestricted enterprise search engine.

## 4. Memory layers

Version 0.1 defines five memory layers.

### 4.1 Evidence memory

Preserves source artifacts and collected facts.

Examples:

- ticket description;
- Autotask note;
- Datto RMM diagnostic output;
- SMART report;
- Microsoft audit record;
- configuration snapshot;
- email header;
- screenshot;
- technician-provided statement.

### 4.2 Case memory

Preserves the governed history of a specific investigation or work item.

Examples:

- observations;
- missing information;
- hypotheses;
- recommendation;
- approval;
- action;
- verification;
- final outcome.

### 4.3 Object memory

Preserves durable history associated with a canonical object such as a client, person, asset, service, policy, or connector.

Examples:

- device incident history;
- known site constraints;
- prior mailbox investigations;
- firmware history;
- ownership and relationship changes.

### 4.4 Knowledge memory

Preserves validated reusable knowledge whose relevance extends beyond one case.

Examples:

- a known failure pattern;
- a tested troubleshooting method;
- a client-specific operating constraint;
- a communication standard;
- a vendor limitation;
- a verified automation opportunity.

### 4.5 Institutional memory

Preserves why TeamAOT adopted, changed, or retired a standard, policy, capability, or architectural decision.

Examples:

- architecture decisions;
- capability retirement reasons;
- recurring operational lessons;
- platform changes that eliminated custom work;
- documented trade-offs and assumptions.

## 5. Canonical record types

Version 0.1 supports the following governed records:

- `source_artifact`
- `evidence_item`
- `observation`
- `hypothesis`
- `decision`
- `recommendation`
- `action_record`
- `outcome`
- `learning_candidate`
- `knowledge_item`
- `memory_link`
- `access_event`
- `retention_action`

These records may be stored in relational tables, object storage, or both, provided the complete governed meaning is preserved.

## 6. Source artifact

A source artifact is the original or provider-native material received by Jason.

```yaml
source_artifact:
  id: art_01JASON
  organization_id: org_aot
  client_id: client_example
  tenant_id: tenant_example

  source:
    provider: autotask
    connector_id: connector_autotask_primary
    external_type: ticket
    external_id: T20260730.0012
    source_uri: null

  content:
    media_type: application/json
    storage_reference: obj://evidence/client_example/art_01JASON
    byte_length: 18421
    encoding: utf-8

  integrity:
    algorithm: sha256
    hash: "..."
    collected_at: "2026-07-30T14:00:00Z"
    collected_by: idn_service_connector
    collection_method: api

  classification:
    sensitivity: confidential
    contains_personal_data: true
    contains_secrets: false

  lifecycle:
    state: active
    retention_policy_id: ret_operational_ticket
    legal_hold: false
```

The service should preserve provider-native content whenever practical. A normalized representation does not replace the original.

## 7. Evidence item

An evidence item is a governed assertion about relevant source material.

```yaml
evidence_item:
  id: evd_01JASON
  artifact_id: art_01JASON
  client_id: client_example

  evidence_type: diagnostic_result
  title: "Disk diagnostic result"
  summary: "SMART reports 14 pending sectors on physical disk 0."

  location:
    selector_type: json_path
    selector: "$.physical_disks[0].smart.pending_sector_count"

  provenance:
    observed_value: 14
    unit: sectors
    source_timestamp: "2026-07-30T13:56:18Z"
    extracted_at: "2026-07-30T14:00:04Z"
    extracted_by: capability.disk_diagnostic_parser

  integrity:
    source_hash: "..."
    extraction_version: "1.0"

  confidence: 0.99
  verification_state: corroborated
```

Evidence items may summarize or locate source content, but must always reference the source artifact or an approved external evidence reference.

## 8. Observation

An observation is a bounded statement derived directly from evidence without asserting root cause or broader meaning.

```yaml
observation:
  id: obs_01JASON
  case_id: case_01JASON
  client_id: client_example
  statement: "Physical disk 0 reports 14 pending sectors."
  confidence: 0.99
  verification_state: corroborated
  evidence_refs:
    - evd_01JASON
  observed_at: "2026-07-30T14:00:04Z"
  recorded_by: capability.ticket_investigation
```

Good observation:

> The latest successful backup completed 18 hours ago.

Not an observation:

> The backup system is unreliable.

The second statement is an interpretation and must be represented as a hypothesis, decision, or knowledge item depending on context.

## 9. Hypothesis

A hypothesis is a testable explanation for observed conditions.

```yaml
hypothesis:
  id: hyp_01JASON
  case_id: case_01JASON
  statement: "The SSD is beginning to fail."
  status: needs_more_evidence
  confidence: 0.82

  supporting_observations:
    - obs_01JASON

  contradicting_observations:
    - obs_chkdsk_clean

  proposed_tests:
    - "Collect vendor-specific SMART attributes."
    - "Run manufacturer diagnostic in read-only mode."

  created_by: reasoning_provider_01
  reasoning_model_version: "..."
  created_at: "2026-07-30T14:01:00Z"
```

Hypotheses must preserve supporting and contradicting evidence. Rejected hypotheses remain part of the case history.

## 10. Decision and recommendation

A decision records a governed conclusion. A recommendation proposes a next action. They must not be collapsed into one record.

```yaml
decision:
  id: dec_01JASON
  case_id: case_01JASON
  conclusion: "The disk has credible indicators of physical degradation."
  confidence: 0.91
  decisive_evidence:
    - evd_01JASON
    - evd_reallocated_count
  unresolved_uncertainty:
    - "Manufacturer diagnostic has not yet been completed."
  decided_by: capability.ticket_investigation
  authority_context_id: ctx_01JASON
```

```yaml
recommendation:
  id: rec_01JASON
  decision_id: dec_01JASON
  action: "Verify current backup and schedule SSD replacement."
  reason: "Pending and reallocated sectors indicate elevated failure risk."
  expected_outcome: "Reduce risk of unplanned device failure and data loss."
  confidence: 0.93
  risk: medium
  approval_required: true
  alternative_options:
    - "Run manufacturer diagnostic before replacement if operational timing requires additional confirmation."
```

## 11. Action and outcome

Actions and outcomes close the loop between advice and reality.

```yaml
action_record:
  id: act_01JASON
  recommendation_id: rec_01JASON
  action_type: schedule_replacement
  performed_by: idn_technician
  performed_at: "2026-07-31T15:10:00Z"
  authority_context_id: ctx_02JASON
  evidence_refs:
    - evd_backup_verified
```

```yaml
outcome:
  id: out_01JASON
  case_id: case_01JASON
  status: successful
  summary: "SSD replaced, operating system restored, and post-replacement diagnostics passed."
  verified_by: idn_technician
  verified_at: "2026-08-01T17:45:00Z"
  verification_evidence:
    - evd_post_replacement_smart
    - evd_backup_success
  residual_risk: low
```

A recommendation without a verified outcome must not be counted as a successful result.

## 12. Learning candidates and knowledge promotion

A completed case may produce a learning candidate.

```yaml
learning_candidate:
  id: learn_01JASON
  originating_case_id: case_01JASON
  proposed_scope: model_specific
  statement: "On device model X, pending-sector counts above zero should trigger backup verification and replacement assessment."
  supporting_cases:
    - case_01JASON
  confidence: 0.68
  status: proposed
  proposed_by: capability.ticket_investigation
  review_required: true
```

A learning candidate may become a knowledge item only after the applicable approval or validation process.

```yaml
knowledge_item:
  id: knw_01JASON
  title: "Pending-sector response for device model X"
  statement: "..."
  applicability:
    organization_id: org_aot
    client_id: null
    asset_models:
      - model_x
  confidence: high
  validation_state: approved
  supporting_evidence:
    - case_01JASON
    - case_02JASON
  owner: role_technology_steward
  effective_from: "2026-08-15T00:00:00Z"
  review_by: "2027-02-15T00:00:00Z"
  retirement_criteria: "Retire when manufacturer guidance or improved telemetry supersedes this response."
```

Version 0.1 must not permit a reasoning model to promote its own learning candidate directly into approved knowledge.

## 13. Memory links

Records are connected through governed relationships rather than copied repeatedly.

A memory link must include:

- source record;
- target record;
- canonical relationship type;
- client and tenant context;
- confidence;
- provenance;
- effective period;
- creating identity or capability;
- supporting authority where material.

Examples:

- evidence `provides evidence for` observation;
- observation `supports` hypothesis;
- decision `references` evidence;
- recommendation `results from` decision;
- action `implements` recommendation;
- outcome `verifies` action;
- knowledge `documents` a recurring pattern;
- knowledge `supersedes` prior knowledge.

Where the canonical Relationship Model does not yet contain a required relationship, the implementation should use a governed subtype of the closest canonical relationship and raise a model-review candidate rather than silently inventing a permanent canonical type.

## 14. Retrieval and context assembly

The service must support purpose-bound retrieval.

A retrieval request includes:

```yaml
memory_query:
  execution_context_id: ctx_01JASON
  purpose: ticket_investigation
  client_id: client_example
  case_id: case_01JASON
  target_objects:
    - asset_123
  requested_record_types:
    - evidence_item
    - observation
    - outcome
    - knowledge_item
  time_range:
    from: "2025-07-30T00:00:00Z"
    to: "2026-07-30T23:59:59Z"
  maximum_results: 50
  relevance_threshold: 0.70
```

The service must apply:

1. execution-context validation;
2. client and tenant filtering;
3. classification and need-to-know filtering;
4. purpose limitation;
5. time and object relevance;
6. confidence and verification-state filtering;
7. result-count and size limits;
8. redaction or summarization rules;
9. access logging.

Retrieval must return evidence references and concise summaries by default. Full artifacts are returned only when authorized and necessary.

## 15. Similar-case retrieval

Version 0.1 may support similar-case lookup using structured fields, tags, object relationships, and text search.

Vector or semantic retrieval may be added, but it must not bypass:

- tenant isolation;
- access policy;
- record classification;
- provenance;
- confidence;
- result explainability.

A semantic match is evidence of relevance, not evidence that two cases share the same cause.

Every similar-case result should identify why it was returned, such as:

- same device model;
- same diagnostic code;
- same observed condition;
- same client constraint;
- same provider event type;
- overlapping evidence pattern.

## 16. Context packages for reasoning

The service returns a bounded, structured context package rather than an unrestricted memory dump.

```yaml
reasoning_context_package:
  package_id: pkg_01JASON
  execution_context_id: ctx_01JASON
  client_id: client_example
  purpose: ticket_investigation

  current_case:
    ticket_summary: "..."
    observations:
      - obs_01JASON
    missing_information:
      - "Current backup status"

  prior_cases:
    - case_id: case_prior
      relevance_reason: "Same model and SMART pattern"
      outcome_summary: "Drive replaced after confirmed degradation"
      confidence: 0.88

  approved_knowledge:
    - knw_01JASON

  exclusions:
    - "Raw client email bodies omitted because they are not necessary for this investigation."

  generated_at: "..."
  expires_at: "..."
```

The package must identify included records, excluded categories, applied policy, and expiration.

## 17. Integrity and chain of custody

For evidence that may support security, compliance, legal, disciplinary, or high-impact operational decisions, the service must support:

- cryptographic content hashes;
- collection timestamps;
- collector identity;
- collection method and connector version;
- source-system identifiers;
- storage location;
- access history;
- redaction history;
- export history;
- legal hold state;
- superseding or correction links.

Version 0.1 does not require a formal forensic evidence platform. It does require enough provenance to determine whether an item is original, transformed, summarized, or manually supplied.

## 18. Classification and handling

Every source artifact and material record must have a classification.

Initial sensitivity values:

- `public`
- `internal`
- `confidential`
- `restricted`

Additional handling flags may include:

- personal data;
- protected health information;
- cardholder data;
- credentials or secrets;
- legal privilege;
- security incident data;
- client-confidential information;
- employee-confidential information.

The service must not place secrets, passwords, API tokens, private keys, or full authentication material into general reasoning context or logs.

When a secret is detected, the service should preserve only an approved secret-manager reference or a redacted evidence record unless policy explicitly requires protected retention.

## 19. Retention, redaction, and deletion

Retention is policy-driven and record-type specific.

The service must support:

- retention policy assignment;
- minimum and maximum retention periods;
- legal hold;
- client contractual requirements;
- regulatory requirements;
- source-system retention references;
- archival;
- redaction;
- defensible deletion;
- tombstone records proving that deletion occurred.

Deletion must not silently break decision lineage. When underlying content is lawfully deleted, the service may preserve a minimal non-sensitive tombstone containing identifiers, classification, deletion authority, date, and affected links.

Redaction creates a governed derivative. The original remains protected when retention policy requires it.

## 20. Initial APIs

### Register source artifact

```http
POST /v1/artifacts
```

### Register external evidence reference

```http
POST /v1/evidence-references
```

### Create evidence item

```http
POST /v1/evidence
```

### Record observation

```http
POST /v1/observations
```

### Record hypothesis

```http
POST /v1/hypotheses
```

### Record decision

```http
POST /v1/decisions
```

### Record recommendation

```http
POST /v1/recommendations
```

### Record action and outcome

```http
POST /v1/actions
POST /v1/outcomes
```

### Query memory

```http
POST /v1/memory/query
```

### Assemble reasoning context

```http
POST /v1/context-packages
```

### Propose learning candidate

```http
POST /v1/learning-candidates
```

### Approve, reject, or supersede knowledge

```http
POST /v1/knowledge/{knowledge_id}/decision
```

### Apply retention action

```http
POST /v1/retention-actions
```

All APIs require a valid execution context from JKD-001.

## 21. Events emitted

The service emits structured events through the orchestrator's event bus:

- `artifact.registered`
- `artifact.integrity_failed`
- `evidence.created`
- `observation.recorded`
- `hypothesis.created`
- `hypothesis.updated`
- `decision.recorded`
- `recommendation.recorded`
- `action.recorded`
- `outcome.verified`
- `learning_candidate.proposed`
- `knowledge.approved`
- `knowledge.rejected`
- `knowledge.superseded`
- `memory.accessed`
- `memory.access_denied`
- `retention.applied`
- `evidence.redacted`
- `evidence.deleted`
- `client_boundary.violation_attempted`

Events record what occurred. They do not independently authorize or perform operational actions.

## 22. Audit requirements

Every material write, retrieval, export, redaction, deletion, knowledge promotion, and policy override must record:

- actor identity;
- execution context;
- organization, client, and tenant;
- purpose;
- affected record identifiers;
- action performed;
- policy version;
- timestamp;
- correlation ID;
- approval reference where required;
- result and reason code.

Routine internal reads may be aggregated where policy permits, but access to restricted, security, legal, employee, or cross-scope records must remain individually attributable.

## 23. Version 0.1 storage

Use PostgreSQL for metadata and relationships.

Use S3-compatible object storage or a protected filesystem abstraction for larger immutable artifacts.

Minimum relational tables:

- `source_artifacts`
- `evidence_items`
- `observations`
- `hypotheses`
- `decisions`
- `recommendations`
- `action_records`
- `outcomes`
- `learning_candidates`
- `knowledge_items`
- `memory_links`
- `context_packages`
- `access_events`
- `retention_policies`
- `retention_actions`

Minimum object-storage requirements:

- client-scoped prefixes or buckets;
- encryption at rest;
- TLS in transit;
- immutable or versioned storage where appropriate;
- integrity verification;
- access through the service rather than direct reasoning-provider access.

SQLite and local filesystem storage may be used for a single-node prototype only when client isolation, backups, integrity, and migration paths are preserved.

## 24. Failure behavior

| Failure | Required behavior |
|---|---|
| Evidence source unavailable | Record the collection failure and return missing evidence; do not fabricate. |
| Hash mismatch | Quarantine the artifact, emit an integrity event, and prevent reliance until reviewed. |
| Duplicate artifact | Preserve one canonical artifact and link duplicate provider references when hashes and scope match. |
| Conflicting evidence | Preserve all credible evidence, expose the conflict, and reduce conclusion confidence. |
| Missing client context | Reject the request. |
| Cross-client reference | Reject, audit, and emit a boundary-violation event. |
| Database unavailable | Fail closed for writes and authoritative retrieval; preserve retryable intake references where safe. |
| Object storage unavailable | Do not claim the artifact was preserved; retain metadata as pending only if clearly marked incomplete. |
| Knowledge approval unavailable | Leave the learning candidate pending; do not promote it. |
| Retention policy ambiguity | Preserve the record and escalate rather than delete. |
| Context package too large | Apply progressive reduction, summarize authorized content, and identify exclusions. |

## 25. Minimum test suite

The first implementation is not complete until it passes these tests:

1. Original ticket content is stored or referenced with hash, provenance, timestamp, client, and source identifiers.
2. An observation cannot be created without at least one evidence reference unless explicitly marked as a reported statement.
3. A hypothesis remains distinct from evidence and records supporting and contradicting observations.
4. Editing an accepted evidence item creates a new version or correction record rather than changing the original.
5. A requester authorized for Client A cannot retrieve Client B evidence.
6. A reasoning provider receives only a bounded context package, not direct unrestricted storage access.
7. Similar-case retrieval identifies why each result was returned.
8. Conflicting evidence is preserved and exposed rather than silently resolved.
9. A recommendation records decision, evidence, confidence, risk, and approval requirements.
10. A completed action is not treated as successful until an outcome is verified.
11. A learning candidate cannot become approved knowledge without the required decision.
12. Superseding knowledge preserves the prior item and its historical applicability.
13. Restricted evidence is redacted or omitted for an audience lacking need-to-know.
14. Secrets detected in evidence are excluded from logs and general reasoning context.
15. Legal hold blocks deletion.
16. Retention deletion creates an attributable tombstone when required.
17. Hash mismatch prevents the artifact from supporting a material conclusion.
18. Every material read and write produces the required audit record.
19. A disabled or expired execution context is rejected.
20. CAP-001 can store a ticket, retrieve relevant evidence, record its investigation, and preserve the verified outcome end to end.

## 26. Definition of done

JKD-002 Version 0.1 is complete when:

- artifacts and evidence can be registered immutably;
- provenance and integrity are preserved;
- observations, hypotheses, decisions, recommendations, actions, and outcomes are distinct and linked;
- client and tenant boundaries are enforced;
- purpose-bound retrieval works;
- bounded context packages can be produced;
- approved knowledge is distinguishable from learning candidates;
- retention and redaction actions are governed and auditable;
- CAP-001 can use the service end to end;
- no reasoning provider receives direct unrestricted database or object-storage access.

## 27. Deliberately deferred

The following should not be built until working capabilities demonstrate a need:

- a universal enterprise knowledge graph;
- autonomous knowledge promotion;
- cross-client pattern learning from identifiable client data;
- generalized vector retrieval across every record type;
- model-generated retention decisions;
- blockchain evidence ledgers;
- full digital forensics case management;
- unrestricted conversation-memory ingestion;
- self-modifying knowledge governance;
- complex distributed storage before the single-node vertical slice requires it.

## 28. Immediate build sequence

1. Create the metadata schema and object-storage abstraction.
2. Implement artifact registration, hashing, provenance, and client scoping.
3. Implement evidence items and observations.
4. Implement case records for hypotheses, decisions, recommendations, actions, and outcomes.
5. Implement authorized memory query and bounded context assembly.
6. Implement learning candidates and manual knowledge approval.
7. Add retention, redaction, access auditing, and failure handling.
8. Connect JKD-001 and JKD-002 to CAP-001 Professional Ticket Investigation.

The next deliverable should be the concrete CAP-001 input/output contract and workflow state machine. That artifact will convert JKD-001 and JKD-002 from service specifications into the first implementable vertical slice.