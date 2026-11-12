# Governed full SQLite integrity time budget — 2026-11-09

**Status:** Source-only proposed repair, NOT installed, not an override of
protected health. Under the active production freeze and circuit breaker,
only an independently verified exact-SHA, exact-scope authenticated Owner-approved governed release may install this change; Teams is not required.

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
require approved exact candidate SHA, authenticated exact-action Owner approval via ChatGPT or an independently verified Owner session, native freeze
transaction, protected rollback and root policy compatibility. After install,
require a real full-integrity service PASS (or its next scheduled daily run),
regular health PASS, CCC PASS, clean protected drift and a separately governed
release-manager timer state. Do not reset systemd failed state or clear the
circuit breaker to mask failures.


## November 12 live incident revalidation

The separately Owner-authenticated Constant Contact OAuth MCP projection PR #2462
is merged **source-only** at main `c1e6fa04357e254446ee353f43662638bde71351`.
No production activation or OAuth provider POST has occurred. Protected live host,
runtime and MCP remain at LKG `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`
with original freeze SHA256
`bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`.

The full proof on November 12 again returned FAIL/124 after 60 minutes;
the orchestration audit file is currently 36.6 GB decimal, with 4.1 GB
authority SQLite. No existing completed PASS snapshot is available. A separate
root-owned temporary five-minute health degradation allowance expired at
15:00 UTC as designed, causing `jason-openclaw-authority-health.service`
to fail and the production drift watchdog to open the root circuit breaker.
At 15:49 UTC, the breaker was still open and drift reported the failed health
unit. There were two failed one-shot services, and no authority to declare
a full integrity PASS. The independent archive filesystem has approximately
185 GB available, so a run-scoped 4 GB authority backup/restore temporary
copy fits with ample capacity reserve.

The proposed 90-minute systemd/SUBPROCESS bounds and run-scoped temporary
cleanup preserve *every* full SQLite integrity check, authority restore
proof, and explicit FAIL/124. A source merge or a preproduction test is
**not** production recovery. Complete the genuine full integrity PASS (or
an independently reviewed equivalent complete proof), then restore the
normal frequent health unit and root drift via the protected revalidation
procedure. Do not prolong the expired degradation allowance, forge proof,
mask failed units, or use direct Docker to work around the open breaker.
The separate Constant Contact OAuth, account/list binding, consent-backed
pilot and scheduler all remain gated until exact activation authorization.
