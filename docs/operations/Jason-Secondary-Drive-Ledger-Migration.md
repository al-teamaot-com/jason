# Secondary-drive orchestration-ledger migration — governed cutover

Status: **Source-only preflight and test evidence. No live ledger has moved.**
Owner direction: use the independent second drive; production changes are
serialized and require exact release-manager authorization through Teams.

## Verified baseline, November 9, 2026

- Root /dev/nvme0n1p2: approximately 233 GiB, 99% occupied; only
  4.2–4.4 GiB allocatable. Archive /dev/sda1, mounted at
  /srv/jason/archive: approximately 234 GiB, 19% occupied; ~190 GiB free.
- Live orchestration-events.sqlite3: ~34 GiB decimal, ~25 million rows,
  active WAL near 915 MB, journal mode wal, zero reusable free pages.
- Live reflection.sqlite3: ~1.86 GB decimal, journal mode delete;
  it is independent and must be migrated and verified separately.
- **Both** jason-runtime and jason-mcp-pilot are active SQLite event
  ledger writers, configured to use the **same existing legacy path** and the
  same writable /var/lib/jason/openclaw bind. Migrating just one process
  would split the event history and is strictly prohibited.
- The runtime's installed settings default the reflection path to the old
  root as a separate explicit variable; changing only the orchestration
  environment variable does not migrate reflection.
- Additional readers are the usage, usage-attribution, security-control and
  autonomy-flight-recording exporters; native runtime diagnostics, JKD-001
  full/frequent operational health and preproduction release checks.
- The existing production release slot is held by a separate, earlier
  candidate. A successful source test is **not** release approval.

## What is implemented without production mutation

tools/jason_secondary_ledger_preflight.py --preflight fails closed on
missing/unmounted/same-device archive, insufficient archive reserve or
inodes, source symlinks or unsafe mode/ownership, unexpected source schema,
an existing target, or split writer-container paths/mounts/inodes. It independently
proves both writer-container ledger inodes equal the host source inode. It uses bounded
read-only SQLite queries, prints no event payloads or secrets, and never
backs up, checkpoints, copies, truncates, moves, unmounts or restarts the
production databases or containers. It requires enough archive capacity to
retain a complete target copy **plus** 20 GiB reserve with the original
database still intact.

The source-only configurability fix makes JKD-001 health and native
jason-ops.sh diagnostics honor the already-defined
JASON_ORCHESTRATION_EVENTS_DB environment variable, leaving the current
path unchanged when the variable is absent. Both paths must be changed
together in a **later** exact-scope release.

A synthetic SQLite backup/restore, last-event readback and schema/integrity
check are tested on small isolated files. This is not an assertion of a
successful full-size production migration.

## Required cutover implementation and acceptance — NOT YET AUTHORIZED

1. Complete the already-queued earlier release and return Production
   Manager to a verified Last Known Good, healthy, unlocked state. Continue
   parallel source engineering, but never open two production transactions.
2. Review the precise new storage profile and host mount. **Do not** add a
   generic writable host-bind capability or a symlink fallback. The existing
   container deployment/rollback code currently clones its prior mounts;
   the target is not yet provisioned and no current installer understands
   a new writable ledger mount. A separate reviewed native release change
   must correctly bind the destination in BOTH writer containers, exporters,
   health units and rollback.
3. Prove exact candidate SHA, manifest scope hash, and rollback SHA, restore
   readiness, signed Teams Owner approval and one-transaction unfreeze
   binding before any service stop, file replacement or writable mount.
   This action is **potentially user-disruptive**. No chat approval or
   standing disk-maintenance permission overrides this boundary.
4. Under a single governed release transaction, quiesce **all** event-ledger
   writers (including MCP) before the final snapshot. Use SQLite's
   transaction-aware backup mechanism, not a plain copy of a live WAL file,
   to create an owner-private 0600 snapshot of BOTH databases on the
   independent disk. Preserve the original database, WAL and SHM intact.
5. Prove per-file identity and expected snapshot source, SQLite
   integrity_check, identical event count, final event rowid, sampled
   event identities, reflection schema and record-count parity, and
   no new source writes after quiescence. Keep immutable evidence and
   SHA-256 digests in the approved archive evidence manifest. A slow or
   failing check means roll back, not skip verification.
6. Activate the new exact mounted path and environment **for both writers
   and every reader** in the same authorized release. Verify backing
   filesystem identity inside each container, write one governed test event,
   and read it back from both writer contexts and all key consumers.
7. If any gate fails, restore the *prior* image, original config and
   original active data source before writers resume. Do not point old
   rollback images at a new incompatible database or accidentally strand
   events written during rollback. This is an explicit test requirement.
8. Only after successful dual-writer, metrics, full/frequent health and
   rollback acceptance may the old primary-disk ledger be considered for
   retirement. Preserve the original as evidence until a separate exact
   retention/safe-retirement authorization is recorded. Root capacity
   cannot be declared healthy until the actual primary bytes are freed
   and verified by the standing independent capacity detector.
9. Recheck production release freeze, automatic-promotion hold and one
   signed Teams approval per transaction. Do not delete OpenBao audit,
   approval records, immutable release images, Docker volumes or unrelated
   worktrees as part of this operation.

## Current blockers

The production freeze and open circuit breaker remain operative. The
earlier release is awaiting signed Teams approval; the old monolithic
engineering worker is intentionally Owner-paused for PMV3 service
separation. Full SQLite integrity timed out after one hour and frequent
JKD-001 health currently fails because it lacks a valid fresh full proof.
The event ledger has no reusable freelist pages, so simple SQLite
vacuum would not provide a root-capacity solution without new storage.

**Do not claim this preflight or its tests achieve the objective.**
The required next engineering deliverable is the native, rollback-safe
dual-writer cutover and post-retirement root-capacity acceptance under the
existing Release Manager. No production operation is authorized by this
document alone.
