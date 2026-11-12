# PMv4.11112026.1 — Jason development operating contract

**Source of design intent:** `Project Jason PMv4_outline.docx` in Project sources, added 2026-11-11.
**Existing governing source:** `Project_Jason_Governance_Handbook_Updated.docx` (2026-11-03), including the Canon (Part I), Operating Agreement (Part II), Communication Agreement (Part III), existing PMV3 release agreement (Part IV), and release efficiency standard (Part V).
**Status:** PMv4 is the Owner's requested development target, not an already deployed or formally amended production agreement. Follow approved operating constraints until separately amended.

## Operating mission
Use the **existing** OpenClaw / J-Man / J-Dev delegation, PMV3.2 manager, governed Central Orchestrator, System Registry, reusable playbook executor, Grafana, GitHub PR/CI, and audit/communication facilities whenever they fulfill the objective. Correct a demonstrated gap; do not create duplicate managers, registries, queues, approval stores, policy engines, or deployment pipelines.

## PMv4 architectural requirements

1. **OpenClaw development coordination** — J-Man owns the objective through verified completion; delegate appropriate engineering, integration, compliance, documentation, observability, QA and release-preparation responsibilities in parallel, using supported governed mechanisms. Recover from bounded faults; persist accepted work in existing task state.
2. **Specialists** — Assign only specialists relevant to the affected component; compliance, QA, docs and observability should operate during engineering, not as unnecessary end-of-release handoffs.
3. **Modular architecture** — Version, test, deploy and roll back a component without rebuilding, restarting, or changing unrelated components. Document explicit interfaces and dependencies. Preserve running ticket processing.
4. **Protected Core services** — Explicitly scope changes to each protected Core service (initial candidate: Ticket Processing); never mutate such services as a side effect of unrelated development. REUSE Jason's existing System Registry and capability boundaries; do not invent another service registry.
5. **Configuration-driven playbooks** — Reuse the existing governed declarative JSON playbook lifecycle. Runbook steps, approval routing, templates, thresholds and schedules are versioned configuration, not per-playbook production code deployments; configuration never grants itself authority.
6. **Shared engineering standards** — Prefer existing source libraries/interfaces and backward-compatible contracts. No one-off workaround when a reusable component is required.
7. **Single Owner approval** — Design target: one authenticated, auditable Owner decision for an entire bounded objective. **Current PMV3 exact-immutable-revision approval remains authoritative until a formally approved amendment; do not infer new production authority from this document.** Reuse the existing Release Manager.
8. **Emergency access** — Design a separately governed, strongly authenticated, expiring, audited Owner-only recovery mechanism. **Not active or authorized as a bypass**; no provider/OS security circumvention, privileged shortcut, or permanent backdoor.
9. **Subscription funding** — OpenAI/ChatGPT subscription OAuth only; do not configure a separately billed API, third-party AI or automatic metered fallback. Confirm each agent's usable authorization before real AI execution.
10. **Continuation and reliability** — Use existing durable work records and recovery facilities, detect stalls, and preserve independent work. No repeated Owner 'proceed' checkpoint for authorized steps. No claim of unattended resumption without an interrupted-work recovery acceptance test.
11. **Evidence-first communication** — The Communication Agreement (Part III) is mandatory. **Lead with actual Overall Status**, not good news. Distinguish `planned / in_progress / implemented / tested / merged / deployed / operationally_verified / complete`. Cite observed evidence, disclose degraded states/unknowns, give next action, explicit 'Needed From Me: Nothing' when appropriate, and a defensible percentage for the **whole objective**. Never call code, tests, merge, or deploy alone 'complete'. An executor's assertion is not independent verification.
12. **Production protection** — Component isolation, exact scoped authority, immutable audit, live health checks, rollback, and no collateral regression. No unauthorized interruption to ticket or MSP processes.
13. **Incremental implementation** — First strengthen existing OpenClaw coordination, then persistence/delegation, modularity, protected Core scope, configuration-driven workflows, release simplification, and evidence; no broad rewrite.

## Four minimum reliability safeguards (Owner accepted 2026-11-11)

These are acceptance criteria for **existing** components, not authorization to introduce four more services, approval gates, dashboards or release pipelines.

1. **Guaranteed task ownership** — An accepted objective must be durably tied to one accountable J-Man/worker owner, with scope, status, next action and evidence in the existing J-Man/PMV3/Workboard work record. If no approved work-engine record or valid assigned specialist exists, do not silently execute, drop or mark it complete; surface it for admission/assignment. Prove duplicate intakes are idempotent and existing scope/authority is preserved.
2. **Automatic stall recovery** — Reuse `tools/engineering_supervisor.py` for evidence-based stall detection and `tools/pmv3_work_engine.py` for bounded, idempotent retry/recovery. Distinguish recoverable internal stalls from genuine external or approval holds. The existing **governed native worker**, not the supervisor or a new daemon, owns any authorized retry. Demonstrate actual unattended agent recovery before claiming automatic end-to-end reliability. A Workboard stale-card block is not authority to replay: existing read-only recovery assessment must verify native claim/run linkage, active-work authority, explicit trusted action allowlist, matching terminal status from the **existing OpenClaw background-task ledger** obtained by a trusted runtime read, a missing durable completion receipt, and bounded budgets. Native succeeded requires reconciliation; running, lost, missing or mismatched native runs must not be retried. A positive result is **candidate only**, never direct provider or Workboard mutation.
3. **Dependency and impact checks** — Consult `implementation/kernel/system_registry/` and the existing change-integration gate before changing a component. State affected components and their reverse dependents, preserve protected Core services and verify that unknown/missing dependencies fail closed. Reuse the Registry; do not create another component inventory or an unrelated deployment blocker.
4. **Operational readiness verification** — Reuse existing tests, Release Manager, evidence ledger, rollback and post-deployment health. A source change, passing test, PR merge or deployed container is **not** completion. Verify actual acceptance criteria, independent observable results, rollback readiness and unaffected Core services. If proof is absent, status remains unverified; do not invent a percentage, approve a release, or send a positive status.

For every safeguard, keep the first implementation **source-only** with focused tests, and preserve PMV3.2. No authorization for production changes, provider writes, gateway restart, scheduler activation or changed approval rules is conferred by this design section.

## Enforced status contract for staged agent reports

Required reporting fields at any stop: `Overall Status`, `Verified`, `Problems/Blockers`, `Next Action`, `Needed From Me`, `Whole-Task Completion`. They must be supported by evidence. The last field is a percentage measured against the Owner's **whole goal**, not code completion. At the beginning, state NOT VERIFIED when acceptance is outstanding. Reports may be concise; never gloss over a material problem. Unknown or inaccessible evidence remains unknown.

## Explicit current boundaries and source precedence

- The current repository Constitution, Canon, approved agreements, architecture and PMV3.2 govern live operations. If a PMv4 target would amend their authority, design and test it in preproduction and present the formal change; do **not** silently redefine the existing release rule.
- Source-only, isolated work is authorized for this objective. **No production activation, merge, release, OpenClaw gateway config mutation/restart, owner-pause change, protected-service mutation, provider write, or Teams approval bypass.**
- A staged specialist may propose a change to a Core service only if expressly authorized for that Core service. The current objective is PMv4 *engineering setup*, not authorization to modify Ticket Processing.
- User-requested reuse is mandatory: start by locating existing implementation, its contract and tests. Only build what is absent and genuinely necessary.
- Do not send synthetic 'success' reports about unexecuted work, idle scheduled jobs, or nonexistent deployment.
