# Audit journal WAL health sandbox — source-only governed repair candidate

## Verified incident

On November 25, 2026 the root-accepted audit forward release remained accepted
and scheduled maintenance reported scheduled_no_restore_verified, but
jason-openclaw-authority-health.service failed with
sqlite3.OperationalError: unable to open database file. Root drift reported
failed_system_unit and opened the release circuit breaker. The journal data
file is an al-owned 0600, WAL-mode SQLite database in a 0700 shared directory.
A normal al host reader can open it. The health unit runs as al with
ProtectSystem=strict; installed 95 drop-ins only permit an optional exact
-shm file, which is often absent when there are no active WAL clients.

A synthetic SQLite WAL file proved that with absent WAL auxiliaries, a parent
directory without creation permission prevents a read-only query, while a
writable parent permits the query and creates -wal and -shm auxiliaries.
This establishes the filesystem requirement but not production acceptance.
User-managed transient systemd tests did NOT enforce ProtectSystem=strict in
the /srv mount, so they are not valid tests of the real root-managed sandbox.

## Proposed bounded repair

tools/audit_journal_health_wal_sandbox.py ONLY renders and validates two
additive 96-audit-journal-wal-health.conf service drop-ins:

- jason-openclaw-authority-health.service
- jason-openclaw-authority-full-integrity.service

It does not change ExecStart, Owner credentials, timers, journal writers,
database contents, LKG, the circuit breaker, or existing 91/92/94/95 drop-ins.
It permits WAL auxiliary creation in the exact shared directory while mounting
the active audit database and all five reviewed sibling database files
read-only. Known optional WAL auxiliaries are read-only as appropriate, and
the internal journal-work directory is inaccessible to these services.

SECURITY BOUNDARY: A directory-level ReadWritePaths exception is broader than
a file-only optional -shm allowance. File-level read-only mounts mitigate, but
do not eliminate, the possibility of new file creation under that directory.
The source-only preflight rejects unknown current directory entries and
untrusted identities. Real root-managed isolated mount testing MUST prove that
protected data files remain read-only and missing WAL sidecars can be created.
If the residual directory scope is unacceptable, this candidate must not be
released. Choose a separately reviewed bounded snapshot reader instead.

## Test and release gates

- Host normal al reader, WAL-mode database: PASS.
- Synthetic WAL mode, no auxiliaries, readonly directory fails and writable
  directory succeeds: PASS.
- Pure renderer and strict current live directory inventory: PASS.
- Generated unit overlays, offline systemd-analyze verify: PASS.
- Real ROOT systemd sandbox with synthetic DB: NOT VERIFIED.
- Root exact Owner approval and native release/rollback: NOT PRESENT.
- Fast/full health, drift and breaker repeated live postflight: NOT VERIFIED.

## Exact-action governed release proposal

Action: REPAIR-EXACT-AUDIT-HEALTH-WAL-SANDBOX.

1. Independently authenticate Owner and grant this exact new action, bound to
   immutable source SHA, two target paths/hashes, baseline hashes, residual
   directory-creation scope, rollback, and authorized health-check units.
   Historical adoption/no-restore approvals remain immutable and cannot be
   reused. Freeze and all other root protections remain effective.
2. Under existing root release locks, recheck source revision, installed
   94/95 before-images, accepted audit receipt, journal directory inventory,
   active file identity, exact candidate bytes and rollback manifest.
3. In an isolated ROOT-managed transient unit using a SYNTHETIC database,
   verify ProtectSystem=strict, no sidecars to start, correct read-only query,
   creation of only WAL auxiliaries and read-only protection of ALL six
   database files. Abort for any broader file-write ability.
4. Atomically install only the two 96 drop-ins as root:root 0644 and execute
   a bounded systemd daemon reload. Do not retarget links, reboot, restart
   runtime/MCP/containers, touch the audit database, or reset the breaker.
5. Under this exact repair authorization, verify fresh fast/full health,
   scheduled audit maintenance, continuous drift PASS and breaker CLOSED for
   consecutive checks. Keep rollback ready during live verification.
6. If any gate fails, remove only the two new 96 drop-ins, reload systemd,
   verify the exact before-image, persist rollback evidence and escalate.

Source code in a mutable development worktree is not an authorized root
executor. This document is a review packet, not installation authorization.
