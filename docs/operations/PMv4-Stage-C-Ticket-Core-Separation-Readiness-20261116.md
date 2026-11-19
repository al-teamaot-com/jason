# PMv4 Stage C — independent Ticket Processing owner, live cutover blockers

**State:** Source-only preflight available; Stage C remains NOT deployed. This
record updates November 11's source-only assumption using live November 16 evidence.

## Independent current production baseline

The original protected production runtime `jason-runtime` image
`sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`
was independently checked live and runs the embedded ticket worker.
All future release/rollback decisions must revalidate the current image SHA.
The live worker's child process, not its parent supervisor, owns a kernel
`FLOCK` on `autonomy-operational-work.sqlite3.owner.lock` UID 1000,
mode 0600, and the physical ledger/lock share a device. This proves Stage B's
exclusive embedded lock is already operational; avoid redundant live restarts.

Four distinct recent ticket-scan rows contain zero duplicate provider items.
A connected, governed Autotask before-release read canary on November 16
verified 19/19 ticket IDs and one exact read with no provider error or customer
content returned. Read-only SQL checks found zero duplicate work IDs, note
identities, semantic note identities or notification keys. None of these
receipts proves an actual **external worker** handoff or resolution of existing
WAITING/BLOCKED ticket backlog.

## Genuine remaining Stage C boundary

The current SQLite DB and its WAL/SHM/lock sidecars live in the **broad**
`/var/lib/jason/openclaw` state directory, which the current HTTP runtime
mounts writable with unrelated PMv3 work. Giving this mount to a second worker
violates the component isolation design. Bind-mounting only the DB file or
hard-linking a second lock path also risks independent SQLite WAL handling or
split-brain dispatch and is **not a valid workaround**.

Before any live cutover, a separately governed exact Owner release must
establish the one authoritative ledger under an isolated
`/var/lib/jason/ticket-core` directory, with verified original SQLite and WAL
consistency, immutable original backup, exact inode continuity, and fixed
versioned rollback. This must be done under a serialized work-admission hold,
with no in-flight provider mutations or unaccounted claims. Both embedded and
future external worker must be tested against the **same** durable data and
persistent lock inode. Do not copy/rename the SQLite database while the worker
is running. The old original source and complete ledger history must remain
recoverable until after independent provider-backed acceptance.

A future component-owned external worker requires a separately reviewed,
minimal provider credential and outbound egress projection. The current
`tools/pmv4_ticket_core_cutover_preflight.py` deliberately accepts only a
dedicated data mount; **all** additional read-only and writable mounts
(including credentials) fail until exact authorization/projection exists.
It is a reusable negative release gate, **not** a credential installer.

## Acceptance and production sequencing

1. Exact immutable source, Owner authentication, freeze/hold and native lock,
   rollback/image evidence, health and provider-read baseline.
2. Preserve current functional embedded worker while engineering isolated
   source/credential projection, installer and rollback in nonproduction.
3. Obtain separate exact transaction approval before changing live data path or
   worker mode. In-flight work must be accounted for and safely quiesced.
4. After lock owner release, launch **only one** external ticket worker, with
   the HTTP runtime remaining healthy and its embedded worker disabled.
5. Verify two distinct real scheduled Autotask scans, same ledger/lock inode,
   stable queue and approved actions, no duplicate jobs/notes/claims, original
   notifications/approval paths and producer read/write authorization.
6. Verify root rollback restores the precise last-known-good operational
   worker/data version. Keep freeze and promotion hold unchanged.
7. Do not claim Stage C complete until actual production cutover, provider
   receipts and anti-duplicate readback are independently verified.

## Source-only acceptance

The verifier reads only SQLite scan-cycle aggregates and precise kernel-file
identity metadata. It never copies the ledger, acquires the dispatch lock,
changes a service, creates provider work, starts containers or requests an
Owner approval. It rejects unsafe data mounts, symlink/UID/mode and ledger/lock
inode differences, duplicate scan samples, missing dedicated state, and all
unknown credential projections. The only live result at this checkpoint is
`status=read_only_baseline_verified`,
`external_cutover_ready=false`, `production_mutations=false`.
