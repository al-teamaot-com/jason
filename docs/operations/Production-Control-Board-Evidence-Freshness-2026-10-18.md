# Production Control Board: preserve newer host observations without granting authority

**Parent:** P0 #1078; related SUPPORT-OPS-050 and #526.
**Change type:** Reporting-only reliability repair; production release controls are unchanged.

## Observed failure

On 2026-10-18, the root-governed release record release-ad11c311251254d3
closed successfully. Protected readback showed circuit breaker closed, an
immutable complete LKG manifest at ad11c311251254d38da2c1295aadd292daed20ef
and a clean production drift check. The release documentation closeout
published the current production observation to GitHub issue #526.

The generated documentation reconciliation PR #1564 contains that current
observation but has not been merged. GitHub Actions rebuilds #526 every five
minutes from main, where docs/control/AUTOMATED-CHANGE-STATE.json still
contains the older dfab202dc production snapshot. It can therefore replace
newer host-published evidence with older repository data.

## Bounded correction

- Keep one canonical production authority: the protected release manager,
  verified release records, protected root state, and controlled readback.
- On actual production documentation closeout, tag the issue #526 report
  with a versioned, advisory host-publication marker.
- Before a scheduled GitHub issue update, compare its repository observation
  with the prior tagged host-published observation. Use the newer observation
  only while its timestamp and revision are structurally valid.
- Recompute age at every refresh. Once the existing 30-minute TTL expires,
  change health to revalidation_required and breaker, lock, transaction,
  queue and drift fields to unknown (host evidence stale).
- Reject naive/future timestamps as proof. Expose that revision is based on
  a last recorded observation, not a continuously verified live host check.
- If main has newer evidence, stop carrying the old host marker.

## Limits and release conditions

This is an advisory display repair, not cryptographic attestation,
transaction locking, proof of host reachability, or authorization to promote.
The GitHub issue body and marker cannot grant Production Manager authority.
An issue edit is not a root-governed release state change.
A concurrent issue edit can still race at the GitHub API; the publisher uses
the latest body observed at its read. Do not treat this as a full production
health/availability feed or a substitute for protected readback.

A separate exact-SHA governed release and post-deployment acceptance are
required. Confirm that (1) a host-origin report is not replaced by the next
scheduled board tick, (2) stale evidence visibly expires, (3) newer main
evidence supersedes it, and (4) release admission and CCC behavior remain
unchanged. The broader #1078 controlled failure/rollback acceptance stays
open even if this reporting repair passes.
