# Production drift: optional observer failures must not block Jason

**Status:** Source-only, awaiting exact reviewed merge and separately
authorized production release. Does not change live breaker state.

## Minimal governing distinction

Only **genuine production integrity changes** or failure of **required
operational/safety services** may open the production drift breaker. A
declared, non-required observer or reporting unit reporting a failed result
must generate a visible **advisory**, not a blocking production drift
violation. This is a classification change to the existing watchdog, not
a new subsystem, approval mechanism or recovery scheduler.

A known November 13, 2026 incident involved
`jason-grafana-assurance.service`: its OpenAI usage/cost metric source
temporarily reported no data, Grafana assurance failed, and systemd
retained the failed result. Metrics returned on the next check without any
protected production code change. That isolated observer failure should
be recorded, not stop unrelated Jason work. The **separate**
`jason-openclaw-authority-health.service` remains a genuine blocking
failure until its independently governed full-health repair succeeds.
This source-only adjustment does not close existing breakers.

## Exact scope

The existing static allowlist admits only eight **explicitly reviewed**
optional observer/reporting units, and **only** when each is already
declared ALLOWED and **not** declared REQUIRED in
`production-desired-state.json`. These are Grafana assurance and its
metrics exporter/timer, standalone isolated provider-health observer and
timer, provider-health canary on-demand service, documentation
reconciliation on-demand service, and the standalone optional full-integrity
scan (not the required authority-health service). A failed unit creates
the existing `independent_optional_system_unit_failed` advisory in
drift evidence and remains visible in systemd.

The change **does not** downgrade other failed units. In particular,
critical authority health, OpenBao backup, production watchdog,
release-control transitions, and runtime health continue to block.
Unrecognized systemd units, required unit failures, non-approved
working directories or execution paths, missing required containers,
unapproved running containers, and independent package/freeze/manifest
integrity violations remain fail-closed. The source does **not** remove
any systemd failed state or restart a service.

### Prevent the watchdog from reporting its own successful detection as failure

Production `jason-production-drift-watchdog.service` is a scheduled oneshot
which correctly returns **code 2 when it finds genuine drift** and records
the OPEN breaker. Previously systemd treated that expected result as a
**failed watchdog service**, creating a second, artificial blocking drift
on every subsequent scan. This feedback was independently verified on the
live host November 13: the timer's service had `ExecMainStatus=2`,
`Result=exit-code` and was classified as another `failed_system_unit`.

The existing systemd unit now declares **`SuccessExitStatus=2`**. This
is the entire fix: code 2 still writes the same root-controlled drift
evidence and opens the breaker, but is no longer an execution failure.
Code 1, unexpected exits, crashes and missing watchdog service remain
real failures. No new process, timer, retries, state machine, or exception
to protected freeze/rollback authorization is introduced. Only the exact
source service unit changes; the live root-owned unit is unchanged
without a separately governed release.

Each drift scan continues to report its own observation time; for an
already-OPEN breaker, the watchdog now preserves the initial
`opened_at` incident timestamp while updating `updated_at`, so a
persistent problem does not appear as a newly opened incident each minute.
A PASS with advisories never automatically closes an existing OPEN
breaker. Native protected Production Manager revalidation remains
required.

## Concurrent source coordination (PR #2404)

Active draft PR #2404, a stale, **do-not-merge** first-cutover rehearsal,
also edits `production_drift_guard.py` and its unit tests. We independently
reviewed its two overlaps: its implementation is limited to a strictly
verified masked `jason-release-manager.timer` plus protected production
freeze marker, and its tests are for that intentional release-manager
hold. The present change touches the separate optional system-observer
classification and watchdog self-feedback exit status; it does **not**
unmask or authorize release-manager timers.

Do not merge or deploy PR #2404 as part of this correction. When that
historical draft is reworked, it must rebase against the reviewed current
main and re-run the entire drift regression. Both protections are intended
to remain separately fail-closed.

## Verification and activation boundary

Tests assert optional reporting failures are advisory, both required and
undeclared instances fail closed, prohibited execution paths still block,
true authority-health failures still block alongside warnings, and a
persistent open breaker retains its original incident time. No new
production service, background task, broad exemption, or alternate
break-glass path is introduced.

The change must pass source CI and exact release review. The live
immutable runtime and root-protected release controls remain frozen until
separately authorized. **No production deployment or breaker reset is
authorized by this source work.**
