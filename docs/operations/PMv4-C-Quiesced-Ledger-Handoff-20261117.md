# PMv4 Stage C — quiesced SQLite ledger handoff primitive

**Status:** Source-only preproduction helper. No production DB, WAL, SHM, lock, service, provider, Owner proof, or container has been changed. No approval is being requested or implied by this file.

## Reuse current runtime instead of engineering a new Ticket Core

The existing embedded worker already owns an exclusive child-process flock on `autonomy-operational-work.sqlite3.owner.lock`. The same source also supports `JASON_TICKET_WORKER_HOSTING=external`, `python -m jason_runtime.ticket_worker_service`, and a configurable `JASON_AUTONOMY_WORKER_DB`. Stage C needs a **single** authoritative ledger in `/var/lib/jason/ticket-core` and a future independently hosted worker that references that exact mounted directory and lock. Retain all current provider approval, durable work, notification, ticket queue and anti-duplicate rules. Do not build a parallel ledger or ticket engine.

The live ledger currently sits under the broad `/var/lib/jason/openclaw` state mount. Mounting that directory into the independent worker, copying only a SQLite file without committed WAL, or linking separate lock files would violate isolation and could cause missed/duplicate work.

## Reusable handoff library

`tools/pmv4_ticket_core_ledger_snapshot.py` has **no command-line apply mode** and must be called only from a future independent exact-Owner, root-protected release transaction that separately proves actual producer quiescence and accounts for in-flight work. It does **not** accept or mint Owner approval, stop a worker, change hosting mode, launch a provider, or install a service.

Given the protected original and an already created root-owned 0700 isolated directory, it verifies the original SQLite ledger and persistent worker-lock file are trusted UID 1000/mode 0600, on one filesystem, with one inode each. It acquires the actual worker lock nonblocking; if another embedded worker owns it, the snapshot fails before creating a target. A read-only SQLite backup includes committed WAL state without copying mutable WAL/SHM files. It validates SQLite quick check, required heartbeat and scan-cycle tables, row-count/scan parity, stable source database+WAL metadata and original lock inode before installing a complete destination. It atomically installs a UID1000/mode0600 database and persistent lock in the dedicated directory with fsync. It retains the original source and returns bounded hash/inode/count evidence (never customer ticket content). Source mutations, symlinks, unknown existing targets, ownership mismatch and active locks fail closed. Interrupted precommit attempts remove only their own exact staged lock/temp files; once the destination is installed, errors retain evidence for root-authorized reconciliation.

## Governed cutover, rollback and acceptance that still must be built

1. Bind the snapshot invocation and exact target mount to a new signed Owner scope and protected host release transaction. Ensure all SQLite producers are quiesced and provider claims are drained. **No running-source copy is authorized**.
2. Capture a complete original backup and approved rollback image; invoke the library once, record SHA, inode and logical scan counts. The original DB and its WAL-related recovery state must remain protected.
3. Deploy a separately owned external worker using the existing runtime code, an independently reviewed **minimal** credential/egress projection, the dedicated directory only, and a pinned image. Do not project the entire `/var/lib/jason/openclaw` state or arbitrary OpenBao secrets. HTTP runtime switches to `external` mode only in the same serialized transaction, and must stay healthy.
4. Prove that embedded and external references resolve to the same **new** ledger and persistent lock inode, that a second claimant fails, and that two separate real scheduled Autotask scans succeed with no duplicate provider actions, work IDs, notes or notifications. Keep the signed freeze/hold and MCP unchanged.
5. **Rollback after any accepted new-ledger writes must retain that new authoritative ledger.** Return to a lock-aware embedded owner using the new ledger if the external service fails; never restore an old SQLite copy and silently lose committed work. A rollback to the historical original path is permitted only if an independent signed gate proves no new ledger writer or provider action was admitted after snapshot.

## Verification evidence

The existing C read-only live gate remains NOT READY for cutover until the separate service and credential projection exist. Disposable tests exercise committed WAL state, free/contended lock, safe target creation, duplicate/unknown target, symlink/mode/ownership rejection, schema mismatch, mid-copy source mutation and interrupted target install. These tests are included in the **existing** Stage C GitHub CI workflow rather than creating another independent approval layer.

**No production effect:** The merged A0/A1 deployment and current embedded ticket worker remain unchanged by this source helper.
