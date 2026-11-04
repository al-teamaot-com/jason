# PMV3 Isolated Service Separation Plan

## Purpose
Reduce PMV3 failure coupling without changing the active PMV3 control path. PMV3 remains the authority and sequencing boundary for integration and production. Independent services produce bounded evidence/state that PMV3 may consume later through an explicit integration change.

## Source-only implementation boundary
This branch does **not** install timers or services, modify PMV3 imports, change branch protection, merge to `main`, change production, grant authority, or contact providers. Each worker is a one-shot program with an explicit input and its own state output.

## Initial services

| Service | Owns | Does not own |
|---|---|---|
| Documentation Assurance | Detect material source changes needing documentation review; persist scan state | Merge docs, approve releases, block unrelated engineering |
| Provider Health Monitor | Aggregate sanitized read-only provider probe receipts; classify healthy/degraded/stale/unhealthy | Provider writes, credentials, production admission |
| Test/Evidence Collection | Hash and index evidence; determine exact-candidate/freshness reuse | Run deployments, waive tests, authorize release |
| Work Reconciliation | Classify commitments into actionable/recoverable/external/governed/waiting | Claim work, merge, deploy, mint approvals |

## Shared-state principle
Services remain separate processes but report deterministic JSON records. They do not create competing work queues. PMV3 remains the single release-state authority. Future integration should reference these records by digest and observed source revision rather than copying their internal state.

## Failure isolation
- Documentation attention does not stop unrelated engineering.
- Stale provider evidence is reported as stale rather than generic PMV3 failure.
- Stale/mismatched test evidence requests refresh instead of poisoning release state.
- Recoverable work defects are distinguished from genuine external/governed blockers.

## Proposed later scheduling
Scheduling is intentionally not installed by this branch. After PMV3 stabilization, each worker can receive a dedicated systemd timer or event trigger and an isolated state directory under `/var/lib/jason/services/<service>/`.

## PMV3 integration boundary
A later separately reviewed change may allow PMV3 to consume only these service outputs:
- documentation assurance status and evidence digest;
- provider health status relevant to the release scope;
- reusable test-evidence index bound to exact candidate SHA;
- work reconciliation next-action classification.

PMV3 must never infer production approval from any service record. Exact-SHA owner authorization, production transaction locking, rollback identity, drift detection, and post-deployment acceptance remain PMV3 controls.
