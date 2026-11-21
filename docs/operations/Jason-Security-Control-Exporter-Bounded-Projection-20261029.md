# Security-control exporter full-scan repair (Issue #770)

## Confirmed live cause

The exporter at port 9471 timed out while its service remained active.
Its collect_counts queried orchestration_events by event_type using a
parameterized IN predicate followed by fetchall. The WAL SQLite audit
database was 26.26 GB, with more than 19 million rows, and had no
event_type index. EXPLAIN QUERY PLAN was a full table scan, repeated on
every metrics request. Prometheus reported 13/14 targets healthy, so
Production Manager's CCC pre-mutation gate denied the previously
authorized Teams notification rollout.

Git history: original exporter commit aa0d6c5c3 (2026-09-24),
and current full-scan query a47586224d (2026-09-30), introduced under
the Project Jason Documentation Automation commit author with title
"Bound observability audit scans." Author metadata does not prove who
physically wrote the source.

## Source correction

A bounded read-only projection scans append-only audit records by the
existing SQLite rowid primary B-tree, with up to 5,000 rows per batch
by default and a pause between batches. HTTP /metrics reads only an
in-memory snapshot: no database connection, query, disk fsync, or
audit write occurs on the HTTP request thread.

Only allowlisted control counters and low-cardinality termination
reason counts are stored. No raw audit payload, ticket or client details
are written to checkpoints or metrics. The raw payload is fetched only
for execution-plan denied and request-terminated events.
Existing metric names and aggregate meanings remain intact when the
initial historical catch-up completes.

A private checkpoint stores only the cursor, a hash of the most recent
event ID, source device/inode identity, and aggregate counts.
On restart, verify all source identities, rowid validity, final event
hash, types, and allowlisted label names before resuming. Invalid
checkpoints fail closed and rebuild from row zero, never fabricate totals.

Until catch-up reaches the observed audit head, or when audit reads
are unavailable or stale, jason_security_control_audit_available=0
and historical count series are deliberately withheld.
New gauges expose catch-up, rowid progress and checkpoint status.
A Prometheus up target alone does not mean the audit counts are ready;
two new alerts report sustained incomplete projection or checkpoint failure.

The systemd unit adds only a private StateDirectory. No provider or
audit database write permission is added. The original audit DB
schema, WAL, audit records and active writers remain unchanged.
No live event_type index or VACUUM is required.

## Verification

- Original security exporter tests remain passing.
- New tests cover batch boundaries, complete and partial totals,
  restart recovery, checkpoint integrity, stale fail-closed behavior,
  secret-safe counters, concurrent WAL audit writes, and rowid query plan.
- Read-only batches against the real 26 GB audit database measured
  about 2.5 ms / 1,000 rows, 8.5 ms / 5,000 rows and 30 ms / 20,000
  rows. No live database writes were performed.
- Deploy only under scoped approval with original exporter unit and
  source rollback available; no live source or exporter service changed
  while creating this patch.

## Operational acceptance

1. Install the reviewed exporter-specific source and systemd unit under
   a governed scoped maintenance process. Preserve the original unit
   and source as immediate rollback.
2. Verify ten consecutive promptly responding metrics scrapes under
   normal audit-write load, bounded projection cursor advancement
   and stable 14/14 Prometheus targets.
3. Verify audit_available stays 0 until complete, then sampled
   historical counters exactly match source evidence and update when
   new events arrive. Restart exporter only if explicitly authorized,
   validating checkpoint recovery and dedupe.
4. Verify original security alerts remain intact and new completeness
   alert rules are loaded through the normal Prometheus control path.
5. Only after CCC passes may Production Manager reattempt the approved
   exact Teams SHA. Never bypass CCC or widen the endpoint change scope.
