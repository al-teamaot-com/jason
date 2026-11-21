# Bounded daily audit-journal migration v1

Status: **dormant source implementation and isolated engineering validation; not deployed or production-authorized**.
Owner request: November 21, 2026 — prepare one bounded migration covering
writer coordination, searchable history, integrity verification and rollback.
Classification: **High-Risk** (shared journal, consumer changes and health-proof policy).
Baseline: a4194c9ee128e1f39938ec175fc52a4fbbd7f52d.
Related work: #1324, #1948 and the Owner-objective framework in #2670/#2671.

This package now includes a source-only exact Root installer, data-recovery services,
component-release plan, archive-backed rollback and safe synthetic tests. None is
installed or activated in production. The installer requires separately verified
Owner identity and an exact one-use approval. It is not an adopted retention policy
or a successful production migration.
Production integration and measured acceptance below are required before an exact
release authorization package can be presented.

## Outcome and boundaries

Keep the live orchestration journal bounded while retaining every committed
event and complete execution/correlation reconstruction. Stop rescanning all
lifetime history as the routine readiness path. Recover through one reviewed
objective, including its data-preserving rollback.

| Item | Bound |
| --- | --- |
| Canonical live journal | /var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3 |
| Archive destination | /srv/jason/archive/governed-audit/orchestration |
| Proposed daily boundary | 00:15 America/New_York; handle 23/25-hour local days |
| Early rollover target | 1 GiB, subject to measured write/verification workload |
| Emergency admission ceiling | 2 GiB including the live WAL; reserve outcome-audit space before admitting new work |
| Proposed final writer-pause budget | 30 seconds, including final delta merge; prove before authorization |
| Proposed rollback tail limit | 128 MiB / 100,000 events; exceed either and rebuild while current writers continue |
| Retention | Preserve all archive history; no age-based deletion in this migration |
| Scope | Orchestration journal, its consumers, maintenance integration, archive custody and the corresponding health-proof format |
| Excluded | Authority/grant/approval DB changes, provider configuration/business writes, arbitrary host cleanup and general Root execution |

Size measurement includes the main database **and its WAL**, not just the
main file. Reserve capacity for already-admitted work to record its outcome.
A capacity stop prevents new admission; it must not turn a provider operation
with an uncertain or unrecorded outcome into a blind retry.

The 1/2 GiB thresholds and pause/tail budgets are proposed engineering targets,
not measured production guarantees. The complete production impact must include
any consumer image replacements, mounts, flags and diagnostic-unit integration.
Do not promise a zero-interruption cutover before drain/reconnect behavior is proved.

## Current evidence and consumers

The current schema is one event table with event-ID uniqueness plus execution and
correlation indexes. The event-store API appends and reads; it has no archive
rotation contract. Frequent read-only health already exists, but its full proof
depends on checking the entire live journal.

Read-only preparation observed the canonical path in Runtime, MCP and Ticket Core
against their running artifacts. Host producers, one-shot
tools, maintenance jobs and integrity readers must also be inventoried. The full
integrity retry is a known current reader. Container names alone are not proof
that every writer has been covered.

Keep current image IDs, paths, open-handle observations and sampled volume metrics
in the private preparation evidence on Jason, not the public source repository.
A complete Root inspection is still mandatory; a UID1000 process scan with denied
/proc entries is not a complete quiescence proof.

## One objective, ordered migration

One future exact approval must cover the complete reviewed source/artifacts,
consumer changes, bounded write pause, initial migration, verification, archive
maintenance policy adoption and rollback. It does not authorize an arbitrary
artifact, new tenant, new provider write, larger disruption or deletion of history.

| Phase | Action | Required evidence / failure behavior |
| --- | --- | --- |
| 1. Inventory and preflight | Bind every producer/reader, source schema and file identity, consumer artifact, Root policy, freeze/hold, storage mounts and rollback source. | Unknown writer, dirty/ambiguous source, insufficient workspace or unavailable archive aborts before data change. |
| 2. Stage compatibility | Prepare archive-aware readers and cooperative writers, dormant by default, and a shared handoff gate. Bind Root policy/catalog and read-only archive mounts. | Every writer version must acknowledge the same gate/catalog generation. Never mix an uncoordinated legacy writer with a rotated canonical path. |
| 3. Drain | Let in-flight provider work reach a safe boundary. Pause new audit-producing admissions and quiesce old SQLite handles; coordinate diagnostic readers. | No forced termination of provider work. If drain or the approved pause cannot be met, resume unchanged and stop before mutation. |
| 4. Cutover | Under the exclusive handoff gate, checkpoint WAL, preserve the closed source, create a small canonical journal and atomically publish the new generation. | Write intent before changes, fsync files/directories and retain before-images. An interrupted intent blocks new admission until independent recovery. |
| 5. Resume | Open each operation against the published generation; do not keep stale SQLite handles across rotation. | Confirm actual appends and reads on every consumer, including cross-boundary executions. |
| 6. Archive closed legacy data | Copy the now-closed history to the independently verified archive filesystem, outside the writer pause. Full-check it, compare event continuity and bind checksum/custody. | Initial legacy verification can be long. Its measured resource/deadline budget is separate from the short handoff. No readiness PASS until complete. |
| 7. Verify recovery copies | Verify a cold restore on the Owner-selected archive drive and prove the archive catalog can reconstruct historical executions. | This scope provides separate-disk archival. It does not claim off-host backup protection. |
| 8. Reclaim exact local before-image | Only after archive-drive restore, reader routing and rollback reconstruction are verified, remove the exact obsolete local copy under the approved scope. | A missing proof retains the local copy. Never delete the active journal, WAL/SHM with live users, archives or unrelated audit/approval data. |
| 9. Adopt recurring operation and health | Use the existing maintenance owner and Root executor, with an explicitly adopted fixed-path daily/size policy and segment-aware health. | No second approval database, bot or scheduler. Handler registration, policy adoption, revocation and custody enforcement require reviewed production implementation. |
| 10. Accept | Complete a real scheduled rollover, cross-segment query, restart/recovery test and native health/revalidation. | A green rehearsal, card, copy or one clean service invocation is not operational acceptance. |

No ordinary raw rename/copy of an open WAL database is allowed. Use SQLite-aware
snapshot/backup and a closed, checkpointed boundary. Archive files must be readable
standalone from a read-only directory; normalize their closed journal format and
prove they do not depend on a writable WAL/SHM directory.

## Runtime and historical reader contract

Preserve get(event_id), list_by_execution and list_by_correlation. Return ordered
events by occurred_at/event_id across active and archived segments. Preserve
identity consistency and duplicate-event rejection across the whole history.
Late events for an older execution go to the current journal and remain discoverable
through the same historical reader.

Publish one atomic catalog generation describing the active journal, closed
pending segments, verified archives, event coverage and proof/custody identity.
Use a stable protected handoff lock. Every producer must participate; a lock added
to the maintenance tool alone cannot coordinate existing live connections.

The production reader requires an archive locator/index and measured fan-out
budget. The rehearsal deliberately scans its small fixture catalog to establish
correctness. That reference behavior is **not** a production performance design.
Do not create a new unbounded all-history payload database or shift the same
whole-file health bottleneck into a growing locator. Validate lookup/index
coverage and bounded verification of its own storage.

Archive paths, profile, catalog and verification receipts must have protected
custody. Reader containers receive read-only archive/profile access, not permission
to replace the catalog or sealed files. An application chmod is not immutable
custody, and a checksum stored alongside an operator-writable archive cannot
independently authorize cached integrity evidence.

## Integrity and backup model

- Active data: produce a bounded, consistent snapshot and run real full integrity
  and restore checks outside the final writer-pause window.
- Newly closed segments: full integrity, complete event-ID/content parity, exact
  coverage boundary and checksum before seal acceptance.
- Sealed history: cache only under an adopted Root-controlled verification catalog
  binding file identity/fingerprint, checksum, proof source/version and custody.
  Replacement, changed fingerprint, missing data, changed verifier or lost custody
  invalidates cached proof. A checksum by itself is not a SQLite integrity check.
- Periodic historical verification: bounded batches with explicit coverage,
  deadline and resource budgets. Do not launch overlapping full scans or silently
  omit old segments. A due/missing/failed verification remains visible and fails
  according to the formally adopted policy.
- Initial legacy segment: one-time full verification and restore/read proof.
  No claim that the old large file becomes cheap to verify just by renaming it.
- Selected destination: the Owner chose the archive drive. Verify event/content
  parity, a cold restore on that drive, reader routing and rollback reconstruction
  before reclaiming an obsolete local copy. This is separate-disk archival;
  off-host backup is outside this scope. A second copy on the same drive is
  restore evidence and never independent/off-host backup evidence.
- Health: current fast/full format stays effective until a separately accepted
  segment-aware format is deployed. Do not extend the existing freshness window,
  write a synthetic PASS, clear failures or force protected control JSON.

### Avoid a circular recovery gate

If the current large-journal timeout is still the production blocker, do not try
to deploy its repair by fabricating the healthy precondition it is meant to restore.
Use only a reviewed exact recovery admission that independently binds the known
failure, current healthy protected peers, source/CI, unchanged authority/freeze and
rollback, with fresh exact Owner authorization. Preserve the open breaker until
genuine post-repair evidence permits normal native revalidation.

This package does not install that admission. A Root recovery exception cannot be
invented by a caller, edited into an old consumed approval or inferred from an
engineering request.

## Recurring daily/size operation

After adoption, the existing maintenance owner evaluates the local-day boundary
and active size. A missed day causes one real rollover, not fabricated empty daily
archives. Size can request earlier rollover; the hard ceiling stops new admission
when a safe rollover is unavailable. Record size, age, pending/unverified bytes,
archive and backup coverage, last successful rollover, check duration and storage
reserve. Deduplicate a concrete Owner exception when bounds cannot be met.

Root performs only the registered fixed-path maintenance action under its adopted,
revocable policy. Routine days do not request another human vote. A changed source,
target, retention/deletion policy, risk or service impact requires a revised
reviewed objective.

## Rollback that preserves new events

1. Stop further rollover scheduling. Keep all archives and native/migration receipts.
2. With current writers still running, build a legacy-schema-compatible database
   from verified history and a consistent active snapshot.
3. Record its catalog generation and active snapshot watermark. Fully verify
   prebuilt history and content parity **outside** the final writer pause.
4. Revalidate the generation. If rotation changed it, rebuild; never merge against
   a stale source set.
5. Briefly quiesce and merge every event committed after the watermark, within the
   measured byte/row/time limits. An exceeded budget resumes current operation
   and rebuilds. Do not hold writers for a whole-history integrity/content scan.
6. Publish the merged canonical database atomically, then restore the exact prior
   consumer artifacts/configuration and resume.
7. Prove the old reader can see historical AND post-cutover events, complete native
   health checks and revalidate through the protected controller.
8. Retain evidence and archives. Data rollback means format/routing rollback with
   all newer committed history preserved, not restoring stale database bytes.

Intent receipts make interrupted cutover/rollback recoverable. An unknown phase
blocks admission until recovered from native facts; it never authorizes another
blind rename, copy, append or deployment.

## Rehearsal and explicit limits

Run only with a new/empty private synthetic workspace:

    clear
    cd /srv/jason/archive/engineering-worktrees/audit-journal-daily-migration-20261121
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=implementation python3 -B tools/audit_journal_migration.py --rehearse /srv/jason/archive/engineering-artifacts/audit-journal-rehearsal-NEW-UNIQUE-ID

The tool has no --apply, production input path, Root installer, provider adapter,
retention scheduler or health-policy activation route. Its catalog format is
explicitly rehearsal-only. It uses the actual event schema and legacy reader.

Tests cover concurrent process writers, day/size/DST rules, archive parity and
standalone format, missing/corrupt archives, duplicate events, interrupted
cutover/rollback, changed-generation rebuild, guarded synthetic reclamation and
legacy-reader rollback including commits made after rollback preparation.

The synthetic final rollback proof scans its small target while holding the gate.
That is intentional for a correctness reference, and is prohibited for the real
large-file implementation. No production pause/latency claim follows from this test.

## Dormant native implementation under review

The legacy store remains the default. An explicit Root-owned profile at
/run/jason/audit-journal/profile.json selects the new adapter only for the
canonical journal. This source does not install the profile or activate a service.

| Source | Implemented behavior |
| --- | --- |
| implementation/orchestrator/segmented_journal.py | Same event-store API; per-operation active connections; shared handoff gate; protected catalog; immutable sealed reads; bounded lookup cache and Bloom filters; global event-ID checks; outcome capacity reservations. |
| implementation/orchestrator/journal_sql.py | Finite writer-UID SQLite operations; standalone checkpointing, full integrity/content proof, online snapshots, filter validation, reconstruction and bounded idempotent tail merge. |
| tools/audit_journal_control.py | Installed isolated Root guard; protected adoption/source checks; one-use initial claim with crash recovery; serialized rotation, seal, scrub, guarded reclamation and event-preserving rollback. |
| implementation/orchestrator/journal_health.py | Consistent active snapshot and cold restore; Root-custodied historical proof/fingerprint coverage; overdue historical scrub rejection. |
| Separate audit_journal operational/fast/full health sources | Explicit-profile integration; the older pinned repair sources stay unchanged. Authority/replay/security/authority-backup checks remain in effect. |
| tools/audit_journal_root_inventory.py | Read-only complete /proc handle inventory and protected baseline metadata; no privileged SQLite queries, credentials, audit payload export or deployment. |
| Native fixture tests | Real SQLite WAL/processes, concurrency, interruption points, two actual UIDs, Root custody denial, post-snapshot event preservation and old-reader reconstruction. |

Pending files use short-lived read connections so old handles cannot obstruct
sealing/reclamation indefinitely. Slow full scans, copies, filter generation and
cold-restore work run outside the exclusive writer handoff. Long hashing of the
prepared rollback file also runs before the final pause; the final gate checks its
Root-protected fingerprint, rechecks the tail budget and merges only the bounded
tail. The legacy-compatible rollback file is reconstructed and verified on the separate
archive filesystem, then published to the canonical path through a Root-validated
file bind. Its boot recovery mapping must be restored before Docker consumers
restart. Only after proof of archive reads, recovery, and event identity may the
original redundant local source be reclaimed. The archive drive is not off-host backup.

New admission pauses only orchestration.request.received. Already-admitted
invocations and their outcome records may finish. Unknown/consumed provider claims
must not be reset, expired or treated as safe-to-retry to force a drain.

The Root controller has no Owner authentication mechanism of its own. Its fixed
production entry requires an immutable installed source closure, a Root policy and
an adoption receipt issued by the existing independent Owner verification path.
Scheduled maintenance cannot claim initial cutover or replay a consumed initial
claim after rollback. There is no deployed Root archive action yet. The dormant installer and four
systemd units are source-prepared and remain gated on exact provenance, live
Root inventory, signed Owner approval, and production postflight.

## Work required before a production authorization request

- Bind the complete Root-authoritative inventory to the exact consumer image,
  configuration, native health and release-control scope.
- Review the dormant native implementation and complete the release bootstrap,
  native health installation and existing maintenance integration.
- Measure representative event volume, payloads, lookup fan-out, pause time,
  rollback tail, copy/check duration, storage/memory/I/O reserves and failure
  behavior; validate or amend the proposed numeric limits as one reviewed scope.
- Test power-loss publication boundaries, ambiguous outcomes, missing mount,
  bad restore, full disk, inode/link substitution, custody/revocation and safe
  restart of the actual consumer artifacts.
- Prepare immutable release artifacts, exact rollback references and a signed
  objective manifest using the existing release/approval boundary.
- Complete controlled native acceptance and one scheduled cycle after approval.

Preparation does not grant production authority. Keep the existing
Owner-objective installation candidate and its protected source unchanged while
this review branch is open.

## November 21, 2026 source validation and release-preparation checkpoint

- Local CI-equivalent pytest invocation: 130 PASS, 0 FAIL, including the
  original event-store/reconstruction and production-health compatibility suites.
- Focused release/recovery tests: 17 PASS. A wider focused suite: 90 PASS.
- No-network, no-host-mount disposable native Root fixture: PASS; actual UID 1000
  SQLite WAL reads/writes, independent filesystems, Root custody, tested
  cross-filesystem file-bind and recursive consumer mount, archive reconstruction,
  recovery and reclamation, interruption/one-use protections and reboot mapping.
- Documentation control and JSON syntax: PASS; source Python compile: PASS.
- These tests demonstrate synthetic behavior only. They do not demonstrate a
  production 44 GiB migration, 24-hour scheduled recurrence, actual three-image
  production substitution or native Root release acceptance.
- Exactly scoped sources: `tools/audit_journal_release_scope.py` and
  `tools/audit_journal_install.py`; dormant data-recovery and maintenance units in
  `infrastructure/jason-audit-journal/`. Source adoption must reconcile the
  pending protected Main `a4194c9...` Owner-objective installer deliberately,
  never overwrite its pinned source or reuse its consent.
- The source-only Root path requires a current healthy breaker/drift result,
  matching freeze/pause/hold hashes, complete Root process/producer inventory,
  exact historical schema, archive capacity and custody, and one authenticated
  Owner exact-action approval. Do not weaken failing gates to force release.
- Explicit outstanding production acceptance: true provider/consumer continuity,
  full initial archive parity/cold restore, genuine redundant 44 GiB reclamation,
  live boot recovery, actual scheduled rollover, independent native full/fast
  health/revalidation, and rollback preserving post-cutover events.
- Storage policy is separate-disk preservation of all events with no off-host
  backup claim and no age-based historical deletion.

**Authorization state:** This checkpoint is engineering evidence only, not a
request to execute a production cutover or permission to modify production.

### Continued recovery-hardening regression (November 21, 2026)

The source-only candidate also tests Root-claimed disposable work recovery
after interruption. Cleanup must honor creation claims, inode/device identity,
link rejection and a strictly bounded work parent; it may not remove retained
history or unclaimed directories. Eleven dedicated negative/positive tests pass, including
a readback requiring real events from both active and sealed history.
The expanded local event-store, health, migration, legacy reconstruction and
release regression suite passes 141 tests, and the isolated UID0/UID1000 native
fixture also passes. These remain non-production proofs and grant no production
authority.
