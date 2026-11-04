# PMV3 baseline scope review — 2026-11-04

**Status: BLOCKED_SCOPE. This is an evidence inventory, not authorization.**

## Exact immutable identities

- Existing production last-known-good (LKG): `1b28ddc9863aee563755cb57599cf211ee82ac19`.
- Protected-main baseline candidate: `4200ac8c011d147d89812161cb5730bd5c496841`.
- Proposed isolated-service engineering branch (not merged): `feature/pmv3-service-separation-20261104`.
- Native baseline release record: `release-4200ac8c011d147d`; state `production_eligible`, preproduction `acceptance_passed=true`, rollback SHA as above.
- Native manual scope digest: `83ea7ba6cc099b153cbc5c7bdaa932210be57305b0fe473b749fa9a2a5ae3b9c`.

## Unresolved release-scope review

Native `tools/manual_release_scope.py` reported `BLOCKED_SCOPE` for the whole exact protected-main candidate relative to LKG. The snapshot contains 78 first-parent commits (264 Git commits in the full ancestry difference), 55 changed files, **40 open PRs overlapping candidate-changed files**, and **four dirty, unreviewed development worktrees**. It inspected 142 open PRs and 279 present worktrees, with additional Git-verified stale registrations. None of the overlapping PRs/worktrees has been treated as reviewed or approved merely because it was enumerated.

Read-only overlap grouping (a PR may be counted in multiple categories): 27 PRs touch runtime source, 10 touch MCP, 10 touch release-control paths, 4 touch host units, and 3 touch other paths. These are not safe-to-merge categories and not proof of semantic conflicts. In particular, the baseline modifies `jason_runtime/autonomy_worker_runtime.py`, `autonomy_worker_supervisor.py`, `composition.py`, and `jason_mcp/server.py`, all sensitive to ticket processing.

The four unreviewed dirty worktrees:

1. `owner-approved-development/issue-1252` — modifies ticket/autonomy worker runtime source.
2. `owner-approved-development/issue-1252-recovery-b80f0863420a` — modifies ticket/autonomy worker runtime source and tests.
3. `recovery-expired-card-renewal-2228` — modifies Production Manager/controller and tests.
4. `todo-607-approval-resume` — includes unresolved merge state in `autonomy_worker_runtime.py` and modifies autonomy/composition/playbook approval paths.

**Do not reset, force-checkout, delete, prune, auto-acknowledge, or merge these worktrees merely to clear this gate.** Release review must preserve unrelated development, inspect source conflict and ownership evidence, and explicitly acknowledge any overlap before native promotion.

## Verified evidence already obtained

- Native baseline preproduction: runtime and MCP image digests verified, failure-path checks and isolated writable-state tests passed, rollback readiness passed; the candidate reached `production_eligible` without deployment.
- Source-only service PR tests: 421 local unit/integration tests plus 7 subtests; all six GitHub workflows PASS on source SHA `86067bfd0b3a679dae90dbc1212f879387db81c8`.
- Eight independent services completed two disposable preproduction cycles with zero production provider writes or runtime changes.
- Governed live Autotask search/read/notes path available. The existing runtime container was healthy; native production drift PASS and circuit breaker CLOSED at observation. This is not proof of end-to-end ticket processing.
- A bounded `ticket_continuity_evidence_review.py` preflight rejects missing test-ticket authority, duplicate claims, lost intake, stale/partial evidence, and missing routing/notification coverage. Even a complete receipt is `evidence_review_required`, not a production approval.

## Remaining mandatory release sequence

1. Complete risk review for the 78 first-parent commits and 40 overlapping open PRs; preserve and resolve or explicitly acknowledge the four dirty worktree conflicts with actual source evidence. Verify scope digest again because production review evidence is time-sensitive.
2. Re-run native whole-scope impact review until it reports `SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED`; no fabricated approvals or blanket acknowledgment.
3. Present the exact baseline SHA, all included scope, provider/ticket continuity acceptance, native preproduction evidence, and verified LKG rollback SHA for **new, explicit exact-SHA production authorization** through the approved channel.
4. Only after baseline production verification and native PMV3 lock reconciliation may PR #2301 be integrated into protected `main` through its required gate.
5. Build the new merged exact-SHA release candidate; independently validate all immutable host-unit/source artifacts and rollback; obtain its own exact-SHA deployment authorization.
6. Perform staged migration with no competing ticket writers. Before any ticket-related worker cutover, verify a controlled XYZ Test Company ticket update using approved governed write/readback, queue/notes/intake/claim/idempotency, alert routing, and notifications. Require two post-change observations and fail closed on anything missing. Never equate healthy read APIs with an end-to-end acceptance result.

## Authority limits

Project Jason's production freeze, protected-main gate, single production transaction, root readback and breaker, immutable LKG rollback, human exact-SHA authorization, and non-disruptive-endpoint rules remain mandatory. No separate service currently has production authority. No deployment or permission expansion is recorded by this document.

## Follow-up metadata-only review of overlapping open PRs

All 40 PR numbers identified by the native impact scanner were looked up using the live GitHub PR metadata API. They remained **open and unmerged** at that inspection. Some were draft; others had unresolved mergeability. Several target intermediate feature branches instead of `main`; therefore a source list alone does not establish that they are eligible for a protected-main integration. This inspection verifies **identity and status only**, not patch correctness, safe concurrency, or a release-scope acknowledgment.

Notable ticket processing/authorization overlaps requiring explicit source-level review include #775 (autonomous ticket admission and worker reliability), #855/#1022 (VulScan follow-up and customer notification behavior), #1110 (playbook approval resume), #1177/#1311 (notification checkpoint behavior), #2125/#2128 (governed routine Autotask/IT Glue write integration), and #2158 (mandatory Autotask pre/post canary and release safety). Release orchestration overlaps include #1112, #2153, #2156, #2279, and #2299. Other open PRs cover portability, metadata and provider reads, Windows Time pilot, KFS, and engineering TODOs. These are illustrative risk groups; **all 40** must be accounted for by the authoritative native review.

Branch-target concerns include #778, #804, #806, #811, #1555, #2122, #2129 and #2138: their bases differ from protected `main`, so their changes must not be silently reinterpreted as already integrated or approved. Draft status and `mergeable=true` are not substitutes for required reviews and release acceptance.

A status/metadata review does **not** resolve the four dirty worktrees. In particular, `todo-607-approval-resume` has an unresolved merge in the ticket autonomy runtime. No automatic stash, abort, reset, prune, merge, or acknowledgment was performed. Native `BLOCKED_SCOPE` remains authoritative until complete source-level reconciliation and explicit review receipts exist.

## Native host-installer cutover dependency (verified read-only)

The current native `tools/reconcile_production_host_services.sh` calls
`install_support_repair_host_worker.py --activate`, requires the
`jason-support-repair-worker.timer` to be active, and verifies exact worker
source equality against the managed production revision. The current
`config/production-desired-state.json` permits/requires the monolithic
support-worker units, not the proposed independent lanes.
`tools/reconcile_managed_unit_delta.py` recognizes canonical user unit sources
under `infrastructure/openclaw-operations/systemd/user` and
`infrastructure/showcase/systemd/user`, not yet
`infrastructure/isolated-services`; its automatic removal bound is eight
units. Therefore **source-only unit definitions do not imply that the native
release can install or roll them back**. Installing new timers manually or
replacing the monolithic worker without a reviewed native host-manifest
migration risks competing job claims, source drift and ticket/support
processing interruption.

A required separately reviewed staged design must first prove the native
source-policy/installer contract for new units with **all new timers disabled**,
without reactivating the old monolithic engineering loop during the Owner
pause. Then prove a nonmutating shadow/readback stage and rollback coverage
for each added unit. Only after an independent ticket-continuity gate and
one-writer handoff may any support/development lane be activated. Unit
rollback cardinality must remain within the native eight-unit bound or be
split into sequential, individually reversible releases. The protected-main
scope lock, owner exact-SHA authorization and root desired-state protections
are not waived by this architecture note.

## Stage A root-installer integration prepared, not deployed

The service-separation branch now includes a narrowly scoped root-owned
staging helper and exact two-unit disabled provider-health service/timer
under the native LKG-recognized systemd source directory. The desired-state
policy lists the units only as allowed. The native reconciliation shell
invokes the helper within the exact-SHA release transaction, never outside it.
The code contains explicit no-activation and rollback compatibility tests.
This does **not** satisfy the unresolved 78-commit/40-PR/four-worktree
production scope gate or constitute a license to activate the service.
Subsequent independent engineering lanes will need separate admission and
ticket-continuity acceptance rather than being bulk-enabled.
