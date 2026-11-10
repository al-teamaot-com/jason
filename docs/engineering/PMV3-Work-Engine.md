# PMV3 Work Engine

PMV3 is an isolated replacement candidate for the Production Manager work engine.
It does not inherit production authority from PMV2 and is not authorized to deploy
itself.

## Agreement-driven behavior

The engine is built around:

SCAN -> SELECT RUNNABLE -> EXECUTE -> VERIFY -> RETRY/RECOVER -> RECHECK -> CONTINUE

The implementation must prove the following before production integration:

- approved runnable work continues without repeated operator prompts;
- a blocked task does not block unrelated runnable work;
- transient failures receive bounded retry/backoff and authoritative re-evaluation;
- waiting work wakes when its dependency becomes true;
- interrupted work resumes after restart;
- durable action receipts prevent duplicate execution;
- external authority/credential/billing gates remain external and are not invented;
- completion percentage describes the entire accepted PMV3 workload, not setup steps.

## Isolation

The first PMV3 implementation is intentionally handler-driven. Tests and
preproduction adapters may inject actions. No production provider worker is wired
to this engine until the scheduler/recovery acceptance suite passes.


## Approval channel

Teams is the only human approval channel for PMV3.

Approval-required work is not runnable unless PMV3 receives a verified approval
decision from Jason's authenticated Teams Approval Service / Universal Teams
Approval path and the decision is bound to the exact approval request.

The following are never approval:
- SSH or shell commands;
- local files or environment variables;
- GitHub comments or repository access;
- typed chat text such as "approve";
- direct state/database edits;
- copied, expired, mismatched, replayed or unverified approval payloads.

Teams Deny leaves the work non-runnable. PMV3 must never instruct the Owner to
SSH to Jason to approve work.


## Governed engineering continuation controller

`tools/pmv3_engineering_controller.py` is the PMV3 production-candidate entry
point for Jason's existing engineering workers. It does not replace their
provider, source, test, merge, or Release Manager gates.

Each activation runs the existing `engineering_pipeline.py`, reads the durable
pipeline and supervisor evidence, and immediately performs another bounded pass
only while the state is classified as internally recoverable and progress is
still changing.

It stops on:
- healthy completion;
- a genuine external/governed dependency;
- control-plane failure;
- two unchanged recoverable passes;
- the configured maximum of three passes.

This fixes the V2 behavior where one pipeline pass could truthfully report
`approved_work_stalled` and then simply wait for another timer/manual prompt.

The installed user service invokes PMV3 directly. The legacy governed pipeline
remains the worker executor under PMV3, preserving existing recovery helpers,
support priority, release bridge, supervisor, and Release Manager safeguards.

## Runtime and status

The engineering timer remains 24x7. A single PMV3 service activation is bounded
to three pipeline passes. The systemd service timeout is sized for those bounded
passes and does not grant additional work or release authority.

`jason_mcp_status` exposes `pmv3_engineering` from the durable controller
state so current continuation status can be verified through governed surfaces
without SSH.

## Crash and duplicate-action handling

The generic PMV3 work engine checkpoints an execution claim before invoking a
handler and supplies a stable action key. An interrupted item is automatically
replayed only when explicitly marked idempotent. Interrupted non-idempotent work
is held for reconciliation instead of being blindly executed again.

Production adapters must preserve the same stable action identity and reconcile
indeterminate provider outcomes before retrying.


## Concurrent release-safety overlap

Open PR #2158 also edits the repository-hygiene portion of
`.github/workflows/validate.yml` to add historical rollback and managed-unit
reconciliation tests. PMV3's CI change is additive: it adds a distinct PMV3
scheduler/controller acceptance step and does not replace or weaken #2158's
tests. Any later integration must preserve both sets of checks.


## Concurrent MCP server overlaps

Open PRs #2125 and #2128 also modify
`implementation/mcp_service/src/jason_mcp/server.py`, but in the routine
governed-write and onboarding-attestation paths. PMV3's server change is
status-only: it adds `_pmv3_engineering_snapshot()` and exposes that snapshot
through `jason_mcp_status()`.

PMV3 must not import, replace, broaden, or weaken the routine-write client scope,
onboarding attestation, provider credential, or approval semantics from those
branches. Later integration must preserve both workstreams.
## Governed integration and release queue

PMV3 separates concurrent development from serialized production integration. Development branches, pull-request updates, and CI may continue while a production candidate is being built or deployed. The Owner retired the previously required GitHub status context `pmv3-integration-gate` on November 10, 2026. The integration queue can retain advisory status reporting, but it must never restore or write branch protection. The eight ordinary required CI checks, strict protected-branch rules, Teams authorization, production freeze, and exact-release gates remain independent and enforceable.

The integration queue admits only pull requests backed by durable Owner-approved development evidence, or an explicitly governed `pmv3-integration-ready` label. It selects a bounded release train (default maximum three PRs), prefers higher-priority work, and batches only PRs whose changed-file sets do not overlap. The optional queue may publish selected/queued statuses for visibility only; these no longer block GitHub merges. Existing CI and review requirements still apply.

After the train is merged, PMV3 records the exact resulting `main` SHA as the production candidate and closes the integration gate for all unrelated PRs. The queue records a release lock until the exact candidate becomes the verified Last Known Good production revision; it no longer enforces that lock through GitHub branch protection. The production release freeze and breaker remain unchanged. A restart or missing queue state fails closed: if protected `main` differs from verified production, PMV3 reconstructs the release lock from observed state.

A release lock does not grant production authority. Release Manager validation, exact-revision Teams approval, deployment, verification, rollback, and production-freeze rules remain unchanged. A bounded release-recovery PR may advance a locked candidate only when it is durably admitted and explicitly labeled `pmv3-release-recovery`; ordinary development cannot bypass the lock.

Canonical queue states are:

`IDLE -> INTEGRATING -> RELEASE_LOCKED -> (production verified/LKG) -> IDLE`

Development continues in every queue state. Queue-control failure is fail-closed for merges and must not stop development.


## 2026-11-04 PMV3 recovery lock and autonomous-intake integration acceptance

This checkpoint is source-integration evidence, **not** operational PMV3
acceptance or permission to modify production.

- Protected `main` was `b905ea197f7b268828c75c01ea4407d4378d0d74`
  when queue PR #2280 was reconciled. The original queue head
  `2371b44f92cd22a2536b8b6b08f9b948bcbae4d2` incorporated that exact
  source in a clean, ordinary engineering-branch merge. It did not merge
  the queue into protected `main`. The resulting pre-documentation feature
  head was `d42d0fbd7d9c78dd31c6a86dbf028ef192b5565a`.
- This merge preserved the merged root-host proof-execution correction
  (#2295) and PMV3 worker quiescence fix (#2293). Reconciled source
  tests: **342 passed + 5 subtests**. No deployed root-helper, image,
  protected-control, user endpoint, or provider state was changed.
- The queue's implementation overlap with autonomous-intake PR #2296
  (exact preproduction head
  `c30ce45f712c6cdc06675b9d42abdd21c35bc3b0`) was explicitly reviewed.
  The changes touch the same `pmv3_engineering_controller.py` but preserve
  both queue mutex admission and bounded stall classification. The two
  PRs merge cleanly with zero unresolved files in a disposable scratch
  worktree. Their exact combined scratch source passed **524 tests and 12
  subtests**. Scratch merge SHA
  `b1b8cfc674f60c1353cf10d2be786bd4fa4c8ea4` was not published as a
  protected release or production candidate.
- Current production remains independently locked to
  `b905ea197f7b268828c75c01ea4407d4378d0d74` while runtime and MCP
  run at LKG `1b28ddc9863aee563755cb57599cf211ee82ac19`,
  `/opt/jason/current` remains on failed
  `3e06627de85ace598f959cda12e257000668864d`, and the owner freeze
  and circuit breaker remain active. The queue cannot be deployed or
  considered functionally active under this host mismatch.
- Current installed PMV3 does not contain the new integration-queue
  reconciler: a GitHub `pmv3-integration-ready` label is not evidence of
  current autonomous merge execution. The corrected TODO/triage logic of
  PR #2296 is likewise still only source-tested.
- An external GitGuardian check also flagged one finding on PR #2280's
  **pre-reconciliation** head. Independent remediation/review is required;
  new passing local pytest runs do not cancel a failing security check.
  The finding must not be printed, ignored, or treated as an approval.

### Required live acceptance after separately authorized release

1. Verify complete protected-host/runtime/MCP alignment at one exact
   authenticated production SHA, after root-helper proof recovery, fresh
   full-integrity PASS, and required independent Release Manager/CCC gates.
2. Confirm the release-lock queue can admit a bounded, approved train
   without crossing the active production transaction lock, omitting
   required GitHub checks, or granting approval to conflicting TODO IDs.
3. Observe **two consecutive complete scheduled production cycles**.
   Intake must not traceback on duplicate `TODO-OPS-013`; blocked
   identities remain quarantined; exhausted repair handoffs are accurately
   classified; unrelated approved work actually changes durable state.
4. Preserve failure receipts, provider health, no-collateral-regression
   evidence, rollback readiness, Owner freeze restoration, and a
   verifiable outstanding-to-complete work count. A running service, zero
   worker exit code, scheduled timer, or CI green check alone is **not**
   operational acceptance.

No unit, provider, permission, root policy, production hold, or release
authorization is altered by this source-only documentation checkpoint.
