# Parallel development admission — governed source candidate

## Objective and actual integration

Parallel engineering must not be confused with production releases. Development branches, staged worktrees, draft PRs, and source-only changes are **not** production drift. Production desired state must remain bound to the separately authorized exact release.

This source candidate extends existing `tools/dependency_conflict_service.py` rather than building a competing controller. `tools/owner_approved_development_worker.py` is the development stage called by `engineering_pipeline.py` under the currently configured PMv4 engineering timer via `pmv3_engineering_controller.py`.

- One secure, nonblocking exclusive lease covers worker state read, admission, durable claim save, and subsequent reconciliation. Concurrent invocations defer; they never claim an empty queue.
- The worker consults source-reviewed `config/development-concurrency-scopes.json` before new development claims, matching files and semantic/shared provider, contract, schema, authorization and deployment domains. Missing or malformed metadata fails closed. This metadata is **not** approval authority.
- Approved development issues are still sourced through existing Owner verification. Admission does not create owner authorization or bypass the production release manager.
- New work is persisted in the existing `development-state.json` through the existing atomic save before worktree creation or model requests. No competing development state database is introduced.
- Existing old-phase records can reconcile, but a previously blocked claim that is recovered must be re-admitted. Existing conflicting editors are held from further source edits until the overlapping PR/claim is stable. PR monitoring remains nonmutating.
- Existing Owner-selected PR adoption is placed *after* dependency admission, closing the path that previously inserted a development record before the controller.
- Historical PR-ready records are excluded from active claims only after explicit GitHub merged-at and merge-commit SHA readback; stale, unknown, or closed-unmerged records remain protected. Live open PR changed files are added to the reviewed semantic scope; an absent or unbounded file inventory is treated as unknown rather than as an empty overlap.
- Updated installer copies the dependency conflict controller and its shared JSON helper to the installed worker module directory. Merely adding an import would have broken the live worker on installation.
- New **feature** claims default to held unless independently verified current production health is supplied. Bootstrap/repair engineering is separately categorized; no production or provider privileges are expanded.
- Worker state exposes `dependency_admission` with queued holds, unclassified work, verified merged PRs, active claims, and existing conflicts. The UI board still requires an authenticated host-to-board evidence bridge before it can display authoritative live holds.

## Read-only reconciliation against live workstreams — November 23, 2026

Authoritative sources were the currently stored development-state JSON (43 historical records) and direct GitHub PR readbacks. Exact GitHub merged-at and merge commit were verified for **10** stale PR-ready records: DEV-1129, DEV-1176, DEV-2309, DEV-2311, DEV-2314, DEV-2315, DEV-2318, DEV-2320, DEV-2322, DEV-950. The remaining relevant live reservations were **DEV-1117**, the open SharePoint-reader PR #1330, and **DEV-2294**, the in-progress financial-statement organizer. They overlap in shared SharePoint provider/contract domains and must not both continue source edits unchecked.

With a **simulated** current production-health acceptance and simulated eligible new claims (not actual authorization), independent DEV-1069 and DEV-1545 are admissible; QuickBooks DEV-1470 conflicts with the active SharePoint work; procurement DEV-759 conflicts with the Teams approver. These are evidence-based dependency examples, not production activation or permission to re-admit previously blocked records.

Read-only reports are saved at `/srv/jason/archive/engineering-artifacts/parallel-development-live-readback-20261123.json` and `/srv/jason/archive/engineering-artifacts/parallel-development-live-readback-v2-20261123.json`. The second readback verified PR #1330 changed-file evidence, showed a direct editor hold on DEV-2294, and confirmed no editor selected while shared SharePoint work is unresolved. The existing production development state was byte-identical before and after validation.

## Source verification

- 262 broad engineering, dependency, worker, installation, integration queue, and control-board tests passed after correcting an outdated test mock whose claimed release-verification reply omitted the required exact `dependency_recheck` status.
- A separate mock-installed-module smoke test successfully executed the worker `--help` path from a temporary directory using exactly its installed Python module dependencies. No systemd unit or installed production file was touched.

## Remaining release/acceptance boundaries

1. Confirm the source package passes protected GitHub CI and any relevant integration/check contracts. This PR stays draft until independently reviewed.
2. Integrate a fresh authoritative production-health attestation feed before allowing **new feature** admission. Never infer that health from a stale repository status field.
3. Confirm every workstream intended for new concurrent admission has complete, source-reviewed semantic metadata; an undeclared scope must remain queued or held. Add source-scope freshness checks if issue contents expand beyond the reviewed declaration.
4. Publish read-only admission evidence to the Development & Release Control Board through the existing governed host mechanism; do not expose the writable ledger to GitHub Actions.
5. Prepare an exact candidate revision, rollback revision and reviewed installer scope under PMV3/PMv4 policy. Obtain applicable authenticated exact-revision authorization before production deployment.
6. Postrelease, verify concurrent independent claims, blocked overlapping claims, automatic recheck of blocked/resumed work, protected Core health, release serialization and absence of false drift, with rollback available.

**Current status:** Integrated and exercised in an isolated source branch. Not merged, installed, deployed, or production verified. No protected service was modified or restarted by this work.
