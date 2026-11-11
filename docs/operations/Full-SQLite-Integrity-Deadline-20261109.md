# Governed full SQLite integrity time budget — 2026-11-09

**Status:** Source-only proposed repair, NOT installed, not an override of
protected health. Under the active production freeze and circuit breaker,
only a new exact-SHA Teams-approved release may install this change.

## Observed problem and scope

`jason-openclaw-authority-full-integrity.service` operates at 03:00 daily.
Its full SQLite `PRAGMA integrity_check` and authority backup/restore normally
consume nearly the previous sixty-minute snapshot limit: on 2026-11-07 it
completed in approximately 50 minutes and on 2026-11-08 in approximately
57 minutes; on 2026-11-09 the source subprocess timed out after 3600 seconds.
The orchestration event DB has grown to roughly 32 GB and authority DB to
roughly 3.6 GB. The published full-health file correctly reports FAIL and
exit 124. The frequent health check then correctly fails on missing/stale
full integrity evidence. No database integrity defect has been proven from
the timeout, but PASS cannot be presumed.

## Bounded source repair

Increase only the full-integrity subprocess bound from 3600 to **5400 seconds**
(90 minutes); systemd outer job bound from 3900 to **5700 seconds** (95 minutes).
The existing 300-second outer cushion remains. The same full integrity checks,
complete orchestration audit check, authority SQLite backup/restore count and
integrity validations, private archive staging and explicit fail-closed timeout
behavior remain unchanged. No automatic retries, global cleanup, mutation or
health shortcut is introduced. Parent-owned staging cleanup from the same
PR continues to preserve unrelated archive files even after timeout.

This is additional verification time, **not** proof the growing audit will
complete in 90 minutes. Resource use, daily frequency, source QA, rollback,
underlying disk pressure, and any subsequent overrun must be independently
reviewed before release. No live systemd unit or timer is modified here.

## Tests and production acceptance

`tools/tests/test_openclaw_authority_health_snapshot.py` asserts the new
source/outer timeout relationship and timeout FAIL rather than stale PASS.
`tools/tests/test_openclaw_authority_operational_health.py` retains SQLite
backup/restore checks and archive scratch cleanup. Before production install,
require approved exact candidate SHA, Teams signed approval, native freeze
transaction, protected rollback and root policy compatibility. After install,
require a real full-integrity service PASS (or its next scheduled daily run),
regular health PASS, CCC PASS, clean protected drift and a separately governed
release-manager timer state. Do not reset systemd failed state or clear the
circuit breaker to mask failures.
