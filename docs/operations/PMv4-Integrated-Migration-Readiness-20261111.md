# PMv4 — Integrated source-only acceptance and governed migration gates

**Status:** Combined **preproduction-only** candidate, assembled November 11, 2026.
**Scope:** Protected Ticket Processing Core, independent JSON Runbook Management,
independent disconnected PMv4 shadow release/recovery, and PMv3 retirement inventory.
**Never infer deployment or production authorization from this branch or a green CI run.**

## Existing implementation reused and integrated

| Concern | Existing or new source | Scope and proof |
| --- | --- | --- |
| Ticket Core | `jason_runtime.autonomy_worker_supervisor`, `maintenance_process`, `ticket_worker_service`, `ticket_worker_ownership` | Existing deterministic provider/approval engine reused, optional external supervisor, persistent exclusive ledger owner lock, embedded-default compatibility |
| Ticket owner validation | `tools/pmv4_ticket_core_container_acceptance.py` | Synthetic 3 Docker scan cycles; initial owner runs two, competing process denied, next owner resumes, 1 unique claim; zero production mounts, keys, provider writes |
| Runbook Management | Existing `SQLitePlaybookRegistry`, `json_playbook_admin`, JSON schema | Transactional immutable versions, activate/retire/readback and actor/fingerprint receipts; existing Markdown/code playbooks unchanged |
| Shadow Release Controller | Existing `tools/pmv4_shadow_release.py`, `pmv4_shadow_docker_adapter.py`, `pmv4_shadow_ci.py` | Independently verified SHA, exact Owner proof, immutable scope/bundle, isolated Docker namespace, bounded receipt/rollback |
| Host safety/recovery | `pmv4_host_release_guard.py`, `pmv4_shadow_host_runtime.py` | Both legacy host transaction lock and PMv4 root lock held through release; trusted direct Ticket Core health; protected root breaker must be closed; rollback of previously signed pending transaction only |
| Migration evidence | `tools/pmv4_migration_evidence.py` | Read-only protected GitHub candidate/CI, file-scope digests, live/rollback image SHAs, root LKG, protected breaker and hold evidence; no unsigned activation |

## Canonical System Registry and protected scope integration

- Reuse `implementation/kernel/system_registry/production-registry.json` as the **single** Jason System Registry. Register `component.ticket-processing-core` and `component.runbook-management` as **proposed/preproduction/not_deployed**, not fictitious operational instances. Both have independent lifecycle ownership, canonical governance dependencies, documented verification methods and precise source globs; neither depends on PMv3.
- `tools/pmv4_component_scope.py` reads the canonical registry and denies component-scoped release of unrelated protected Core files, shared runtime/composition/MCP entrypoints, untrusted source paths or missing/altered registry entries. It does **not** mint release/Owner authority and must be combined with the existing signed exact-scope gates.
- While PMv3 remains authoritative for production, `config/release-manager-policy.json` now marks Ticket Core, JSON runbook and PMv4 host release-control files as protected source so legacy release admission cannot silently treat them as routine changes.
- Production source, installed desired-state, active System Registry and live ticket worker are **unchanged**. Promotion of either new proposed component into active status needs its own governed lifecycle event and real deployment/readback proof.

## Source integration acceptance

- Merged exact protected-main source into the PMv4 preproduction stack without merge conflicts.
- Merged Ticket Core, Runbook Management and live PMv3 dependency audit with independent shadow release/recovery controls.
- Ran combined regressions across Ticket Core, worker supervisor, runtime composition, JSON Runbook Management, independent host/Owner release, Docker adapter and scope/CI migration packet; **exit code 0**.
- Ran the separate Docker Ticket Core acceptance from the combined source. PASS: 3 synthetic scans, 1 unique synthetic claim, contender denied, recovery acquired lock. Production traffic, credentials and ticket data were not used.
- Read-only inspection independently found running production source and protected LKG
  `690250b4d21f32cce79cab9f5b4c18cf93e7e94a`,
  previous protected LKG/available rollback image source
  `ee46ef631e04678a16f2543c76a8ee08ec974265`.
- Production circuit breaker is **OPEN** for prior undeclared container drift; later drift PASS cannot authorize bypass or close it. PMv4 source guard fail-closes accordingly.

## Exact governed release order and rollback (no skips)

**Release A — isolated shadow infrastructure, NOT Ticket Core.**
1. Wait for exact merged protected-main SHA, full required CI, trustworthy root hold/freeze/LKG readback and authenticated Owner decision bound to reviewed file scope, manifest, candidate SHA, rollback SHA, and image digest.
2. Independently install trusted root PMv4 shadow control and Owner Entra proof issuer through the existing governed production release machinery; prove no shared PM host transaction in flight. Do not self-issue signers or invoke a developer-supplied bypass.
3. Sign the shadow-only **initial empty baseline** rollback `0000000000000000000000000000000000000000` (not the old jason-runtime image). Then run one disconnected PMv4 shadow release, verify signed receipt, guarded health and intentional failure/rollback.
4. The current PMv3 circuit breaker must first be revalidated and **closed through its governing recovery procedure**. Successful health checks alone are not approval.

**Release B — lock-aware embedded Ticket Core bootstrap.**
1. Review the exact new Ticket Core source SHA, current protected source `690250...` as rollback and live authority/provider/ledger/queue evidence. Requires separate protected-Core production release scope and exact Owner approval.
2. Upgrade the embedded owner only under existing governance, **without enabling an external worker**. Verify its kernel lock, current SQLite ledger, provider-backed scan/readback and no duplicate claims. Preserve existing PM and release freezes.
3. If failure, roll back only to the separately verified embedded image after ensuring the worker is fully quiesced; do not lose pending claims.

**Release C — actual external Ticket Core cutover.**
1. Prepare separate component-owned container/service and the minimal credential/data projection. The current live work ledger shares the `/var/lib/jason/openclaw` namespace; avoid broad writable PMv3 state mounts in the new independent service. A data/credential separation design, real image and host unit rollout are therefore independent required acceptance work, **not yet deployed**.
2. Stop new embedded admissions only within the authorized transaction, reconcile in-flight work, verify the old worker released its lock, then start exactly one external worker with the same authoritative durable state. If locking/mount invariants cannot be proven, **NO-GO**.
3. Verify two distinct real scheduled Autotask ticket scans, controlled test-ticket provider readback, existing ticket/waiting counts, zero duplicate notes/claims/jobs, notification outbox, MCP health and exact rollback. Only then treat Ticket Processing as independent.

**Release D — Runbook Management independence.**
1. Reuse the existing JSON registry; move its management service lifecycle out of the PM deployment boundary, retaining identity, exact Owner activation and capability gate.
2. Verify validate-stage-activate-readback-retire while PM engineering is unavailable, preserving previously accepted code/Markdown runbooks until each is migrated separately.

**Release E — remove PMv3 implementation.**
1. After PMv4 release/controller/recovery and Core deployments are live and proven, migrate monitoring/status, approval notifications, engineers' workboard, root reconciler/drift/boot recovery and historical compatibility reads.
2. Remove obsolete PMv3 services and protected desired-state entries via exact reviewed unit deltas, retaining source/receipt archives and prior LKG rollback.
3. Restore protected freeze, revalidate production-wide health and verify all work completes without PMv3 processes.

## Explicit current blockers

- None of the source-only draft PR SHAs is the **final approved protected-main production candidate SHA**.
- No trusted PMv4 Owner issuer/signing trust, root service lock, independent installer or component provider/data mount has been deployed.
- Live protected production **circuit breaker open**; exact governed closure remains required.
- Legacy embedded production worker does not yet claim the new lock; parallel external worker activation would be unsafe.
- Source-only Docker synthetic acceptance cannot substitute for two *real* provider-backed post-cutover ticket scans.
- A general PMv4 multi-component production release adapter beyond the disconnected shadow release remains an unfinished engineering item.
- PMv3 user/root units are still required by protected desired-state policy. Do not stop/delete them outside governed retirement.

## No-go / completion rule

No production deployment, restart, unauthorized provider write, signer creation,
freeze mutation or legacy service teardown is authorized by this artifact.
Finish only after exact merged SHA, authenticated release approval, continuity
through all component cutovers, independent recovery, full functional readback,
and audited PMv3 retirement have actually been demonstrated.
