# PMv4 — PMv3.x implementation retirement: dependency audit and remediation plan

**Audit:** November 11, 2026; read-only live Jason host, protected GitHub `main` SHA `690250b4d21f32cce79cab9f5b4c18cf93e7e94a`.
**Owner decision:** Ticket Processing and Runbook Management must operate independently of the Production Manager. Continue development with ChatGPT + Desktop Commander + GitHub; J-Man/J-Dev remain optional, subscription-only Codex agents. No paid AI/API fallback.
**State:** This is a **source-only retirement plan**, NOT production retirement, a release approval, a change to PMV3 governance, or a command to disable services.

## Executive finding

PMv3 is not one daemon. It is a coupled collection of the engineering controller, timers, release runner, Owner-approval processing, root trust/reconciliation, rollback/incident recovery, state files, and reporting interfaces. Deleting `pmv3_*` code or disabling `jason-release-manager.timer` now would leave existing production release and recovery controls incomplete. The safe objective is **replace the running implementation and its dependants with smaller governed components, prove parity, then retire the old schedulers/artifacts while archiving historical evidence.**

### Confirmed live dependencies and disposition

| ID | Dependent function / exact live evidence | Connection to PMv3 | PMv4 disposition / replacement |
| --- | --- | --- | --- |
| D01 | User `jason-support-repair-worker.timer/service` (timer enabled; service skipped by Owner-pause file), installed `pmv3_engineering_controller.py` and `pmv3_worker_release_gate.py` | PMv3 controls development, support-repair, TODO intake, integration/retry and pipeline supervision | Independent governed engineering work-item worker and durable progress receipts; ChatGPT/Desktop Commander is primary; J-Man/J-Dev optional only; retire legacy controller/timer last |
| D02 | User `jason-release-manager.timer/service` (timer enabled; active condition held), installed `release_manager_host_runner.py` | Source checkout, build, preproduction, signed deployment, freeze, LKG and rollback currently share PMv3 runner/state | Separate **PMv4 Release Controller** using exact Owner decision, manifest, bounded transaction, independent component deployment and rollback; preserve all safety checks |
| D03 | User `jason-release-approval-only.timer/service` (enabled; last run succeeded) | Approval request/receipt processing invokes the same legacy `release_manager_host_runner.py`; mobile release workflow reads its state | Independent Owner authorization service + one-time exact action receipt, no Teams dependency; don't remove before live replacement and back-compat readback |
| D04 | Root `jason-release-host-reconcile.path/service`, `jason-release-control-transition.timer/service`, `jason-release-control-readback.timer/service` | Root host mutation, signed control state and approved freeze/release transitions depend on current PM state and helper scripts | PMv4 root-owned **host/release boundary** with the same controlled locks, LKG, freeze and audit; never bypass with direct shell; safely migrate service owner/config, then retire legacy units |
| D05 | Root `jason-production-drift-watchdog.timer/service`, `jason-boot-recovery.timer/service`, user `jason-self-heal-watchdog.timer/service` | Drift/recovery and convergence checks reference PMv3 runner, release timer, transaction lock and policy files | Preserve continuous safety monitoring. Change source-of-truth to new component-registry/PMv4 release state after dual-read proof; remove only obsolete PMv3-specific assumptions |
| D06 | `jason-runtime` healthy; ticket worker is a supervised child of HTTP runtime and uses `autonomy-operational-work.sqlite3` | Not invoked by PMv3 controller directly, but shares runtime deploy/restart scope with unrelated releases | **Protected Ticket Processing Core**: reuse the existing worker, ledger, approvals and supervisor; independent process/container lifecycle and rollback; one-worker exclusive ownership/lock, zero duplicate claims, two distinct successful scans |
| D07 | MCP `jason-mcp-pilot`, `_pmv3_engineering_snapshot()`, `jason_mcp_status()` | Operations status reads PMv3 controller state, presents `pmv3_engineering` and legacy integration queue | Keep MCP capabilities unaffected. Add versioned PMv4 status source/compatibility view, segregate ticket status from engineering, eventually retire PMv3-only snapshot with consumers migrated |
| D08 | JSON runbooks: `jason_mcp` playbook tools, `SQLitePlaybookRegistry` (live generation 0); legacy Markdown/code playbook registry | JSON definition lifecycle is already hot-load and does **not** require PM release; new code engine/legacy playbook changes still use shared production release | **Runbook Management** as separately maintained control plane using existing JSON registry, validated immutable versions, transactional audit, owner-governed activation. Migrate legacy playbooks individually; do not create a second registry |
| D09 | Runtime `mobile_release_approval.py`, `autonomous_completion_notification.py` and release notifications | Owner approvals and notification outboxes read `/var/lib/jason/openclaw/release-manager` and legacy service principal | Rebind to PMv4 exact-release authority/notification service; preserve live Owner identity, exact-action evidence, audit and signed receipts; eliminate Teams-only cards |
| D10 | `operations_configuration_exporter.py`, `operations_configuration_metrics.py`, `production_health_exporter.py`, Grafana panels; live exporters | Dashboards, alerts and health probes read PMv3 release records, drift and schedule state | Versioned read-only compatibility projection for old history and new PMv4 component status; transition alert source and Grafana panels without losing history/coverage |
| D11 | `config/production-desired-state.json`, `config/release-manager-policy.json`, `config/open-breaker-recovery-policy.json`; installers and `tools/reconcile_production_host_services.sh` | Desired-state **requires** the old release, approval and support-repair timers; root reconciliation asserts installed PM helpers match source | Modify protected desired state **only after** replacements are proven; stage exact old/new unit delta in governed release, preserve byte-for-byte unit archive and deterministic rollback |
| D12 | Work/TODO/PR pipeline (`engineering_pipeline.py`, `owner_approved_development_worker.py`, `pmv3_integration_queue.py`, `todo_release_bridge.py`, `release_breaker_recovery_manager.py`) | PMv3 state/admission, shared release locks and pipeline handoff can stall unrelated development/commitments | Separate durable work intake and one-owner claim from release. GitHub PR/CI remains authoritative. Use existing tools via adapters, not duplicate engineering engines; swap PMv3 gates to generic guarded work/transaction gates |
| D13 | `infrastructure/isolated-services` proposed support/TODO/development/supervisor units | Source-only candidate deliberately references `pmv3_worker_release_gate.py`, and requires old ticket continuity evidence | **Not currently installed.** Rework or supersede before installation; never activate both old and new workers concurrently |
| D14 | Provider health canaries, DNSFilter boundary reconciliation, KFS collector, monitoring exporters, OpenBao/authority integrity, core MCP tools | Live service instances exist but are **not all PMv3 dependants**; many share only production release protection and/or standard host scheduling | Preserve as-is until independently reviewed; avoid an indiscriminate PMv3 teardown or bulk redeployment |
| D15 | `JASON_PM_V2_CONTROL_PROFILE` live runtime variable and historical CCC/Teams records | PMv2 or historical governance artifacts may coexist; not proof of a live PMv3 runtime dependency | Inventory separately, preserve history and rollback compatibility. Do not delete by name matching |

### Protected policy/source evidence

- `config/production-desired-state.json` marks `jason-release-manager.timer`, `jason-release-approval-only.timer`, `jason-support-repair-worker.timer` **required user units**, plus root release readback/transition/reconciliation/drift units **required system units**. Removing them without a governed desired-state transition creates drift.
- Live `jason-runtime` and `jason-mcp-pilot` use protected revision `690250b4...`; OpenClaw gateway also healthy. This verifies service availability, **not** successful ticket remediation.
- The live ticket worker reports its own scan and durable ledger. Earlier MCP readback: 39 waiting, 41 blocked, zero eligible now; do not misclassify as a PMv3 timer failure.
- Live PMv3 engineering Owner-pause file exists; promotion incident hold exists; **do not erase either** as part of this engineering plan.
- The existing isolated-services manifest explicitly sets `production_deployment_authorized=false`. It cannot be treated as a deployed PMv4 alternative.
- Historical CCC retirement source is in `docs/operations/CCC-Legacy-Retirement-20261110.md`; its preserved audit/rollback data remain independently relevant. PMv4 retirement does not authorize removal of CCC evidence.
- The signed Owner exact-revision and emergency controls, tenant isolation, provider permission gates, protected freeze, LKG, source attestation, independent Core health, rollback and immutable audit are **governance requirements**, not PMv3 implementation features to discard.

## Ordered remediation / release plan

### Phase 0 — Pin the contract and baseline (no production change)

1. Establish PMv4 service ownership inventory: **Ticket Core**, **Runbook Management**, **PMv4 Release Controller**, **Owner Authorization**, **Engineering Work**, **Host Recovery/Drift**, **Observability**, **Provider Connectors**.
2. Name the PMv3 live/source dependency for every installed unit, filesystem writer, state consumer, secret mount, API tool and alert. Tag each as `replace`, `retain`, `compatibility` or `history` (D01–D15 above). Include user, root and container lifecycles.
3. Capture exact protected production SHA, deployed images, service/timer states, hold/freeze bytes, required/allowed desired-state unit lists, provider/auth status, ticket scan, ledger backup, runbook generation and monitoring baseline.
4. Reconcile any existing PMv4 PR stack against protected `main`; no duplicate release engine or second ticket ledger.

**Exit:** Accounted inventory, compatibility consumers and signed baseline; no production mutation.

### Phase 1 — Protect operational services (highest priority)

1. Stage independent **Ticket Processing Core** from the existing `jason-ticket-autonomy` runner, SQLite work ledger and supervisor. New source must default to old embedded mode. Introduce one same-inode, cross-process exclusive owner lock before a separately hosted worker may be activated.
2. Prove a controlled admission/claim → deterministic diagnostic → wait/recheck/verify path, including process termination recovery, no duplicate ticket/job, correct zero/one active owner, provider readbacks and two separate successful scheduled scans.
3. Make **Runbook Management** a configuration/data service using the current JSON registry. Verify validate/stage/activate/retire with identity, fingerprint, atomic receipts, hot-reload and rollback while PM engineering is paused. Migrate Markdown/code runbooks one at a time after parity tests; don't remove old runbooks prematurely.
4. Update the protected-Core inventory so unrelated PM/release changes cannot replace/restart Ticket Core or modify its state; preserve independent read-only health and escalation.

**Exit:** Both operational services continue when PM engineering/release service is intentionally unavailable in the lab; no provider writes needed for simulated tests; production proof requires bounded governed acceptance.

### Phase 2 — Independent governance and host controls

1. Reuse existing signed exact-Owner approval, identity and per-provider policies in a PMv4 authorization boundary. Prove Teams is optional; keep production emergency override short-lived, one-use, auditable and scoped.
2. Migrate root-owned release control, transaction lock, production freeze, protected LKG, drift/boot/self-heal and release-host reconciliation to a **component-scoped** controller. Verify identity, source SHA, reviewed file scope, image digest, rollback SHA, source/host integrity, and protected service exclusions *before* changing host state.
3. Split notification/approval *delivery* from actual authority and mutation. Migrate runtime/mobile approval and outboxes to versioned PMv4 event receipts with backward-compatible read-only lookup.
4. Prove a totally isolated shadow component release (no network, provider writes, production mounts, borrowed API keys or unapproved restart) plus exact rollback, without touching Ticket Core.

**Exit:** PMv4 can govern an independent low-risk shadow component end to end; original PMv3 release path remains available as verified rollback until subsequent acceptance.

### Phase 3 — Replace PMv3 engineering and release scheduling

1. Use ChatGPT + Desktop Commander + GitHub for approved engineering work. Keep J-Man/J-Dev optional under existing ChatGPT OAuth; **no separately billed Codex/API tokens**, no metered fallback.
2. Create separate resumable **Engineering Work** claim/retry and integration processes from existing PMv3 adapters. Preserve durable ownership, idempotence, receipts, authorizations, PR gates and approved commitments; never double-run legacy and replacement job families.
3. Migrate `release_manager_host_runner.py` functionality into PMv4 component-scoped release orchestration through existing proven source helpers, rather than bypassing governance. Allow independent version/rollback per component.
4. Transition old release-approval, release-manager, engineering timers and root host helpers in a **single governed, exact-unit-delta release** only after PMv4 replacement parity and preserved LKG are demonstrated. Do not modify the protected desired-state list early.
5. Rebind MCP status, Grafana/exporters/alerts, TODO/work commitments and Owner notifications. Keep legacy data readable until all consumers are moved.

**Exit:** A new PMv4-governed authorized release can be prepared, signed, deployed, verified and rolled back without executing the PMv3 engineering controller or legacy release manager. Protected Ticket Core does not restart.

### Phase 4 — Controlled PMv3 decommission and final proof

1. Obtain appropriate **exact production-revision/rollback/scope Owner release authorization** after current governance's formal PMv4 amendment is reviewed. An overall objective approval is not a blanket permission to bypass the present release freeze.
2. Quiesce old PMv3 work claims, archive queue, approval and release receipts; wait for any in-flight native provider jobs and release transaction locks to reach a stable state. Preserve historical immutable records.
3. Apply exact source/desired-state retirement of the PMv3-only user timers, obsolete root helper units and policies after verifying their PMv4 successors are running and the new drift policy explicitly permits the delta. Do not remove unrelated systemd units.
4. Run independent acceptance: protected Core continuity, controlled runbook lifecycle, authenticated Owner exact-action release + rollback, provider read canaries, status/exporter continuity, no duplicate claims/notifications, no unauthorized paid AI route, no production regression, freeze state restored.
5. Observe **two or more** distinct post-cutover ticket scans and the independent component lifecycle; test an unrelated PMv4 release and a bounded PMv4 failure/rollback without disturbing Ticket Core.
6. Mark PMv3 implementation `retired` only when no live timer, release, mutation path, alert, API consumer or protected desired-state entry requires it. Archive versioned executable source and recovery evidence for historical rollback; do not delete authority/audit history.

**Exit:** Independent Ticket Core and Runbook Management proven, PMv4 release/approval/recovery proven, PMv3 runtime/source dependencies at zero, verified rollback and monitoring retained. **Retirement not yet achieved.**

## Critical NO-GO checks

- Any unknown or unaudited installed PMv3 consumer, missing auth/scope evidence, or protected policy mismatch.
- A second ticket worker using the same durable ledger without a proven lock; an old worker that does not honor the new lock; or an attempted ungoverned direct provider action.
- PMv4 release or rollback that stops/rebuilds the protected ticket worker or suppresses alerts.
- A runbook/configuration change that grants its own execution authority, loses version history, or bypasses owner approval for activation.
- Unavailable independent rollback SHA, freeze evidence, required CI, ticket readback, integrity/audit or root service health.
- Authentication fallback to paid OpenAI/API-key or other subscription services.
- An alleged test result based only on Docker/HTTP health without a real functional receipt.

## Delivery work already underway (preproduction only)

- Ticket Core: source-only embedded/external hosting mode, single-owner file lock and standalone worker entrypoint; separate PR will supply controlled test evidence.
- Runbook Management: fixes atomic SQLite registry lifecycle and adds immutable versioned actor/fingerprint/generation receipts; separate PR will supply controlled tests.
- Standalone PMv4 shadow release: draft PR #2429 and runtime inspection hardening draft PR #2435; no live deployment.
- Subscription-only recovery: draft PR #2434; Codex-backed agents optional, not a PMv4 release dependency.

**Decision needed to start planning/preproduction:** None. **Production retirement authority:** Not yet requested; must name exact candidate SHA, rollback, reviewed scope, test evidence and root-control compatibility when deployment-ready.


## Exact source/rollback evidence packet (read-only, repeatable)

Run `python3 tools/pmv4_migration_evidence.py` from the PMv4
retirement-plan source tree on the Jason host. It interrogates current
protected GitHub main, fixed PMv4 PRs #2436 (plan), #2437 (runbooks),
#2438 (ticket Core), #2440 (independent shadow release/recovery), each
PR's exact head SHA, reviewed changed file list/sha256 and **all required
baseline check names**, plus pinned production/rollback Docker image
revisions and hashes of readable Owner hold files. It makes no
production/service/provider mutations, generates no approval and
does not silently turn a draft PR into production release authority.

At the November 11 live readback, protected `main` and the deployed
`jason-runtime`/`jason-mcp-pilot` both had source
`690250b4d21f32cce79cab9f5b4c18cf93e7e94a`.
The locally tagged `jason-runtime:rollback-current` and
`jason-mcp:rollback-current` images both identify source
`ee46ef631e04678a16f2543c76a8ee08ec974265` (image labels);
this is the **available rollback-image SHA**, not an independently
verified root-protected Last Known Good record.
The Owner PMv3 engineering pause and automatic-promotion hold were
present. The protected production control-state file was **not
readable by the non-root inspection identity**, so root-signed
readback remains a release NO-GO until separately verified.
The new PMv4 host control lock and Owner trust installation are absent.

The packet explicitly reports
`exact_production_release_candidate_sha=null`,
`owner_exact_action_approval_recorded=false` and
`production_changes_made=false`. After the component PRs merge,
rerun the packet and bind the resulting single protected-main release SHA,
exact file-scope digest, final image IDs, proven rollback/Last Known Good,
freeze bytes and verified Owner authorization into the formal governed
release record. Do not present any source-branch SHA as the actual
released production revision.
