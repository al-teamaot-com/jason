# PMv4.x engineering intake — source only, 2026-11-11

**Objective:** Implement the Owner's `Project Jason PMv4_outline.docx` as the new engineering design standard, without interrupting the current PMV3.2 runtime, changing its release authority or deploying anything. The November 3 Governance Handbook's Canon, Operating Agreement, Communication Agreement and PMV3 remain controlling for live actions.

## What we must reuse
- J-Man / J-Dev already configured in OpenClaw; Nov 9 delegated source-only engineering acceptance recorded in the existing J-Man TASKS.md. Six specialist profiles staged by draft PR #2421. Reuse these agents; do not create another manager.
- The existing PMV3.2 release-manager and engineering-supervisor pipeline handle protected-source integration, release staging, rollback and audit. **No new release pipeline.**
- The existing System Registry and governed capabilities express system/component identity. Extend if necessary for protected Core declarations; **no separate Core registry**.
- The existing JSON playbook validate/stage/activate/retire capabilities already support configuration-driven runbooks. Extend gaps rather than reinvent the workflow engine.
- The existing J-Man TASKS.md, PMV3 persisted work items, scheduled jobs and pending Workboard PR #2382 are the persistence starting point. The previously observed gap is real successful interrupted-task resumption; do not claim cron scheduling itself meets that acceptance.
- The existing governance and Communications Agreement require independent evidence and precise status; use the existing report workflow rather than create a second reporting service.

## First preproduction assignment to J-Man
Perform **read-only discovery plus a written PMv4 gap-and-reuse review**, using the current main repository, PR #2421, PR #2382, and existing J-Man work record. Identify exact reused modules, authoritative dependencies and missing PMv4 capabilities. Keep proposed changes modular, beginning with OpenClaw persistence/workboard and enforcement of evidence-first status. Delegate a narrowly bounded, nonproduction review to J-Dev using existing supported sessions, if permitted by current Owner-pause constraints. Do not restart the gateway, enable Workboard/plugin, change PMV3.2 production, write providers, promote releases, merge code, unfreeze, or alter protected Core services.

## Acceptance for first assignment
1. A durable J-Man objective record identifies the Owner's PMv4 request, overall status, exact source refs, next safe action, and evidence.
2. Gap/reuse review maps each PMv4 area to a concrete existing module/service or clearly identifies the genuine missing capability; no invented systems.
3. Communication Agreement fields appear in J-Man's response: actual Overall Status first, Verified, Problems/Blockers, Next Action, Needed From Me, Whole-Task Completion. Percent counts whole PMv4 program; estimates distinguished from evidence.
4. Distinguish source-only test results from deployed operations. Independent review evidence is recorded without substituting for end-to-end acceptance.
5. Production services, PMV3.2, ticket worker, approval/freeze state and OpenClaw gateway have not been mutated.

## Known blockers that do not prevent source-only preparation
- Workboard PR #2382 remains source-only and release-locked; full unattended recovery after interruption has not been proven.
- Specialist profiles PR #2421 is a draft; source-only staging passed local tests but is not integrated or production activated.
- PMv4 single-approval / Owner emergency access requirements are design targets needing formal governance review and tested implementation, not current authority.
- OpenClaw agent subscription OAuth was verified usable for J-Man on Nov 11, but long-lived session continuity, specialist OAuth and concurrency need tests.

## Verified existing PMV3 durable-engine reuse (2026-11-11)

A disposable, nonproduction test in `tests/test_pmv4_reuse_durable_recovery.py` exercises **the existing** `tools/pmv3_work_engine.py` across different Python processes, without another scheduler, production work record, provider, API call or gateway restart:

- A deliberately interrupted **idempotent** development work item is persisted as `running`, picked up by a later fresh engine process, completed with receipt, and not executed again on a subsequent process.
- A persisted item with independently recorded completion receipt is marked complete without repeating any action.
- A deliberately interrupted **non-idempotent** action without a receipt remains waiting for reconciliation and is **not** retried or incorrectly claimed complete.

These tests demonstrate a reusable PMV3 execution primitive. **They do not** demonstrate that OpenClaw Workboard currently dispatches into that primitive, that J-Man is scheduled to drive it, or that a real agent can recover from an interruption and finish unattended. Workboard-to-engine handoff requires a governed adapter or equivalent supported dispatch, durable correlation/receipt contract, targeted tests, and actual preproduction end-to-end acceptance before PMv4's autonomous continuation can be called operational. No second work manager is proposed.

**Stop condition:** Only production activation requires further release authorization; J-Man may complete all independently authorized engineering and nonproduction tests in the meantime.

## Evidence-first reporting repair (not activated)

The existing live J-Man `status_report.py` includes dated, static claims about earlier approvals, and infers status from substring matches in `TASKS.md`. That is incompatible with the current Communication Agreement's evidence-first standard. **Do not patch or restart the running reporter as part of this source-only work.**

The candidate `config/openclaw-specialists/reporting/status_report.py` is an intended **replacement of that existing script**, not an additional service. It continues to read the existing task register and use the existing OpenClaw Teams message path. It removes hard-coded Owner routing, requires a configured private `JMAN_TEAMS_TARGET` for delivery, refuses unconfirmed sends, detects missing/stale records, exposes blocked outcomes ahead of positives, and does not turn a self-reported `COMPLETE` into an operational completion assertion without independent evidence. Unknown percentages are not invented. The proposed replacement remains offline, with targeted negative tests. It **does not independently verify** provider, ticket-worker, production or Workboard operational outcomes and must not be represented as doing so.

Acceptance before replacing the current reporter: verify the existing scheduled invocation flags, configured Owner recipient, receipt parsing and human-readable message; review the current task register's status and percentages; preserve the original reporting schedule and Teams destination; test a delivered message in an authorized sandbox; deploy only under the appropriate component-scoped release.

## Workboard / PMV3 read-only reconciliation preproduction prototype

The candidate `tools/pmv4_workboard_reconciliation.py` is a **pure read-only decision function** on the existing Workboard card schema and the existing PMV3 work-engine state. It does not create a Workboard replacement, a new scheduler, a new release/approval path, a background process, or a bridge that mutates either state store. It does not activate agents or production capabilities.

The reconciliation contract:

1. Accept only existing approved specialist agent IDs and valid Workboard lifecycle states. Never create a privileged or unbounded executor from a card.
2. Require an existing PMV3 work record for an incoming card; do **not** auto-admit, auto-authorize, or call the provider from a Workboard record.
3. Defer execution/retries to the **existing** PMV3 work engine. If uncertain non-idempotent work is waiting for reconciliation, preserve that halt.
4. A Workboard `done` state alone does not mean the PMV3 engine completed; a PMV3 `complete` state without a durable action receipt does not mean the work finished.
5. Even if the Workboard card contains a `passed` proof reference and the PMV3 engine has a durable receipt, require **separate independent operational acceptance** before calling a PMv4 objective complete.
6. Missing, malformed or unrecognized records fail closed with no provider writes, authority elevation, dispatch, or automatic retry.

Seven focused tests verify missing records, unauthorized agent IDs, divergent status, missing receipts, unverified proof, indeterminate non-idempotent work and read-only idempotence.

**Not yet proven:** a live Workboard card actually flowing into the existing PMV3 engine, creation of a correctly governed work record, J-Man subscription-backed dispatch, worker execution, crash/restart recovery, completion-proof readback, scheduler continuity and final communication. This module is an interface and reconciliation proof, **not a functioning deployed adapter**. A future accepted implementation should use the **existing** Central Orchestrator and work engine instead of granting Workboard its own provider authority.
