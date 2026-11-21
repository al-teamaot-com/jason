# Bounded daily audit-journal migration v1

Status: **engineering preparation and synthetic rehearsal only**.
Owner request: November 21, 2026 — prepare one bounded migration covering
writer coordination, searchable history, integrity verification and rollback.
Classification: **High-Risk** (shared journal, consumer changes and health-proof policy).
Baseline: a4194c9ee128e1f39938ec175fc52a4fbbd7f52d.
Related work: #1324, #1948 and the Owner-objective framework in #2670/#2671.

This package is a reviewable migration specification plus executable data-safety
rehearsal. It is not a production installer, an adopted retention policy, a
production event-store replacement or a request to approve unfinished deployment.
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
| Emergency admission ceiling | 2 GiB; fail closed with a capacity exception if maintenance cannot proceed |
| Proposed final writer-pause budget | 30 seconds, including final delta merge; prove before authorization |
| Proposed rollback tail limit | 128 MiB / 100,000 events; exceed either and rebuild while current writers continue |
| Retention | Preserve all archive history; no age-based deletion in this migration |
| Scope | Orchestration journal, its consumers, maintenance integration, archive custody and the corresponding health-proof format |
| Excluded | Authority/grant/approval DB changes, provider configuration/business writes, arbitrary host cleanup and general Root execution |

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
| 7. Verify recovery copies | Verify an approved independent backup, restore/read it and prove the archive catalog can reconstruct historical executions. | The archive disk alone is not a complete backup strategy. A second directory on the same disk is not independent backup evidence. |
| 8. Reclaim exact local before-image | Only after archive, independent backup, reader routing and rollback reconstruction are verified, remove the exact obsolete local copy under the approved scope. | A missing proof retains the local copy. Never delete the active journal, WAL/SHM with live users, archives or unrelated audit/approval data. |
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
- Backup: preserve event IDs and content. Verify another approved recovery copy
  and its restore before reclaiming the local original. The rehearsal's second
  synthetic copy explicitly reports independent_backup_verified=false.
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

## Work required before a production authorization request

- Complete Root-authoritative consumer/open-handle inventory and exact image/
  configuration/source scope.
- Implement and review production writer/reader routing, protected catalog,
  archive locator, Root maintenance handler and independent backup integration.
- Measure representative event volume, payloads, lookup fan-out, pause time,
  rollback tail, copy/check duration, storage/memory/I/O reserves and failure
  behavior; validate or amend the proposed numeric limits as one reviewed scope.
- Test power-loss publication boundaries, ambiguous outcomes, missing mount,
  bad backup, full disk, inode/link substitution, custody/revocation and safe
  restart of the actual consumer artifacts.
- Prepare immutable release artifacts, exact rollback references and a signed
  objective manifest using the existing release/approval boundary.
- Complete controlled native acceptance and one scheduled cycle after approval.

Preparation does not grant production authority. Keep the current a4194c9
Owner-objective installation candidate and its protected source unchanged while
this review branch is open.
