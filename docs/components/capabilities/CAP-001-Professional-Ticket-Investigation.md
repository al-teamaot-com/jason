# CAP-001 — Professional Ticket Investigation

**Version:** 0.1  
**Status:** Building  
**Capability Stage:** Recommend  
**Owner:** Jason Architecture Authority  
**Initial Providers:** Autotask, Datto RMM, IT Glue, approved reasoning provider  

## 1. Purpose

CAP-001 gives an AOT technician a concise, evidence-grounded assessment of an operational ticket and a recommended next action.

The capability is the first end-to-end Jason vertical slice. It exists to validate the Identity and Authority Service, Evidence and Memory Service, orchestration pattern, reasoning contract, communication standard, and learning loop against real operational work.

Version 0.1 is recommendation-only. It may collect approved evidence, analyze, summarize, rank hypotheses, and recommend. It must not perform operational remediation.

## 2. Organizational outcome

The capability succeeds when it reduces the time and attention required for a technician to understand a ticket without reducing safety, accuracy, client isolation, explainability, or professional judgment.

The primary measure is **Time to Useful Answer**.

A useful answer must tell the technician:

1. what appears to be happening;
2. what evidence supports that view;
3. what remains uncertain or missing;
4. what the technician should do next;
5. how confident Jason is;
6. whether risk, approval, or escalation is involved.

## 3. Scope

### 3.1 Included in Version 0.1

- Accept one operational ticket as the root work item.
- Resolve requester, AOT, client, ticket, and asset context.
- Verify authority to investigate the ticket.
- Preserve original ticket content and permitted supporting material as evidence.
- Normalize diagnostics and supporting records into observations.
- Retrieve a bounded set of relevant prior cases and approved knowledge.
- Identify missing information.
- Generate and rank plausible hypotheses.
- Recommend the lowest-risk useful next action.
- Produce a progressive-disclosure technician response.
- Preserve the investigation record and learning candidate.
- Accept a later human-recorded outcome for evaluation and learning.

### 3.2 Excluded from Version 0.1

- Automatic remediation.
- Closing or changing ticket status.
- Sending client communication.
- Creating or modifying configuration items.
- Unbounded searches across client data.
- Treating model output as authoritative evidence.
- Automatically promoting a learning candidate to approved knowledge.
- Legal, HR, contractual, or other inherently human determinations.

## 4. Governing principles

CAP-001 must conform to the Jason Constitution, canonical models, J-401 Adaptive Build Method, JKD-001, and JKD-002.

The following rules are mandatory:

1. Evidence before inference.
2. Authority before access.
3. Client scope before retrieval.
4. Observation, inference, decision, and communication remain distinct.
5. Missing information reduces confidence; it never invites fabrication.
6. Use the smallest useful investigation.
7. Recommend the lowest-risk successful next step.
8. Preserve complete internal evidence while respecting human attention externally.
9. Agents never communicate with or invoke other agents directly.
10. The orchestrator owns routing, context, policy gates, retries, timeouts, escalation, and final assembly.

## 5. Invocation contract

### 5.1 Required request

```json
{
  "capability": "operations.ticket.investigate",
  "version": "0.1",
  "correlation_id": "corr_...",
  "requester_context": {
    "identity_id": "idn_...",
    "organization_id": "org_aot",
    "client_id": "client_...",
    "requested_mode": "recommend",
    "execution_mode": "deterministic"
  },
  "ticket": {
    "provider": "autotask",
    "external_id": "T20260730.0012"
  },
  "options": {
    "include_related_tickets": true,
    "include_asset_context": true,
    "include_knowledge_matches": true,
    "maximum_related_cases": 5,
    "maximum_evidence_age_days": 90
  }
}
```

### 5.2 Mandatory fields

The request must contain:

- capability name and supported version;
- correlation ID;
- requester identity;
- organization and client scope;
- requested mode;
- ticket provider and external identity.

Missing client scope, requester identity, ticket identity, or correlation ID requires rejection.

### 5.3 Optional supplied evidence

The caller may supply references to already-collected evidence, including:

- diagnostic output;
- monitor or alert output;
- screenshots;
- logs;
- email or message content;
- configuration item data;
- recent ticket notes;
- approved documentation.

The capability accepts references, not unaudited conversational claims, as source evidence.

## 6. Preconditions

Before investigation begins, the orchestrator must obtain a valid execution context from JKD-001.

The context must establish:

- requester identity;
- AOT role;
- client and tenant scope;
- ticket identity;
- permitted capability and mode;
- authentication assurance;
- expiration;
- matched authority grants.

The maximum mode for Version 0.1 is `recommend`.

If the requested mode exceeds `recommend`, the service must return `allowed_limited` or reject the request according to policy.

## 7. Workflow state machine

CAP-001 uses the following states:

1. `received`
2. `context_validating`
3. `evidence_collecting`
4. `evidence_normalizing`
5. `context_retrieving`
6. `reasoning`
7. `quality_checking`
8. `response_assembling`
9. `completed`
10. `awaiting_information`
11. `escalated`
12. `failed`

A case must preserve every material transition, actor, timestamp, reason, and related evidence.

### 7.1 State transition outline

```text
received
  -> context_validating
  -> evidence_collecting
  -> evidence_normalizing
  -> context_retrieving
  -> reasoning
  -> quality_checking
  -> response_assembling
  -> completed
```

At any stage the workflow may transition to:

- `awaiting_information` when a bounded, specific missing item prevents a useful conclusion;
- `escalated` when the case is outside competency, authority, or acceptable risk;
- `failed` when safe continuation is impossible.

## 8. Evidence collection plan

The orchestrator builds a case-specific collection plan. It must not retrieve all available client data by default.

### 8.1 Minimum evidence set

The minimum initial set is:

- original ticket title and description;
- ticket creation and update timestamps;
- company/client mapping;
- requester identity when present;
- configuration item or asset mapping when present;
- ticket status, priority, queue, and assignment;
- visible notes and attachments permitted by authority;
- source and collection metadata.

### 8.2 Conditional evidence

Additional evidence may be collected when relevant:

- Datto RMM device facts and monitor output;
- approved component diagnostic output;
- recent related tickets for the same client and asset;
- relevant IT Glue documentation;
- service, agreement, site, and contact context;
- approved knowledge items;
- recent changes or alerts affecting the same asset or service.

### 8.3 Bounded curiosity

Each retrieval must have a reason tied to a hypothesis, missing fact, or expected outcome.

The collection record must state:

- what was requested;
- why it was relevant;
- source system;
- scope;
- time range;
- result count;
- whether the result was used.

## 9. Normalized case package

The Evidence and Memory Service provides the reasoning step a bounded case package.

```yaml
case_package:
  case_id: case_...
  correlation_id: corr_...
  client_id: client_...
  ticket:
    canonical_id: ticket_...
    provider: autotask
    external_id: T20260730.0012
    title: "..."
    description: "..."
    status: "..."
    priority: "..."
    created_at: "..."
  affected_objects:
    - object_id: asset_...
      object_type: asset
      relationship_confidence: 0.98
  observations: []
  evidence_index: []
  approved_knowledge: []
  similar_cases: []
  constraints:
    mode: recommend
    client_scope: client_...
    maximum_risk: medium
  unanswered_questions: []
```

Only evidence and memory permitted by the execution context may enter this package.

## 10. Observation contract

An observation is a normalized statement derived from identified evidence.

```yaml
observation:
  id: obs_...
  statement: "Disk diagnostic reports 14 pending sectors."
  subject_id: asset_...
  observed_at: "..."
  recorded_at: "..."
  source_evidence_ids:
    - evd_...
  source_type: diagnostic
  confidence: 0.99
  interpretation_level: direct
  tags:
    - disk
    - smart
```

Allowed interpretation levels:

- `direct` — explicitly present in source evidence;
- `normalized` — reformatted or mapped without adding meaning;
- `derived` — calculated from evidence by a deterministic method.

A model-generated conclusion is never an observation.

## 11. Reasoning contract

The reasoning provider receives the normalized case package and returns structured analysis only.

### 11.1 Required reasoning output

```yaml
analysis:
  situation_summary: "..."
  missing_information:
    - item: "..."
      importance: required|helpful
      reason: "..."
      suggested_collection_step: "..."
  hypotheses:
    - id: hyp_...
      statement: "..."
      supporting_observation_ids: []
      contradicting_observation_ids: []
      confidence: 0.0
      status: leading|plausible|unlikely|rejected
      next_test: "..."
  recommendation:
    action: "..."
    reason: "..."
    confidence: 0.0
    risk: low|medium|high|critical
    approval_required: false
    expected_outcome: "..."
    verification: "..."
    alternatives: []
  escalation:
    required: false
    reason: null
    target_class: null
  learning_candidate:
    proposed: false
    summary: null
    reuse_scope: null
```

### 11.2 Reasoning constraints

The reasoning provider must:

- cite observation and evidence identifiers;
- distinguish confirmed facts from hypotheses;
- expose contradictions;
- use calibrated confidence;
- state when evidence is insufficient;
- avoid instructions exceeding the allowed mode;
- avoid unsupported client, legal, security, or compliance conclusions;
- prefer a small next step over an expansive investigation when both are adequate.

## 12. Confidence standard

Confidence represents support from available evidence, not rhetorical certainty.

Suggested interpretation:

| Range | Meaning |
|---|---|
| 0.90–1.00 | Strong direct or corroborated support; material contradictions absent |
| 0.70–0.89 | Good support; limited uncertainty remains |
| 0.50–0.69 | Plausible but incomplete; additional evidence recommended |
| 0.25–0.49 | Weak; one of several reasonable explanations |
| 0.00–0.24 | Speculative or contradicted |

Confidence must be reduced when:

- sources are stale;
- identity or asset mapping is uncertain;
- evidence conflicts;
- required diagnostics are missing;
- a similar case is used without sufficient matching context;
- the reasoning depends on an unverified relationship.

## 13. Quality gates

Before output is released, deterministic and policy checks must validate:

1. client scope is consistent across all referenced objects;
2. every material factual statement has evidence or observation support;
3. hypotheses are labeled as hypotheses;
4. no unsupported execution has been proposed as already completed;
5. the recommendation is within Version 0.1 authority;
6. risk and approval status are present;
7. missing information is explicit;
8. confidence is present and within range;
9. no secrets or restricted fields are exposed;
10. the response follows progressive disclosure;
11. evidence references resolve;
12. the case record is auditable.

Failure of a critical quality gate prevents completion.

## 14. Technician-facing response contract

The default technician response should be readable in approximately ten seconds.

### 14.1 Level 1 — Useful answer

```text
Assessment
[one or two sentences]

Recommended next action
[one clear action]

Confidence: [High/Moderate/Low] ([numeric value])
Risk: [Low/Medium/High/Critical]
```

### 14.2 Level 2 — Supporting detail

```text
Why
- [decisive observation]
- [decisive observation]

Missing or uncertain
- [specific missing item or contradiction]

Verify success
- [verification step]
```

### 14.3 Level 3 — Investigation detail

Available on request or in the case record:

- all observations;
- hypotheses and ranking;
- contradictory evidence;
- retrieval history;
- evidence index;
- policy and authority decision;
- reasoning provider metadata;
- complete audit events.

The default response must not expose the full internal investigation journal.

## 15. Completion outcomes

A run may end with one of these outcomes:

- `useful_recommendation`
- `information_required`
- `human_escalation_required`
- `no_issue_identified`
- `duplicate_or_related_case_identified`
- `unsupported_request`
- `authorization_failed`
- `safe_failure`

Every outcome must include a reason code.

## 16. Memory records created

A completed or suspended investigation creates:

- case record;
- immutable evidence references;
- normalized observations;
- retrieval and provenance records;
- hypotheses and confidence history;
- recommendation;
- authority and policy decisions;
- technician-facing response;
- audit events;
- optional learning candidate;
- later outcome and verification records when supplied.

Conversation text is not automatically promoted to knowledge.

## 17. Outcome feedback contract

A technician or trusted system may later report what happened.

```json
{
  "case_id": "case_...",
  "outcome": {
    "status": "resolved",
    "resolution_summary": "SSD replaced and diagnostics passed.",
    "recommendation_followed": true,
    "actual_root_cause": "failing_ssd",
    "verified_at": "2026-07-30T15:00:00-04:00",
    "verified_by": "idn_...",
    "supporting_evidence_ids": ["evd_..."]
  }
}
```

Outcome feedback is used to:

- measure recommendation usefulness;
- calibrate competency reputation;
- identify false confidence;
- propose approved knowledge;
- improve retrieval and reasoning contracts;
- reveal architectural gaps.

It must not silently rewrite the original investigation.

## 18. Events emitted

- `ticket_investigation.received`
- `ticket_investigation.authorized`
- `ticket_investigation.authorization_failed`
- `ticket_investigation.evidence_collected`
- `ticket_investigation.awaiting_information`
- `ticket_investigation.reasoning_completed`
- `ticket_investigation.quality_gate_failed`
- `ticket_investigation.completed`
- `ticket_investigation.escalated`
- `ticket_investigation.failed`
- `ticket_investigation.outcome_recorded`
- `ticket_investigation.learning_candidate_created`

Events describe state changes and do not directly perform operational remediation.

## 19. Failure behavior

| Condition | Required behavior |
|---|---|
| Missing or invalid execution context | Reject and audit |
| Client or tenant mismatch | Reject, flag boundary violation, and audit |
| Ticket not found | Return `information_required` or `safe_failure`; do not guess |
| Asset mapping ambiguous | Preserve ambiguity, reduce confidence, request the smallest clarification |
| Provider unavailable | Use valid preserved evidence when policy permits; otherwise stop safely |
| Reasoning provider unavailable | Preserve case and evidence; return a clear retryable failure |
| Evidence conflict | Expose contradiction and avoid a definitive conclusion |
| Required evidence absent | Recommend a bounded collection step |
| Quality gate failure | Do not release the response; record reason and escalate when appropriate |
| Unsupported domain or risk | Escalate to the appropriate human role |

## 20. Security and privacy

- Every query and record is client scoped.
- Secrets, tokens, and connector credentials must not enter reasoning context or logs.
- Personally identifiable and regulated information must be minimized according to purpose.
- Attachments must be classified before inclusion in reasoning context.
- Prompt injection or untrusted instructions contained in ticket text or attachments must be treated as data, not governing instructions.
- External content may not alter authority, policy, or system behavior.
- Cross-client similarity retrieval is prohibited in Version 0.1.

## 21. Initial provider adapter responsibilities

### 21.1 Autotask adapter

- retrieve ticket, company, contacts, notes, attachments, assignment, queue, priority, status, and configuration item references;
- map provider IDs to canonical objects;
- preserve source timestamps and record versions;
- avoid writing changes in Version 0.1.

### 21.2 Datto RMM adapter

- retrieve authorized device facts, monitor output, recent component results, and relevant alert context;
- preserve device-to-client mapping and timestamps;
- avoid running components in Version 0.1 unless a separately approved evidence-collection capability is introduced.

### 21.3 IT Glue adapter

- retrieve only authorized, relevant, approved documentation and structured records;
- preserve source, organization mapping, and document version;
- distinguish documentation from verified current state.

### 21.4 Reasoning adapter

- accept the canonical case package;
- return schema-valid structured analysis;
- expose provider, model, version, request ID, and timing metadata;
- have no direct connector access;
- hold no independent authority;
- never communicate with another agent.

## 22. Initial API surface

```http
POST /v1/capabilities/ticket-investigation/runs
GET  /v1/capabilities/ticket-investigation/runs/{run_id}
GET  /v1/capabilities/ticket-investigation/runs/{run_id}/response
GET  /v1/capabilities/ticket-investigation/runs/{run_id}/evidence
POST /v1/capabilities/ticket-investigation/runs/{run_id}/outcome
POST /v1/capabilities/ticket-investigation/runs/{run_id}/retry
```

Retry must create a new attempt record while preserving prior attempts.

## 23. Reference test fixtures

The initial implementation must include at least these fixtures:

1. **Healthy but noisy alert** — evidence shows no actionable fault; Jason recommends monitoring or closing after verification.
2. **Disk failure indicators** — SMART evidence supports likely failure; Jason recommends backup verification and replacement planning.
3. **Windows Update unhealthy** — mixed evidence, multiple plausible causes, bounded next diagnostic step required.
4. **Missing asset mapping** — ticket exists but the affected device cannot be reliably identified.
5. **Conflicting diagnostics** — one source indicates failure and another indicates healthy state.
6. **Duplicate historical ticket** — a relevant prior case exists for the same client and asset.
7. **Cross-client contamination attempt** — supplied evidence belongs to another client and must be rejected.
8. **Prompt injection in ticket text** — untrusted text attempts to override policy or request secrets.
9. **Provider outage** — Autotask or Datto RMM is unavailable after initial evidence preservation.
10. **High-risk recommendation** — likely security incident requires immediate human escalation rather than routine troubleshooting.

## 24. Acceptance criteria

CAP-001 Version 0.1 is acceptable when:

- one API request creates a complete investigation run;
- identity, authority, and client context are validated;
- original source material is preserved;
- evidence, observations, hypotheses, and recommendations remain distinct;
- all material claims are traceable;
- the default response is concise and actionable;
- missing information is handled honestly;
- no operational action is performed;
- all test fixtures pass;
- no cross-client data is exposed;
- outcome feedback can be recorded;
- metrics can be calculated from stored records.

## 25. Initial metrics

- median and 95th percentile Time to Useful Answer;
- technician acceptance rate;
- recommendation-followed rate;
- confirmed-correct root-cause rate;
- false-confidence rate;
- evidence citation completeness;
- information-request usefulness;
- escalation appropriateness;
- cross-client leakage count;
- quality-gate failure count;
- model/provider failure rate;
- cost per completed investigation;
- learning candidates accepted, rejected, or duplicated.

A cross-client leakage count greater than zero is a release-blocking incident.

## 26. Deliberately deferred

Do not add these until operating evidence justifies them:

- automatic ticket updates;
- autonomous remediation;
- client-facing delivery;
- cross-client trend mining;
- generalized multi-agent investigation teams;
- self-modifying prompts or policies;
- automatic knowledge approval;
- broad workflow engine abstractions beyond what CAP-001 needs;
- universal ticket-provider support.

## 27. Implementation sequence

1. Define JSON Schemas for invocation, case package, analysis, response, and outcome.
2. Build the CAP-001 orchestrator state machine.
3. Implement Autotask read-only ticket adapter.
4. Connect JKD-001 execution context validation.
5. Connect JKD-002 evidence and case storage.
6. Implement deterministic normalization and quality gates.
7. Implement one approved reasoning adapter.
8. Render progressive-disclosure technician output.
9. Add the ten reference fixtures.
10. Pilot with historical, de-identified tickets before live read-only use.
11. Compare Jason recommendations with technician outcomes.
12. Revise the architecture only where real evidence reveals a durable requirement.

## 28. Definition of done

CAP-001 is not done merely because it produces plausible text.

It is done when a technician can submit a real, authorized ticket and receive a concise, evidence-linked, safe, auditable recommendation; the investigation can later be compared with the actual outcome; and the entire process remains within client, authority, risk, and progressive-disclosure boundaries.
