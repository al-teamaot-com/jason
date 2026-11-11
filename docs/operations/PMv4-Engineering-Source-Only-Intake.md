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
