# P0 — Audit authority-health private WAL reader repair

## Verified incident and constraint

The 2026-11-25 root-accepted audit forward release is accepted; maintenance
reports scheduled_no_restore_verified. The jason-openclaw-authority-health
service fails sqlite3.OperationalError: unable to open database file under
ProtectSystem=strict and the root circuit breaker opens. The active journal is
a 0600 al-owned SQLite database in WAL mode within a 0700 shared directory.
The installed service can read files, but the installed 95 drop-in only
conditionally permits an *already existing* -shm file. SQLite needs to create
its own -wal and -shm auxiliaries when the database has no live clients.

The original writable-parent sandbox proposal (closed, unmerged PR #2735) is
REJECTED: a created WAL file can contain canonical journal data, and the
proposed directory-write exception allows its modification by the reader.
A synthetic filesystem permission test shows why the old fix is insufficient.
User-managed systemd namespaces were shown NOT to enforce ProtectSystem=strict,
so their successful runs are NOT live-root acceptance evidence.

## Candidate source behavior

The proposed solution changes two existing files, never the systemd
sandbox's writable access:

1. implementation/orchestrator/journal_health.py: on a segmented journal,
   take the existing journal handoff gate exclusively for a bounded
   read-only, O_NOFOLLOW copy of the canonical active file and any existing WAL
   into a private temporary scratch directory, verifying ownership, 0600
   modes, inode, size and mtime identity. SQLite queries, integrity backup,
   restore comparison and validation of outcome age use the scratch copy.
   The source journal and WAL are not opened by SQLite and not modified.
2. tools/openclaw_authority_fast_health.py: preserve the exact already
   installed native journal full-proof validation and redirect only the
   adopted orchestration-audit schema probe through the same private-copy
   reader. Other authority and security database checks are untouched.

All copied WAL/SHM files and SQLite transactions operate in already writable,
private, disposable scratch (/var/lib/jason/openclaw for fast health and
/srv/jason/archive/authority-health-scratch for full health). The journal
handoff lock prevents governed writers from changing the source during the
copy. The target private files do not survive the check. The helper requires
segmented mode; legacy-mode policy remains unchanged.

## Tests and limitations

- 28 focused journal + native frequent-reader tests PASS.
- 106 combined native health/journal/maintenance regressions PASS.
- Separate synthetic test proves live WAL contains a committed table and the
  private copied DB returns its row, with identical source journal/WAL hashes
  before and after; 11 targeted journal health tests PASS.
- No code was executed against live protected journal using mutable source.
- Root-only sandbox and actual installed runtime fast/full proof: NOT VERIFIED.
- The new copy takes the existing journal gate exclusively while reading the
  active file (currently ~17 MiB; bound by the existing ceiling). This
  temporarily delays governed writers and requires operational review before
  production activation; no change to writer/provider authority.

## Exact governed root repair — proposed, NOT authorized

Action identifier: REPAIR-EXACT-AUDIT-HEALTH-PRIVATE-READER.

Install targets only:
- /usr/local/lib/jason/audit-journal/trusted/implementation/orchestrator/journal_health.py
- /usr/local/lib/jason/audit-journal/native-health/openclaw_authority_fast_health.py

The immutable packet must pin source SHA, both exact file candidate digests,
the live installed before-image digests/modes/uid, current maintenance
acceptance, approved root health policy, one-use Owner signature, rollback
bytes, and both existing health unit names. Previously consumed audit adoption
or no-restore approvals must NOT be reused.

Within trusted root release locks, verify exactly the two targets and before
images, no unexpected write paths, and no concurrent health unit execution.
Use the protected native installer to atomically replace only these two
files, preserving original uid/gid/mode. No daemon reload is necessary
because service directives and environment do not change. Do not touch the
audit journal database, append outcome, recycle containers, change the
systemd sandbox, suppress failures, or reset the breaker.

Run exactly authorized health service acceptance. Require a fresh successful
frequent proof and valid independent full proof, maintenance timer health,
drift PASS and breaker CLOSED on consecutive watchdog observations. On any
failure, atomically restore both exact original bytes, revalidate installed
file custody and service health, and record immutable failure/rollback
evidence. If a new root blocker arises, fail closed.

Source PR review, tests, and local packet preparation do not constitute
authenticated Owner release approval or production acceptance.
