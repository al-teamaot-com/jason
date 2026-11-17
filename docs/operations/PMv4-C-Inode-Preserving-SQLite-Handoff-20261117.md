# PMv4 Stage C — zero-copy shared SQLite migration under one governed transaction

Status: SOURCE-ONLY; not deployed. No live service, provider, database, WAL,
host lock, production freeze/hold, Owner approval or production revision changed.

## Why zero-copy is necessary

On November 17, read-only inspection of the existing host showed:
- Orchestration audit SQLite: approximately 41.2 billion bytes (39 GiB disk
  allocation) plus roughly 1.1 GiB of active WAL; journal_mode=wal.
- Reflection SQLite: approximately 2.3 billion bytes (2.2 GiB).
- Ticket operational ledger: approximately 20 MB.
- All paths are on the same ext4 device, /dev/nvme0n1p2 (st_dev=66306).
- The filesystem was about 88% utilized, with about 27.9 GB reported free.
  A full second copy of the orchestration database is NOT a safe cutover plan.
- Both the live jason-runtime and jason-mcp-pilot processes have audit and
  identity databases open. The parent and child ticket workers also hold
  promotion, targeted wake and operational ticket files.

A worker-only migration would not achieve isolation or single authoritative
state. Under current governance, the move cannot execute until the Owner
approves the separately scoped production release that quiesces all affected
producers, including MCP, and preserves their current production guarantees.
A stop, restart, shutdown or interruption without that authorization remains
forbidden. No unreviewed copy/symlink/wildcard-secret shortcut is authorized.

## Reusable source-only handoff library

tools/pmv4_c_sqlite_family_handoff.py is not a CLI or an authorization
issuer. It provides (1) exact read-only inode and WAL-family discovery,
(2) active-open-file denial using pinned Linux lsof, (3) an atomic same-device
RENAME_NOREPLACE transfer of exact database, WAL, SHM, and worker-lock files,
(4) durable intent/move/complete events in a separate root-owned mode-0700
journal directory, and (5) an inode-based pre-new-writer rollback reconciler.
It moves zero database-content bytes. It never uses os.rename to overwrite an
unknown target, never deletes the old ledger, and never copies a live WAL.

Caller requirements: A separate authenticated exact Owner release must
enforce protection of the original production runtime/freeze/hold, quiesce every
writer, block new admissions, bind the exact source/destination/UID/inode journal
and release SHA, and hold exclusive host/root release locks. The mover requires
the independent host fence and producer-quiescence callbacks before every move.
It refuses unexpected new or mismatched files, symlinks, permissive modes,
hard links, filesystem mismatches, active SQLite handles, missing lsof,
occupied target names and journal tampering. The journal must be separate from
worker-writable state; the production caller must execute as root and require
journal_owner_uid=0. Any interruption leaves a durable root journal for
a separately governed reconciliation.

Recovery: A rollback to original paths is permitted only if an independent
root check proves no new worker/other service has written the moved database
and no new provider action, ticket claim or notification has occurred. After any
new authoritative write, retain the new ledger and recover the producer or
service against the new canonical path; never overwrite new state with a
stale original database.

## Actual outstanding release dependencies

- The current production MCP and runtime both use the broad original state
  root. The exact source must route all their canonical paths to the new state
  roots as part of the same governed transaction. A newly hosted external
  worker must use the same inodes and persistent owner locks, not a copy.
- The original governed-execution.sqlite3 and resolution-memory.sqlite3
  were mode 0644 on the live source. This preflight deliberately denies that
  mode, rather than silently changing protected production permissions.
  A separately reviewed, exact root repair/migration is required.
- Existing settings, additional worker-owned DBs such as client questions,
  enabled connector roles, and the full effective Docker security/egress
  profile must be reconciled before approval. No container is authorized.
- No universal live source cutover/rollback script, root signed release packet,
  serialized owner authorization, or two real external provider-backed scan
  acceptances have yet passed.

## Evidence and acceptance

Source tests cover exact allowlisted family names, source and WAL sidecar inode
parity, atomic no-overwrite, a real SQLite record surviving relocation,
foreign/malformed targets, open-file denial, symlink/mode/file identity denial,
the protected journal hash chain, synthetic mid-transaction interruption,
in-place reversal before any new write, and refusal of rollback after any new
writer. The shared source-only Stage C CI gate runs these tests. A green
source-only gate is not a production authorization or a production verification.
