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

## Second service slice

| Service | Owns | Does not own |
|---|---|---|
| Dependency/Conflict Analysis | Detect file/component/contract/provider/schema/deployment overlap and explicit dependencies | Serialize releases, approve work, merge |
| Source Baseline Monitor | Compare an expected immutable source SHA with an observed protected ref | Change refs, lock GitHub, merge |
| Rollback Readiness | Validate that a complete, already-verified rollback manifest is present | Construct or execute rollback, weaken rollback requirements |
| Operational Acceptance | Aggregate explicit post-change checks into accepted/pending/failed | Deploy, authorize production, manufacture missing evidence |

These services further shrink the intended PMV3 core without changing it yet. They are deterministic classifiers/aggregators, not controllers. They cannot turn missing evidence into authority and cannot perform a provider or production mutation.

## Current migration direction

1. Preserve current PMV3 production-safety controls while service separation is proven.
2. Pause new PMV3 controller/gate/lock complexity unless required to protect an existing production safety boundary.
3. Build and test isolated services against fixtures and existing state formats.
4. Add real read-only adapters and independent service supervision.
5. Introduce one shared authoritative ledger contract.
6. Migrate one responsibility at a time out of PMV3 with comparison/shadow evidence.
7. Remove superseded PMV3 logic only after equivalent service behavior is verified.
8. Keep exact-SHA owner approval, single production transaction, verified rollback, drift detection, deployment, and post-deployment verification in the PMV3 core.

## Shared ledger and supervision

The isolated services now have a source-defined ledger contract (`config/isolated-services.json`) and two additional components:

- `isolated_service_ledger.py` produces a digest-bound view of service-owned state files and their freshness. It does not grant authority or execute work.
- `isolated_service_supervisor.py` classifies service health. Optional service failures are warnings/degradation, not global PMV3 blockers. Only services explicitly marked `required` may create a supervisor-level block due to missing/stale evidence.

All initial services are deliberately configured `required: false` while the architecture is source-only and under shadow validation. Promotion of any service to `required` is a later migration decision tied to the responsibility being removed from PMV3.


## Existing execution inventory and migration owner map

| Existing implementation | Current ownership | Proposed target and migration rule |
|---|---|---|
| `tools/engineering_pipeline.py` (support, TODO, development stages) | PMV3 sequential work dispatcher | Keep existing approved worker authority; split process scheduling into independent workers, retaining support-first and claim/idempotency semantics |
| `tools/engineering_supervisor.py` and TODO reconciliation stage | PMV3 inline monitoring and retries | Work Reconciliation service; only advisory until exact state parity and bounded retry/claim acceptance are proven |
| `tools/todo_engineering_intake.py` | Owner-approved TODO admission | Existing TODO authority remains canonical; independent worker must consume this authority, never create a second queue |
| `tools/pr_integration_source_reconciler.py` and `tools/pmv3_integration_queue.py` | Protected-main integration | Retain PMV3 core integration admission and the protected-main gate |
| `tools/todo_release_bridge.py` | Release and TODO acceptance reconciliation | Release Evidence and Operational Acceptance services provide facts; PMV3 retains exact-SHA production admission and authoritative closure |
| `tools/pmv3_engineering_controller.py` | Global pipeline passes and retry loop | Delete redundant looping logic **only after** individual worker supervision proves forward progress, no duplicate claims, and accurate blocker classification |
| `tools/release_breaker_recovery_manager.py` | Protected release-safety recovery | Remains in trusted Production Manager/release-control path; never moved to an unprivileged advisory worker |
| `tools/documentation_source_reconciler.py` and documentation readiness tools | Documentation validation | Reuse in independent Documentation Assurance service; do not equate a changed docs file with accurate documentation |
| `tools/provider_read_live_acceptance.py` and provider health canaries | Provider read evidence | Separate Provider Health service; preserve credential boundaries and do not turn absence of fresh probes into a healthy assertion |

### Shadow evidence inputs already verified

- `/var/lib/jason/provider-health-canaries.json` contains provider result objects with explicit `healthy` booleans and `generated_at`. The adapter reads bounded regular files and persists only provider name/health, age and evidence digest.
- `/var/lib/jason/openclaw/support-repair/todo-release-state.json` exposes durable `items` keyed by TODO identity and `updated_at`. The adapter normalizes phase/blocker and reports stale evidence rather than claiming eligible work was executed.
- `origin/main` is a local tracking ref and may be stale. The Source Baseline Monitor can independently query `refs/heads/main` with a read-only `git ls-remote`, pinned to an exact expected SHA.
- Root-protected release-control records and privileged rollback paths are **not** bypassed. Rollback and operational acceptance remain advisory/pending until evidence is obtained through the existing approved protected readback path.

### No premature authority promotion

No isolated record can authorize or trigger production deployment. In this branch, service outputs carry `advisory_only=true` and `production_authority=false`; unknown, missing, future-dated, and stale data remain visible. Tests prove that an optional worker failure cannot freeze other workers.

### Before migration from current PMV3

1. Have a complete, current source/control map and baseline health evidence.
2. Prove independent worker execution, failure isolation, input bounds, output atomicity and recovery across two consecutive validation cycles.
3. Validate a representative approved TODO against current canonical intake state; no duplicated claims, writes, PRs, or loss of progress.
4. Validate a representative release candidate against existing main-protection, exact-SHA, Teams owner authorization, exclusive transaction, rollback and post-deployment acceptance semantics.
5. Introduce optional read-only/shadow output consumption in a staged migration, with old authoritative behavior preserved until proven equivalent.
6. Only then remove duplicated PMV3 code and scheduling. Do not remove production safety/authorization controls or override a held production transaction.

The systemd template units in `infrastructure/isolated-services/` are **not installed**; their deployment must be in an immutable Release Manager manifest and independently authorized for the exact candidate SHA.
