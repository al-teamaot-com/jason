# Parallel development admission — governed source candidate

## Objective and actual integration

Parallel engineering must not be confused with production releases. Development branches, staged worktrees, draft PRs, and source-only changes are **not** production drift. Production desired state must remain bound to the separately authorized exact release.

This source candidate extends existing `tools/dependency_conflict_service.py` rather than building a competing controller. `tools/owner_approved_development_worker.py` is the development stage called by `engineering_pipeline.py` under the currently configured PMv4 engineering timer via `pmv3_engineering_controller.py`.

- Real worker file locking is covered by an independent-process contention test, not just a synthetic in-memory collision. A redundant standalone claim-ledger primitive was retired; the existing worker development-state file remains the sole canonical claim database.
- An unclassified legacy active source editor is held until reviewed scope exists, because unknown dependencies cannot be assumed independent.
- One secure, nonblocking exclusive lease covers worker state read, admission, durable claim save, and subsequent reconciliation. Concurrent invocations defer; they never claim an empty queue.
- The worker consults source-reviewed `config/development-concurrency-scopes.json` before new development claims, matching files and semantic/shared provider, contract, schema, authorization and deployment domains. Missing or malformed metadata fails closed. This metadata is **not** approval authority.
- Approved development issues are still sourced through existing Owner verification. Admission does not create owner authorization or bypass the production release manager.
- New work is persisted in the existing `development-state.json` through the existing atomic save before worktree creation or model requests. No competing development state database is introduced.
- Existing old-phase records can reconcile, but a previously blocked claim that is recovered must be re-admitted. Existing conflicting editors are held from further source edits until the overlapping PR/claim is stable. PR monitoring remains nonmutating.
- Controller-owned dependency holds are automatically reassessed on every later authorized worker pass. Release requires verified scope, free capacity, no active conflicts and current production-health evidence for feature work. Manual/credential/issue approval holds do not reopen. An upstream PR merge is source stability, never proof of Production Verified acceptance.
- Legacy overlap detection now covers authorization paths and tenant scopes as well as files, contracts, providers, schemas and deployment paths.
- Existing Owner-selected PR adoption is placed *after* dependency admission, closing the path that previously inserted a development record before the controller.
- Historical PR-ready records are excluded from active claims only after explicit GitHub merged-at and merge-commit SHA readback; stale, unknown, or closed-unmerged records remain protected. Live open PR changed files are added to the reviewed semantic scope; an absent or unbounded file inventory is treated as unknown rather than as an empty overlap.
- A GitHub-only scheduled board refresh preserves a recent host-admission advisory observation for up to 30 minutes; it refuses forged/invalid previous content, and expires to not-verified when no fresh host observation exists. This is board display, never engineering authority.
- Updated installer copies the dependency conflict controller and its shared JSON helper to the installed worker module directory. Merely adding an import would have broken the live worker on installation.
- New **feature** claims default to held unless independently verified current production health is supplied. Bootstrap/repair engineering is separately categorized; no production or provider privileges are expanded.
- Worker state exposes `dependency_admission` with queued holds, unclassified work, verified merged PRs, active claims, and existing conflicts. The existing Development & Release Control Board now has a read-only projection for fresh host claim evidence, including legacy editor holds and queued dependency blocks. The GitHub-only publisher will correctly display **not verified** when host evidence is unavailable; a separately governed host-to-board publisher remains necessary for authoritative live visibility in GitHub.

## Read-only reconciliation against live workstreams — November 23, 2026

Authoritative sources were the currently stored development-state JSON (43 historical records) and direct GitHub PR readbacks. Exact GitHub merged-at and merge commit were verified for **10** stale PR-ready records: DEV-1129, DEV-1176, DEV-2309, DEV-2311, DEV-2314, DEV-2315, DEV-2318, DEV-2320, DEV-2322, DEV-950. The remaining relevant live reservations were **DEV-1117**, the open SharePoint-reader PR #1330, and **DEV-2294**, the in-progress financial-statement organizer. They overlap in shared SharePoint provider/contract domains and must not both continue source edits unchecked.

With a **simulated** current production-health acceptance and simulated eligible new claims (not actual authorization), independent DEV-1069 and DEV-1545 are admissible; QuickBooks DEV-1470 conflicts with the active SharePoint work; procurement DEV-759 conflicts with the Teams approver. These are evidence-based dependency examples, not production activation or permission to re-admit previously blocked records.

Read-only reports are saved at `/srv/jason/archive/engineering-artifacts/parallel-development-live-readback-20261123.json` and `/srv/jason/archive/engineering-artifacts/parallel-development-live-readback-v2-20261123.json`. The second readback verified PR #1330 changed-file evidence, showed a direct editor hold on DEV-2294, and confirmed no editor selected while shared SharePoint work is unresolved. The board projection and its missing/stale/forged-evidence cases were tested in isolation without accessing the host audit database. The existing production development state was byte-identical before and after validation.

## Source verification

- 262 broad engineering, dependency, worker, installation, integration queue, and control-board tests passed after correcting an outdated test mock whose claimed release-verification reply omitted the required exact `dependency_recheck` status.
- A separate mock-installed-module smoke test successfully executed the worker `--help` path from a temporary directory using exactly its installed Python module dependencies. No systemd unit or installed production file was touched.

## Remaining release/acceptance boundaries

1. Confirm the source package passes protected GitHub CI and any relevant integration/check contracts. This PR stays draft until independently reviewed.
2. Integrate a fresh authoritative production-health attestation feed before allowing **new feature** admission. Never infer that health from a stale repository status field.
3. Confirm every workstream intended for new concurrent admission has complete, source-reviewed semantic metadata; an undeclared scope must remain queued or held. Add source-scope freshness checks if issue contents expand beyond the reviewed declaration.
4. Connect the new read-only Development & Release Control Board projection to the existing authenticated host publication mechanism. GitHub-only runs must show **not verified**, not assume an empty queue. Do not expose the writable ledger to GitHub Actions.
5. Prepare an exact candidate revision, rollback revision and reviewed installer scope under PMV3/PMv4 policy. Obtain applicable authenticated exact-revision authorization before production deployment.
6. Postrelease, verify concurrent independent claims, blocked overlapping claims, automatic recheck of blocked/resumed work, protected Core health, release serialization and absence of false drift, with rollback available.

**Current status:** Integrated and exercised in an isolated source branch. Not merged, installed, deployed, or production verified. No protected service was modified or restarted by this work.

## November 23 dependency safety follow-up

Source-level regression additions now verify automatic hold recheck, capacity and production health gates, manual hold isolation, legacy tenant/authorization overlaps, and control-board observation freshness. The owner-approved source branch remains isolated; none of these checks operated the production database or activated any root-owned service.

Fresh read-only production control evidence on 2026-11-23 reported drift_detected, breaker open, and required_system_unit_not_active for jason-audit-journal-maintenance.timer. The database cleanup and drift repair remain separate activities. Do not merge or deploy this change as a normal feature rollout while the breaker is open. A new health/rollback preflight and exact-action Owner approval are required before release.

## November 24 scoped installation preparation

Live Stage E runs the installed development module from `/home/al/.local/lib/jason`, while the shared engineering source link remains pinned to the accepted Stage E checkout. That checkout predates the new concurrency registry. Advancing the shared link just to read one registry would implicitly change unrelated worker source and invalidate reviewed release baselines.

The scoped candidate therefore resolves the registry beside the installed worker. Source-checkout execution continues to use the checkout's `config` registry. A missing installed registry does not fall back to another revision; new claims remain held. The existing installer copies the registry alongside the installed dependency modules. No new controller, timer, release lane or authority is introduced.

The live activation scope is four files in `/home/al/.local/lib/jason`: `owner_approved_development_worker.py` (replace), `dependency_conflict_service.py`, `isolated_service_common.py`, and `development-concurrency-scopes.json` (add if still absent). The existing general installer is source-reviewed for future use, but is NOT the scoped deployment mechanism: invoking it would replace unrelated files, source links or unit configuration. The release coordinator is already present in protected main for GitHub's board workflow and does not need a live host replacement for this narrow activation.

Prepare exact candidate and rollback bytes and modes, and rehearse their installation and rollback in a disposable installed-layout fixture. Live installation remains separately gated by successful audit migration, fresh protected health and drift evidence, a reviewed native scoped transaction under existing locks, exact authenticated Owner approval, and actual post-install acceptance. Preserve the current Stage E source link, engineering pause/feature admission holds, runtime and MCP, timers, production freeze and rollback. Do not interpret independent engineering preparation as authority to deploy multiple production changes simultaneously. Feature admission still requires a fresh authoritative health attestation; the current conservative `production_healthy=False` remains deliberately unchanged pending that integration.
