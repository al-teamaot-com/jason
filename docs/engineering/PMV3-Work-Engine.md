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
