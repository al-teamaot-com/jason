# Root-protected production drift policy — exact-release parity gate

**Status:** Source-only exact-release policy migration and rollback repair; not deployed
**Incident:** #1974; blocks Universal Teams Approver #1440
**Authority:** Exact owner-approved immutable release and separate CCC material review; root-controlled drift guard and protected LKG remain independent

## Evidence from the October 23 failed release

Production candidate `e8caace9791659adfd383a7ff148253c2ac5f424` added two units:

- `jason-openclaw-authority-full-integrity.timer`, **required** system timer
- `jason-openclaw-authority-full-integrity.service`, **allowed** system service

The independently root-protected policy at `/etc/jason/release-readback-recovery/production-desired-state.json` declared **neither unit**. The owner confirmed both as `MISSING` using a root read-only check on 2026-10-23. Existing installer `tools/install_release_control_transition.py` adds only its two predefined root release-control units, preserving the older recovery-policy overlay. It does **not** migrate newly admitted full-integrity units.

The root `set_last_known_good` transition independently invokes the current immutable `production_drift_guard.py` with that protected overlay when previous root drift evidence is stale. The guard treats an installed undeclared service or timer as drift and refuses to report PASS. This provides a concrete failure mechanism for the observed `independent production drift refresh did not pass`, but the actual rejected unit was not captured by the previous root transition, so the precise historical cause is **probable, not independently proved**.

Post-deployment CCC passed, but root LKG refused. Native rollback restored the old runtime and MCP and host revision, but timed out on the legacy multi-minute OpenClaw health service during host reconciliation. Durable release record is `failed`, and its historical rollback verification is false. On October 23 at approximately 13:25 UTC, the Owner explicitly authorized native non-drift host recovery. Jason independently compared all ten protected immutable LKG fingerprint fields (all MATCH), observed root-owned drift PASS and zero failed systemd units, and invoked its existing root-governed `revalidate` transition. Root worker independently returned `root_verified_revalidate` for the original LKG revision, closing the breaker. **This is new recovery evidence, not retroactive historical rollback success.** The automatic-release incident hold remains intact.

## Source safety gate introduced by this change

Root-owned `release_host_reconcile_worker.py` now inspects:

1. The exact candidate's `config/production-desired-state.json` loaded from protected Git source.
2. The independently root-owned, mode-0600 recovery-policy override, opened without following symlinks.
3. Every required and allowed system/user unit declaration, preserving the distinction between **required** and merely **allowed**.

**Before** materializing or invoking the candidate host installation script, any missing declaration causes a bounded, named fail-closed error. The worker **never** copies arbitrary candidate units into the root overlay. A missing root policy, invalid schema, unusual file owner/mode or malformed unit declaration fails closed. In rollback to an older source, this check is necessary but not sufficient to prove the final host baseline: the native LKG and protected drift checks remain mandatory.

Root transition `refresh_stale_drift()` separately extracts at most six bounded `kind:jason-unit` values from the independent guard's structured failure evidence, not raw stdout/stderr, command lines, credentials or provider data. Nonzero guard results still fail. A 70-second timeout is explicitly classified as denial, never accepted as green.

## Protected four-unit migration and symmetric downgrade

The exact failed-release source delta is **four declarations**, not just the two system units: REQUIRED `jason-openclaw-authority-full-integrity.timer`, ALLOWED `jason-openclaw-authority-full-integrity.service`, and ALLOWED user `jason-openclaw-recovery-source-bridge.service` and `jason-openclaw-recovery-source-bridge.timer`.

`tools/protected_root_policy_migration.py` now implements a bounded root-only migration. The four specific names and categories are a static source-review boundary; it will **not** union arbitrary units advertised by a candidate into the privileged overlay.

When an **independently owner-approved, CCC-reviewed, exact-SHA** future release reaches native immutable host reconciliation:

1. The candidate's root host reconciler and rollback helper are installed **first** from that exact immutable release source, before any policy mutation. The currently running old reconciler still controls the forward request, but the newly installed helper is available for the subsequent rollback request.
2. After the new units and standard host controls are installed, the candidate's `install_release_control_transition.py` validates root last-known-good and closed breaker, exact candidate SHA and rollback SHA, the production release record's owner approval and `production_control_core` classification, and matching `person-al` CCC material review. It compares the old/new immutable desired-state files; all non-unit fields must match, and only the four explicit declarations may be added.
3. The migrator preserves all existing root-only recovery additions, saves the **exact original policy bytes**, hashes, source revisions, reviewed delta and authorization linkage in a mode-0600 root ledger. It installs the exact changed policy atomically with root ownership, mode 0600 and filesystem sync. It never changes `last_known_good`, the breaker or a release record itself.
4. At final LKG, the independent root drift checker sees only reviewed required/allowed units, and its original fail-closed invariant remains unchanged. Unknown units still block.
5. If the promotion fails and native Release Manager rolls back to its original immutable LKG, the installed root host reconciler first checks the active root-only receipt, **restores the exact original root policy bytes**, archives the migration receipt, and *then* invokes the older immutable host rollback script. A different rollback SHA, tampered policy hash, missing receipt or diverged root LKG refuses restoration.

The migrator **cannot be invoked as a standalone policy-write shortcut** and does not install candidate-only requirements into the currently healthy older production state. Its activation depends on a new reviewed source revision being merged, independently authorized and promoted normally; the previous failed `e8caace979...` release is never silently retried or reused for approval.

## Separate rollback service timeout still requires acceptance

The old immutable rollback script actually budgets **240 seconds** for `jason-openclaw-authority-health.service`, not 45 seconds; a protected Git read verified that exact source and SHA-256 `d8bf41dfe824b8eb01ae192386907a6657f09c245aa246306597a1162c7d1707`. The failed rollback returned `rc=124` while systemd still reported the unit `activating`; the failed start may have been queued behind an already-running health job, and root logs did not prove it was simply an undersized configured timeout. A root-owned compatibility path for **only** exact historical LKG `aca94fdc0bfa551162f6ea99d7ddded311786414` verifies the immutable script's SHA-256 and one exact health-start line. It writes a separate throwaway root-only materialization with **only** `240s` changed to **`300s`** for the same mandatory full-health `systemctl start` call; the immutable source file remains unchanged. Every result/verification gate remains intact. The root worker's historic-only execution budget is **410 seconds**, below the independently enforced Release Manager **420-second** and root systemd **480-second** limits. A missing old blob hash, multiple matching lines, any other SHA, actual failed service result, or expired deadline still fails closed. This is an audited exception requiring independent review and fault-path proof, not authority to patch arbitrary previous releases or skip security scans.

The incident's **current LKG** is independently recovered and breaker-verified as described above. Before repeating production promotion, separately prove the full candidate-to-legacy rollback fault path in isolated preproduction, including queued or long-running systemd starts and timeout/error rejection. A pinned timeout-only source transformation passing local tests is not proof of successful real rollback. The automatic promotion hold remains active until documented disposition.

Final production acceptance still requires new source/approval/CCC, immutable runtime-MCP-host match, full protected root LKG, fresh CCC PASS and real rollback readiness. Teams Approve/Deny production acceptance is downstream.

## Test boundary

Focused checks cover missing required/allowed declarations, required-vs-allowed substitution, malformed or non-root policy, exact SHA read from Git, failure before host mutation, bounded drift messages without credential leakage, timeout denial, LKG/rollback and breaker behavior. Tests in an isolated worktree validate source behavior only, including exact byte-for-byte migration restoration; they do **not** establish that any new policy has been applied on live production or that the legacy health-service rollback timeout is resolved. No protected production state is modified by this source change.
