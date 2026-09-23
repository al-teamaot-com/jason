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
