# Root-protected production drift policy — exact-release parity gate

**Status:** Source-only P0 release-safety repair; not deployed  
**Incident:** #1974; blocks Universal Teams Approver #1440  
**Authority:** Exact owner-approved immutable release and separate CCC material review; root-controlled drift guard and protected LKG remain independent

## Evidence from the October 23 failed release

Production candidate `e8caace9791659adfd383a7ff148253c2ac5f424` added two units:

- `jason-openclaw-authority-full-integrity.timer`, **required** system timer
- `jason-openclaw-authority-full-integrity.service`, **allowed** system service

The independently root-protected policy at `/etc/jason/release-readback-recovery/production-desired-state.json` declared **neither unit**. The owner confirmed both as `MISSING` using a root read-only check on 2026-10-23. Existing installer `tools/install_release_control_transition.py` adds only its two predefined root release-control units, preserving the older recovery-policy overlay. It does **not** migrate newly admitted full-integrity units.

The root `set_last_known_good` transition independently invokes the current immutable `production_drift_guard.py` with that protected overlay when previous root drift evidence is stale. The guard treats an installed undeclared service or timer as drift and refuses to report PASS. This provides a concrete failure mechanism for the observed `independent production drift refresh did not pass`, but the actual rejected unit was not captured by the previous root transition, so the precise historical cause is **probable, not independently proved**.

Post-deployment CCC passed, but root LKG refused. Native rollback restored the old runtime and MCP and host revision, but timed out on the legacy multi-minute OpenClaw health service during host reconciliation. Durable release record is `failed`, rollback verification is false, and the root breaker is OPEN. No CI check or clean readback snapshot may reclassify the failed release as closed.

## Source safety gate introduced by this change

Root-owned `release_host_reconcile_worker.py` now inspects:

1. The exact candidate's `config/production-desired-state.json` loaded from protected Git source.
2. The independently root-owned, mode-0600 recovery-policy override, opened without following symlinks.
3. Every required and allowed system/user unit declaration, preserving the distinction between **required** and merely **allowed**.

**Before** materializing or invoking the candidate host installation script, any missing declaration causes a bounded, named fail-closed error. The worker **never** copies arbitrary candidate units into the root overlay. A missing root policy, invalid schema, unusual file owner/mode or malformed unit declaration fails closed. In rollback to an older source, this check is necessary but not sufficient to prove the final host baseline: the native LKG and protected drift checks remain mandatory.

Root transition `refresh_stale_drift()` separately extracts at most six bounded `kind:jason-unit` values from the independent guard's structured failure evidence, not raw stdout/stderr, command lines, credentials or provider data. Nonzero guard results still fail. A 70-second timeout is explicitly classified as denial, never accepted as green.

This is an **admission and diagnostic fix**, not authorization or an automatic root policy migration.

## Protected migration and release recovery — required separate work

1. Preserve original root overlay bytes, owner/mode, and audit evidence before proposing migration.
2. Compute the exact desired-state delta from current immutable LKG to the separately approved candidate; do not union all candidate-controlled unit names into a privileged root allowlist.
3. Independently review and authorize the candidate-bound root policy delta, including **downgrade/rollback policy restoration**. A service approved for one SHA must not stay **required** after rollback to an earlier LKG which does not declare it.
4. Implement a root-owned, bounded, atomic versioned policy transition, protecting schema, ownership, path and exact SHA, and stage it **before** host mutation. Do not modify the protected policy by hand as an expedient workaround and do not use provider/shell bypasses.
5. Prove real rollback host reconciliation across the legacy slow authority-health service, with appropriate bounded timeout budgets. The recovered old runtime/MCP and no failed systemd units are helpful evidence but do not substitute for a root host PASS.
6. Obtain separate human-reviewed non-drift breaker recovery and exact-SHA release/CCC authorizations. Do not re-use the failed release approval, clear the incident hold, self-certify failure, or force `production_verified`.
7. Final acceptance requires a new release record `closed`, all candidate runtime/MCP/host identities aligned, complete root-owned LKG, fresh post-release CCC PASS, desired-state drift PASS, and rollback safety proved. Only then proceed to Universal Teams Approve/Deny acceptance.

## Test boundary

Focused checks cover missing required/allowed declarations, required-vs-allowed substitution, malformed or non-root policy, exact SHA read from Git, failure before host mutation, bounded drift messages without credential leakage, timeout denial, LKG/rollback and breaker behavior. Tests in an isolated worktree validate source behavior only, **not** a successful production migration or a completed rollback. No protected production state is modified by this source change.
