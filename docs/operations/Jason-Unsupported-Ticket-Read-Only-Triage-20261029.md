# Jason unsupported-ticket read-only triage — P0 #770

## Scope and purpose
A ticket with no promoted matching playbook must not silently vanish from the
worker's responsibility. The fallback collects **read-only** evidence,
stores its outcome durably, and records the next action required. It neither
turns unsupported tickets into eligible remediation work nor claims resolution.

The stage runs after normal promoted-playbook processing and examines at most
two unsupported tickets per scan by default. Existing admission and technician
ownership guards still apply. It does not claim assigned technician tickets
or non-Jason In Progress discovery tickets.

## Evidence and authorization boundaries
- Use the exact-ID, authoritative ticket snapshot already obtained by the
  governed queue search. Do not call service.ticket.read: the standing
  autonomous-worker information-release policy intentionally does not permit
  that separate capability. Governed notes-history read remains ticket-ID bound.
- Verify same-company ticket and active configuration item; require exact
  DRMM UID and matching endpoint identity/hostname before device diagnostics.
  No cross-tenant guessing or device-name inference.
- For independently verified online Windows endpoints only, use fixed
  read-only Windows licensing, RocketAgent service or disk capacity commands.
  Other cases receive ticket/device evidence without endpoint commands.
- Store allowlisted telemetry, not unrestricted PowerShell output or secrets.
- No Autotask updates, queue claims, notes, client communications,
  disruptive scripts, restarts, cleanups, patches or reboots.

## Durable lifecycle
The SQLite table autonomy_unsupported_triage contains ticket identity,
source version, category, outcome, allowlisted evidence, next step, attempt
count, checked-at, next-due and error type. Outcomes include read_only_assessed,
needs_company_identity, needs_device_identity, waiting_device_access,
diagnostic_not_applicable, needs_security_review, needs_playbook_review,
governance_blocked, read_failed_retry and needs_human_review.

Old triage rows recorded by the earlier implementation as governance_blocked
are re-evaluated once on upgrade via a safe, versioned evidence marker;
production SQLite rows are not edited directly.

A successful read-only assessment refreshes daily or upon source version
change; offline tickets retry after 15 minutes, missing identity after four
hours, and transient read failures with bounded 5-60 minute backoff. Governed
read denial never grants new privileges; it is recorded and delayed 24 hours.
After three transient failures, Jason records needs_human_review with a
technician-action reason. Conflicting authoritative identities record an immediate
needs_device_identity outcome, not repeated blind provider reads. One ticket's
failure never consumes another's remediation work slot.

Read-only operator count query:

    python3 -c "import sqlite3; c=sqlite3.connect('file:/var/lib/jason/openclaw/autonomy-operational-work.sqlite3?mode=ro',uri=True); print(c.execute('SELECT state,COUNT(*) FROM autonomy_unsupported_triage GROUP BY state').fetchall())"

## Acceptance and remaining work
Require integration tests for tenant isolation, exact identity, endpoint
availability, fixed-command allowlist, retry, source change, restart persistence,
no provider mutation and coexistence with existing playbooks. After an exact
approved production deployment, verify ledger entries for real unsupported
tickets and two complete scans, and confirm read canaries and release health.

This is **diagnosis only**, not verified resolution. Publishing internal notes,
human escalation and actionable generic playbook advancement require separate
governed promotion, provider readback and real-ticket acceptance. Issue #770
remains open until eligible tickets are consistently advanced and resolved.
