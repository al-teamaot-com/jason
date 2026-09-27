# Decision Memory

Decision Memory lets Jason reuse previously verified conclusions before invoking new model reasoning.

It now also contains the provider-neutral foundation for **Operational Resolution Memory (RESMEM-001 / TODO-OPS-001)**: structured historical incident outcomes, successful and failed troubleshooting steps, deterministic similar-case ranking, and durable single-node SQLite storage.

## Constitutional fit

This subsystem is constitutional because it does not grant new authority. It reuses evidence-backed knowledge under the same policy, approval, scope, verification, audit, and escalation controls that govern the original action.

A cached result is never treated as universally true. It is valid only when:

- required evidence is present;
- applicability conditions match;
- exclusion conditions are absent;
- the record has not expired or been invalidated;
- client and organization scope match policy;
- the proposed action is still permitted;
- verification remains mandatory after execution.

Decision Memory may reduce model calls, but it may not bypass authorization, safety controls, disruption controls, client isolation, or human approval requirements.

## Processing order

1. Normalize ticket/alert and environment facts.
2. Evaluate deterministic rules.
3. Search exact verified decision memory.
4. Search verified pattern memory.
5. Retrieve similar historical resolution cases as evidence.
6. Rank prior steps by similarity, recency, outcome quality, and observed success/failure history.
7. Prefer current read-only evidence gathering before proposing remediation.
8. Invoke an approved model only when needed.
9. Route any action through normal Jason governance and the Central Orchestrator.
10. Verify the outcome and record the resulting history.

## Memory classes

- `exact`: an exact normalized fingerprint match.
- `pattern`: a bounded reusable rule covering allowed variations.
- `similar_case`: historical evidence only; never direct authority to act.

## Operational Resolution Memory

The RESMEM-001 foundation is implemented in:

- `resolution_memory.py` — provider-neutral case/signature/step contracts plus deterministic similar-case and step-evidence ranking;
- `resolution_sqlite.py` — durable single-node SQLite storage with organization/client query isolation;
- `resolution_service.py` — bounded service facade and JSON-safe reasoning projection;
- `test_resolution_memory.py` — regression coverage for isolation, recency, failures, ranking, durability, and no-authority semantics.

A `ResolutionCase` preserves:

- organization/client scope;
- normalized issue signature;
- source/correlation references;
- product/platform/device-role context;
- symptoms and normalized attributes;
- diagnostics, remediation, verification, and communication steps;
- success, improvement, failure, or inconclusive outcome for each step;
- read-only/approval/disruption metadata;
- root cause and final resolution;
- technician confirmation and recency.

Raw historical cases are deliberately restricted to the same organization **and client**. Any future cross-client reusable pattern must be separately normalized, reviewed, and promoted through governed pattern memory rather than exposing another client's raw history.

Similarity and step ordering are evidence functions only. Every returned match and step projection explicitly carries `grants_authority=false`. Historical success therefore cannot convert a mutating or disruptive action into an approved action.

Failures remain first-class evidence. Repeated failed steps can be marked `historically_unreliable`; repeated successful comparable steps can be marked `historically_supported`. A single success is intentionally insufficient to create a verified pattern or organizational truth.

## Non-negotiable controls

- No raw ticket-text-to-answer cache.
- No cross-client reuse of raw client-sensitive resolution cases.
- No automatic widening of applicability.
- No execution authority stored in memory.
- No historical outcome may bypass current approval or disruption rules.
- No silent use of expired, deprecated, or low-similarity records.
- Failures and contradictory outcomes remain visible and reduce confidence.
- Similar-case history is evidence, not an autonomous remediation engine.
- Promotion from similar case to reusable pattern/playbook requires governed review.

## Current implementation boundary

The RESMEM-001 data/ranking foundation is being built first. It does **not** yet mean every Autotask ticket or Datto alert is automatically ingested, and it does not yet automatically inject Resolution Memory into every technician conversation. Those are subsequent integration slices after the durable model, isolation, ranking, and regression contract are proven.

The first live integrations should ingest verified closed/resolved work from authoritative sources and expose a governed read path for similar-case evidence. Automatic provider actions remain outside this memory subsystem.


## Owner-scoped live retrieval

Organization-scoped AOT owners may explicitly select an Autotask company for `operations.resolution.search` or `operations.resolution.read` with `company_id`. Jason verifies that company through the ordinary governed `service.company.read` path, proves the owner already has the exact organization-scoped OBSERVE grant for the Resolution Memory capability, and derives a short-lived one-minute client-specific OBSERVE context.

This does not create a cross-client search mode. Raw historical cases remain restricted to the selected client, non-owner callers cannot derive this scope, and failure to verify the Autotask company or exact Resolution Memory authority fails closed.


## Automatic verified-resolution ingestion (RESMEM-002)

Jason ticket-work completion now has a distinct `complete_work` path. A plain Autotask status change does not create memory. To create durable Resolution Memory automatically, the ticket must already be claimed by Jason and the completion request must include a bounded structured resolution package with:

- incident category, product, device role, platform, symptoms, and optional bounded attributes;
- explicit root cause and final resolution;
- overall `resolved` outcome;
- technician confirmation;
- terminal verification confirmation;
- at least one ordered troubleshooting step;
- at least one successful verification step;
- evidence summaries for every stored step.

Jason derives the ticket identity and company boundary from an authoritative governed Autotask read. The caller cannot supply a different client boundary or arbitrary case identity. The case ID is deterministic from the Autotask ticket, making exact repeat completion idempotent. A conflicting second history for the same deterministic case ID fails closed.

The Autotask ticket update still follows its normal mutation authority and approval rules and still requires provider readback verification. Only after that governed ticket completion succeeds does Jason ingest the verified resolution locally and mark the ticket-work claim completed. Historical remediation metadata remains evidence only and every later Resolution Memory result continues to expose `grants_authority=false`.

If local memory ingestion fails after the provider ticket update has succeeded, Jason does not fabricate success for the memory write; the ticket provider result remains visible and the claim is left retriable rather than silently inventing a case.

## Cross-client AOT Pattern Memory (RESMEM-003)

RESMEM-003 adds a second resolution-memory layer without weakening raw client isolation.

The retrieval hierarchy is now:

1. current live evidence and current incident facts;
2. same-client exact/similar Resolution Memory cases;
3. AOT-wide sanitized generalized patterns;
4. generic playbook, vendor, and reference knowledge.

Historical similarity never outranks contradictory current live evidence. Both client cases and AOT patterns remain evidence only and return `grants_authority=false`; execution authority continues to come only from current Jason governance.

### Promotion threshold

Automatic AOT-wide promotion requires at least **two independent client scopes** supporting the same sanitized technical pattern. One client case cannot promote itself automatically. A single-client pattern may be created only by explicit technician-approved early promotion, and its confidence is reduced.

Promotion confidence incorporates independent support count, recency, outcome quality, contradiction rate, and current-environment similarity at retrieval time. Failed and inconclusive steps are retained in aggregate form. Contradictory evidence lowers pattern confidence and produces conflicted/unreliable step dispositions rather than being discarded.

### Sanitization contract

Cross-client pattern payloads are constructed from an allowlisted technical schema only. They may retain normalized symptom class, platform/product/device-role traits, bounded technical version, allowlisted environment attributes, canonical action keys, aggregate success/failure counts, outcome quality, confidence, support count, and approval/disruption metadata.

They never contain source case IDs, ticket numbers, source references, client/company/customer IDs or names, hostnames, IP addresses, usernames, email addresses, domains, tenant IDs, configuration-item IDs, provider-native record IDs, owner names, or free-form source evidence. Free-form root-cause and resolution text are not copied into AOT patterns; the root-cause class is derived from sanitized technical context and canonical successful remediation keys.

If a symptom, retained attribute, canonical action key, or other proposed pattern field contains identifying/ambiguous material, that case fails closed for cross-client promotion while remaining available inside its original client-scoped Resolution Memory boundary.

### Storage and access boundary

`resolution_cases` remains the authoritative raw client-scoped history. Runtime raw reads still require organization + client scope. The internal derivation feed is not exposed as a runtime read capability and exists only to build sanitized AOT pattern records.

`aot_resolution_patterns` stores only sanitized generalized records. Pattern projections contain aggregate supporting-client counts but no list of source clients or source cases. Another client can retrieve a matching AOT pattern while remaining unable to read any raw source case from another client.
