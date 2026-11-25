# Delegation Maintenance SQLite Contention

## Incident

At 2026-10-15 02:55 EDT the root-owned hourly
`jason-delegation-maintenance.service` returned exit code 1 with SQLite
`OperationalError: database is locked`. Its earlier hourly executions
succeeded. Root drift correctly identified the failed required systemd unit
and opened the release circuit breaker. The deployment remained on the
last-known-good source. Incident tracking: GitHub #1443.

## Scoped source change

`tools/delegation_maintenance.py` closes SQLite connections after every
transactional attempt and retries *only* `SQLITE_BUSY` / `SQLITE_LOCKED`
with a maximum of five attempts, five seconds per connection acquisition,
and bounded backoff of 1, 2, 4, then 6 seconds. Expired delegation updates
and their paired authority audit entries remain in one SQLite transaction.
Each failed attempt rolls back; retry recomputes expiry from the current
clock and resets its changed-delegation list. A subsequent successful
attempt commits once, and re-running the job does not duplicate expiration
audits. No approval/delegation is created, broadened or extended.

Unrelated SQLite errors or contention beyond this bound still return a
nonzero systemd result and remain visible to drift/CCC. The fix does not
disable locking, change journal or database permissions, or artificially
clear protected release control-state.

## Validation and rollout

Tests use isolated SQLite databases and deliberately inject both transient
and persistent contention. They verify retry/backoff bounds, exactly-once
audits, rollback after an UPDATE with a failed audit INSERT, nonbusy
failure behavior and the CLI's nonzero status on failure.

**Do not merge or deploy this source change ahead of the existing
Owner-approved Stage 1 SHA 5c65cde71d45feec96673966f6242de612e018ef.**
That release's exact SHA approval must remain valid. First recover the
failed unit via ordinary authorized systemd/timer execution, independently
verify drift PASS and use only root-governed breaker revalidation. Then
apply the approved Stage 1 release; schedule this patch afterward as a
separately reviewed release requiring its own exact source approval.

The code repair alone cannot clear the already-failed service unit;
root/systemd control and a successful native maintenance run are required.
