# Project Jason: governed production circuit-breaker self-recovery

## Problem

The production desired-state drift watchdog intentionally opens the protected
circuit breaker when a user/system unit is unhealthy and **never closes it**
merely because a later drift scan passes. The root-owned transition worker
already verifies a distinct revalidate request against the last-known-good
(LKG) revision, fresh root-owned desired-state evidence and independently
captured runtime/MCP/host health. But nothing reliably generates that request
after production returns to health, leaving approved engineering releases
stranded without an authorized root terminal.

Observed incident on 2026-10-19: production revision
e6503eabb53d2f9b5fb9d388a7d43c49c784544a was independently confirmed
to match the live runtime, MCP and installed release manager. Production drift
returned pass and there were zero failed units, but the protected breaker
remained open, source production_drift_watchdog, due to an earlier
failed_user_unit. Release candidate PR #1604 was merged at
8fe9320fc6f9b1f85728ffb0bf8c2f5bca851941; production had not advanced.

## Bounded autonomous intent, not delegated root authority

New release_breaker_recovery_manager.py is a separate, independent stage of
the existing scheduled engineering pipeline. The versioned, immutable source
policy at config/release-breaker-self-recovery-policy.json requires:

* Exact LKG SHA and complete immutable manifest from protected root readback.
* The protected breaker is open specifically because of continuous desired-
  state drift, with exact source production_drift_watchdog and exact
  continuous_production_drift_detected reason. Release errors, failed
  rollbacks, missing authority and all other breaker types remain human gated.
* At least 90 seconds after breaker opening, then three separate clean
  root-observed drift reports at least 15 seconds apart, each fresh within
  180 seconds and newer than the breaker's opened timestamp.
* The installed engineering repository HEAD exactly equals the protected LKG
  source revision. Policy must be read from that exact Git revision, not from
  a mutable or newer developer checkout.
* No active production transaction lock.
* Maximum two recorded revalidation intents per exact breaker identity,
  separated by at least five minutes; the durable restricted-permission ledger
  records the attempt before any root worker call. An invalid ledger cannot
  silently reset authorization attempts.

Eligible attempts call only the Release Manager's existing
revalidate_circuit_breaker function, which captures a fresh production
manifest and asks the installed root-owned transition worker to execute one
finite revalidate action. Only the root worker may change protected state;
it checks its own root-owned drift, LKG and exact revision. The root worker
also compares the observed runtime/MCP image digests, source revisions,
host release, scheduled unit state and desired-state policy digest to the
original immutable LKG evidence before closure.

Failures, missing protected files, mismatched image fingerprints,
busy deployments, stale drift, denied source, exhausted attempts and timeouts
are visible blockers, not successful verification.

A rejected native root revalidation additionally persists a **whitelisted,
non-secret failure classification** in the durable attempt ledger. The
classification distinguishes independently rejected production drift,
immutable LKG mismatch, protected file/identity rejection, root transition
timeouts, stale readback and preflight health failure when a known root error
is explicitly returned. Unknown errors remain
`unclassified_root_revalidation_failure`, never guessed healthy. Raw root
exceptions, paths, secrets or provider data are never written to the
unprivileged ledger, and no additional root request or budget reset is
authorized by these diagnostic fields. Historical rejections from before the
instrumentation remain unknown; root operator evidence is still required.

The October 20 breaker incident had two rejected native revalidation requests
at 12:21:18Z and 12:31:11Z; the installed version retained only their
`ReleaseManagerError` type. This diagnostics-only change does **not** replay
those attempts, clear that open breaker, delete the owner incident hold, or
supply exact-SHA authorization for a newer release. A closed breaker is a
no-op; engineering release approval, preproduction, CCC, rollback and
postdeployment checks remain independent and mandatory. No provider calls,
production deployment, Docker retagging, sudo, shell forwarding or mutable
trusted-policy overrides are introduced.

## Operational acceptance

After an authorized deployment of this code and its root-owned source
reconciler, observe (1) an opened drift-only breaker, (2) three distinct
fresh green root readbacks, (3) durable one-time request ledger, (4) a
root-owned positive transition/result with exact LKG and all baseline
fingerprints, (5) protected breaker readback closed, and (6) normal exact
owner-approved release flow resuming. Negative tests must show denial for
release-manager or rollback-origin breakers, failed/stale drift, wrong SHA,
dirty installed repo, missing or tampered LKG, busy transaction, duplicate
samples and exhausted recovery budgets.

This PR cannot repair the currently open protected breaker by itself:
the installed production release must be updated through an already-authorized
root-governed path or a duly authorized operator/bootstrap flow. No source
merge or local dry-run is proof of live closure. Maintain #1517 and #1526
for the separate governed CCC installation/recovery authority and bootstrap
requirements; do not present this narrow drift-only automation as completing
those broader issues.

Integration coordination: #1078, #1301, #1440, #1517, #1526, #1601, #1603, #1604.

## November 14, 2026 — PMv4 independent recovery installation gap (source-only)

**Observed live host, read-only:** production LKG remained
`d1b8c196dadd4b672ec8ba47075f27bb61c98d63`; the scheduled
full SQLite integrity proof returned PASS at 03:47 EST, the five-minute
authority health check passed, the drift watchdog returned PASS with no
blocking problems, and runtime/MCP containers remained up. Nonetheless
the root-owned breaker was still OPEN because of an earlier failed system
unit. The engineering pipeline's recovery stage last ran November 4,
and the unprivileged recovery ledger was last updated November 12.
The existing `jason-release-breaker-recovery.service` and matching
timer existed in the pinned source but were absent from the actual
`al` systemd user unit directory. Merely having the manager and unit
definitions in source does **not** demonstrate autonomous recovery.

**Source-only correction:** `tools/install_support_repair_host_worker.py`
now supports an *explicit opt-in* `--activate-breaker-recovery`
**together with** the existing `--activate`. The ordinary installation
path is unchanged and never stages or starts this recovery timer.
The opt-in copies only the two already-defined recovery units using
the existing installer; reuses the already installed, policy-limited
`release_breaker_recovery_manager.py`; reloads the user systemd manager;
enables the timer; and requires `is-active` success. If activation or
readback fails, it attempts to disable the unverified recovery timer
and reports failure. No new scheduler, signer, policy store, release
engine, or provider-write authority is introduced.

**Authority boundary:** This flag is an installation mechanism, **not**
production approval. Do not invoke it on Jason's live host merely
because the code is merged or because the breaker is currently open.
An approved, exact-source governed release transaction must first
authorize the independent timer activation. Preserve the protected
production freeze, automatic-promotion hold, root-owned breaker and
last-known-good until the authorized release process performs its
separate health and rollback checks. The timer can only request the
existing native root revalidation: root alone can close the breaker,
after policy-required healthy observations. The flag does not activate
PMv4 Stage A0, Ticket Core cutover or PMv3 retirement.

**Preproduction acceptance:** disposable installer fixtures must prove
unchanged default service deployment, rejection of opt-in without
activation, exact paired recovery-unit installation, fail-closed missing
unit, and disable-on-failed-readback. The existing recovery policy,
isolation, concurrency and denied-transition regressions must also pass.
After a separately authorized activation, verify the exact installed
unit hashes, active timer, three distinct fresh clean root drift
observations, the signed/guarded native revalidation result, protected
breaker readback, and unchanged runtime/MCP, ticket processing,
freeze/hold, and providers. If the native revalidation denies, leave
the breaker OPEN and report its sanitized cause; never reset the
attempt ledger, bypass root or repurpose the release manager's
approval-only hold.
