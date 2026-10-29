# Stage C restack — Windows Time JSON read-only shadow after narrowed Stage B1

**Status:** Isolated source-review branch only. Not merged, not a PM release candidate, not activated, no provider mutations.

## Authoritative lineage and preservation

- Deployed protected-main Stage A baseline: `d71cde5d24bdd65e67cb5c44d29eaf5f104edcbf`.
- New narrowed Stage B1 parent (draft PR #2137): `b2bbb4cdb10c26a88db08bc4a293fdd126b27997`. This is not yet accepted or merged to main.
- Original broad Stage B #2128 at `6fc2b60ea4ee5adff8d615833b548388512ab1b8`, original stacked Stage C #2129 at `ab60230e9c3a72b173e7eb3da2ecb1a1abed0a29`; these original branches and PRs remain untouched.
- Restack applies **only** the 31 unique changed paths between original broad B and original C on top of B1, preserving B1's one default-OFF human Autotask profile. It does not copy unaccepted Stage B IT Glue/Entra registration, write secret mounts, cloud-user creation or client-scope/credential code.
- The two intentionally overlapping files `implementation/runtime_service/src/jason_runtime/composition.py` and `infrastructure/jason-runtime/compose.yaml` were merged additively and must be retested independently; neither may introduce the broad Stage B write adapters.
- The 2026-10-28 full-scope release dossier is retained as a **historical snapshot**, with its outdated predeployment/merge state clearly marked. It must never be used as a current PM release authorization or rollback instruction.

## Read-only pilot contract

- One additional JSON classifier for the existing Windows Time source worker, using existing governed `management.alert.search`, `endpoint.device.read` and `endpoint.alert.history.search`.
- No new scheduling worker or provider permission. No endpoint modifications, tickets, alert resolutions, customer notifications, autonomous remediation, reboots, service restarts, network resets, or Datto RMM write calls.
- All 16 JSON preview drafts remain `autonomy.activation=disabled`. The 17th client-information playbook remains independent and unconverted.
- `JASON_WINDOWS_TIME_JSON_SHADOW_ENABLED` defaults **false**; `JASON_WINDOWS_TIME_JSON_SHADOW_SITE_UID_ALLOWLIST` defaults empty. A nonempty allowlist is not authority to enable the pilot.
- Any **future** on-host shadow canary, only after an authorized exact-SHA deployment, must be constrained to Riggins Company site UID `17065ca1-dfdf-4c6b-95c7-8a8a5f5dc14a`, evidence from two consecutive 15-minute cycles, and no provider changes.

## Verification and release gates

1. Verify Stage B1 branch is accepted, merged to protected main, tested and separately production-authorized before processing Stage C's dependent release. Reconcile the stacked branch against **that resulting production/main SHA**, not its original branch base, and review the full release scope including unrelated main changes.
2. Run isolated source tests for JSON preview schema/manifest, windows-time source and shadow evidence, composition interaction, Stage B1 Autotask authority/disabled state, strict UID-only site selection, negative and stale evidence, no provider writes.
3. Run exact-head CI and build two immutable candidate images; verify the one reviewed Windows Time JSON candidate is included, and both native deployment scripts return `PREFLIGHT=PASS` with inactive pilot defaults.
4. Obtain independent code/security review, provider-backed authorized read-only canary evidence, exact candidate SHA, rollback SHA and native PM preproduction/CCC checks. An unmerged draft is **not** PM production eligible.
5. Obtain separate Owner exact-SHA deployment authorization and subsequent separate Riggins-only read-only pilot activation. Restore broader freeze/incident hold and roll back to verified LKG upon any failed mandatory check.

**No transition or permission change is approved by these documents.**
