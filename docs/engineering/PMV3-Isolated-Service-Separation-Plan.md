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


### Approved protected-readback input (rollback readiness)

The independent rollback observer now reads **only** root-published snapshots at:

- `/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json`
- `/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json`

The underlying root-owned `production-control-state.json` and `production-drift.json` are never opened or modified by the service. Its bounded regular-file reader rejects symlinks and oversized/non-JSON files, records exact source SHA-256 digests, and performs the same 90-second freshness model as the native Release Manager: **publisher file mtime**, not the older `control.updated_at` breaker-change timestamp. The service checks LKG manifest completeness, release identity alignment, breaker state, and drift status. It reports only `evidence_present`, `blocked`, `unknown` or `stale`, never grants rollback/deployment authority, and never closes a breaker.

This distinction was verified against current operational readback behavior. After the owner-approved PMV3 pause, the old timer was kept active while a user-level systemd `ConditionPathExists` guard blocks its engineering service starts. Native drift returned to PASS without disabling release safety. Breaker recovery continues exclusively through its existing proof-and-readmission policy (three distinct fresh root PASS observations, cooldown and bounded root verification), not by modifying protected state.


## Existing independent publishers: reuse, do not duplicate

A fresh host inventory established that Jason already has independently scheduled native publishers:

| Existing producer | Cadence observed | Migration decision |
|---|---|---|
| `jason-documentation-reconciliation.service/.timer` | Noon and midnight | **Reuse** for approved documentation PR/readiness updates; the independent Documentation Assurance service detects unresolved source-to-doc gaps and consumes the existing publisher's verified receipts. Do not create a second documentation writer or an alternate branch merge route. |
| `jason-provider-health-canary.service/.timer` | Periodic | **Reuse** the existing read-only provider probes; the new Provider Health service normalizes their signed/observed health, freshness and error classification. Do not create a second credential-bearing provider probe framework. |
| Native Release Manager root readback and drift controls | Continuous | **Keep protected**. Independent Rollback Readiness reads root-published copies only; it cannot open root files, reset breaker, or execute rollback. |
| Existing support/owner-approved/TODO native workers | Formerly chained in PMV3 | **Separate scheduling only after governed cutover**, retain exact same entrypoints and their existing scope/claim/approval logic. |

These reuse decisions matter: a new writer for documentation or a new provider-check scheduler would add the very overlapping control planes that this project is intended to eliminate.

## Native engineering lane cutover acceptance

The source-only templates `jason-independent-{support,todo-intake,development,supervisor}.{service,timer}` call existing native worker implementations. Their live installation is **not authorized** by source tests alone. The immutable release package must include all companion scripts, particularly `pmv3_worker_release_gate.py` (present in source but not yet installed at the proposed path), and the exact unit inventory in `infrastructure/isolated-services/installation-manifest.json`.

Prove during preproduction and governed cutover:

- All lanes run as unprivileged `al`, never root, with bounded filesystem writes and no expanded provider authority.
- No two processes claim the same support/TODO item, create duplicate PRs, or duplicate external actions; claim/capacity/support-first evidence uses the existing native ledger.
- A held production transaction mutex prevents lane execution without a failed service; no new lane starts while the old monolithic engine is active.
- Each service restart/failure is isolated; one failed docs/provider/engineering lane cannot cause an unrelated production circuit-breaker event.
- Source/test/health evidence remains bound to the exact intended merged SHA, and the existing protected release controls continue independently.
- The old timer stays in LKG-expected `active` state but its guard refuses starts until the replacement is deployed and independently verified. Removing the guard and changing last-known-good unit expectations requires a separately governed, rollback-ready release.

The service-splitting PR is currently **source-only**, not a certified production candidate. A passing PR diff/CI does not replace production Manager's exact SHA, source scope, provider-backed operational acceptance, breaker and rollback checks, or Teams authorization.


## Reproducible isolated-service preproduction acceptance

`python3 tools/ci/isolated_service_preproduction_lab.py` constructs a disposable Git
repository and sanitized fixture provider/TODO/test/dependency/rollback/acceptance
snapshots, then runs all eight isolated services as independent one-shot Python
processes through two complete cycles. It verifies durable documentation review
retention, actual provider failure isolation, stable TODO classification, exact
source-SHA absence remaining unknown, expected preproduction classification,
unchanged fixture source digests, and exactly ten stable service/ledger/supervisor
records. No provider calls, service deployment, GitHub mutations, approval grants,
or production state writes occur. The dedicated GitHub CI workflow preserves a
JSON acceptance receipt as an artifact. This lab is **not** equivalent to a
production release or a provider-backed operational acceptance.

The independent native engineering support, TODO-intake, development and
supervisor timer/service templates are staged source-only. They call existing
worker entrypoints and retain the existing production-transaction admission
check; their installer must include the admission helper in its immutable host
manifest. Their current deployment status remains **not installed/disabled**.


### Advisory acceptance terminology

A standalone untrusted rollback manifest can only report
`manifest_reported_verified`; it is **not** a verified rollback or production
readiness. Passing standalone check records can only report
`checks_reported_passing`; they are **not** proof of independent production
operational acceptance. The protected root-published readback adapter validates
actual LKG identity, drift and breaker state and reports `evidence_present`
only as a nonauthorizing observation. The native Release Manager continues to
own rollback readiness, exact-source admission, deployment, and final
operational acceptance. No output of these shadow services may mint owner
approval or close an Autotask/production work item independently.


## Mandatory ticket-processing continuity: NO-GO release invariant

The Owner explicitly requires that PMV3 separation **must not interrupt or
regress live service-ticket processing**. This is a hard release and cutover
boundary, not merely an advisory dashboard metric. The current ticket runtime
(`jason-runtime` / Autotask governed capabilities) and the separate PMV3
engineering-support queue must not be conflated. The old engineering pipeline
includes `support_repair` and `todo_intake`; disabling it is not proof that
runtime ticket autonomy is safely unchanged. The new replacement engineering
lanes remain uninstalled until source admission and ticket continuity pass.

Before any worker activation or migration of PMV3 responsibility:

1. **Prechange live baseline:** Use existing governed read capabilities to
   verify at least one known active controlled ticket, notes, queue, current
   state, relevant device association, and the functioning runtime/MCP worker
   health/status. Preserve exact readback correlation and timestamp without
   committing customer data or secrets to GitHub. Record waiting/blocked work
   separately from healthy work; a read-only success alone is not proof of
   ticket-processing functionality.
2. **Controlled transactional proof:** Use a preapproved test ticket (XYZ Test
   Company), verify its current reversible field, perform exactly one
   governed, authorized update/note through the active release's tool/approval
   path, and verify post-write readback. No customer production ticket should
   be modified just to certify this redesign. Validate queue movement,
   status, priority, notes/customer visibility, device association, and
   notification/alert routing as applicable, without due-date assumptions.
3. **Ticket worker correctness:** Run existing ticket create/update/internal
   note and autonomy worker claims/retry/recovery tests. Verify no duplicate
   ticket actions, ownership claims, provider writes, or closures from shadow
   services. Include real workflow receipts for customer-updated reactive
   tickets, Jason-queue tickets, Datto EDR/AV, BackupIQ, VulScan, and DRMM
   alerts where the capability is in the release's actual scope.
4. **Safe cutover:** Do not disable the existing ticket intake or runtime
   processing path. Do not activate independent support/development lanes
   until replacement scheduling and claims are proven in isolation and the
   production ticket runtime is healthy. Migrate one responsibility at a time
   using shadow comparison rather than two competing writers.
5. **Postchange acceptance:** Require at least two independently timestamped
   observation cycles, the same governed ticket-read/note/queue tests,
   expected worker scheduling, no unexpected stalled ticket backlog, and no
   duplicate actions. Missing, stale, unknown or failed evidence is **NO-GO**,
   not an assumed PASS. Retain the original ticket controller until the new
   route is verified; on regression stop new workers and use the authorized
   exact-release rollback process. No unapproved production changes.

Pre-release test evidence should include the existing suites under
`implementation/runtime_service/tests/test_autotask_ticket_update.py`,
`test_autotask_internal_note.py`, `test_autonomy_worker_supervisor.py`,
`test_autonomy_indeterminate_recovery.py`, `test_autonomy_targeted_wake_runtime.py`,
`implementation/mcp_service/tests/test_ticket_work_claim_store.py`, and the
canonical ticket-read/queue parity tests. The existing `SEC-007` workflow also
covers Autotask mutation authority regressions. These checks are additive to,
not substitutes for, provider-backed operational acceptance.

As of the 2026-11-04 live read-only inspection: `jason-runtime` was healthy;
the governed `service.ticket.search` for an existing ticket and
`service.ticket.notes.search` both succeeded, and the separate autonomy status
showed waiting/blocked tickets. This **does not prove end-to-end ticket
processing or closure**, so the release remains ineligible for ticket-runtime
cutover pending controlled transaction and independent post-change evidence.

### Ticket continuity evidence preflight (non-authorizing)

`tools/ticket_continuity_evidence_review.py` is a bounded source-only reviewer
for the pre/post ticket evidence package. It requires a controlled XYZ Test
Company ticket identity, exact candidate/rollback revision, governed
before/update/after receipts with digest references, and at least two distinct
postchange observations with complete intake, queue, ticket-read, note,
controlled-write, claim-idempotency, alert-routing and notification surfaces.
A malformed, missing, duplicated-claim, lost-intake, stale, or partial receipt
returns `blocked`. The strongest permitted result is
`evidence_review_required`: the native Release Manager must still
independently verify the authenticated provider evidence, exact owner approval,
no duplicate provider actions, and actual production ticket processing. Source
fixture data, self-asserted booleans or hashes alone do NOT confer authority.
The tool never writes tickets or providers, moves queues, or changes production
release state. There is no synthetic acceptance or installation path in this
branch; ticket cutover remains prohibited until the native authority approves
its exact SHA and validates the ticket continuity proof.

### Native Stage A implementation: disabled provider-health only

Source-only staging is now implemented in
`tools/stage_isolated_provider_shadow_units.py`, called exclusively from the
native root `reconcile_production_host_services.sh` while processing an
immutable exact-SHA approved production candidate. Two canonical **system**
unit files (`jason-isolated-provider-health.service` and `.timer`) are staged
as disabled, permitted-but-not-required units. This does **not** launch
provider health probes, touch ticket intake or activate any independent
engineering lane. The stage fails closed for unexpected existing unit bytes,
symlinked/active/enabled units, absent sources, invalid policy/manifest or
source revision mismatch. The LKG-compatible candidate-only unit delta
planner can remove exactly these two files on rollback. The first-stage
container/ticket runtime remains unchanged and the original engineering owner
pause remains in force until a later admitted, verified lane handoff.

No production staging has occurred by merely merging this source; deployment
still requires the full protected-main release-scope review, explicit Owner
exact-SHA authorization, native rollback checks and ticket-continuity
verification. Enabling timers is explicitly outside Stage A.
