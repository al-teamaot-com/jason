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
are visible blockers, not successful verification. A closed breaker is a
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
