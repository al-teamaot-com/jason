# Audit journal: Owner-directed 30-day permanent database retention

State: data engineering preparation. No production database modification authorized by this document. Evidence as of November 23, 2026.

## Exact objective

For the canonical local SQLite orchestration journal at /var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3, retain **only records with occurred_at at or after (UTC cutover time - 30 days)**. Permanently remove older records from the live database family once a governed transfer has been accepted, not merely archive or relocate those records. Repeat daily so age-based retention remains effective. The owner explicitly rejected all-history archive as the solution.

The existing audit journal migration proposal requires all history to be retained and cannot be reused as though it approved a destructive retention change. The Jason Canon describes Audit as a permanent record, and the Architecture Catalog describes the orchestration evidence store as append-only. A revised retention classification and exact governed production release approval are necessary to reconcile that conflict. Until they are approved, the source and all other historical records remain untouched.

Retention scope is solely the orchestration_events table in the canonical local journal. Separate approval chains, customer/provider records, other journal databases, recovery evidence, and immutable Root authorization ledgers are **not** deletion targets. This proposed distinction must be confirmed by the independently authenticated exact-scope release authority.

## Verified discovery

At 2026-11-23T19:27 UTC, live journal held 34,088,082 rows. Under cutoff 2026-10-24T19:26:00+00:00, 15,564,333 were older and 18,523,749 were recent. Original database used 46,777,184,256 bytes, plus ~1.25 GiB WAL. The Root disk was 97%-98% used; archive disk had more than 140 GiB available. SQLite page freelist count was 0 and auto_vacuum=0. Simple DELETE does not reclaim ext4 space; in-place VACUUM has insufficient root headroom and would risk exhausting the production disk.

## Implementation phases

1. **Non-mutating source snapshot:** build a recent-only SQLite file on a separate physical volume with the canonical schema, event IDs and indexes. Source connection is URI mode=ro, PRAGMA query_only=ON in a read transaction. Verify destination integrity, recent-only predicate, count and SHA256. No historic rows are written to this replacement. Original is not touched.
2. **Offline delta:** after initial snapshot, perform a separate read-only live-source scan by source rowid high-water mark and add subsequent recent events to an offline clone. Remove rows that aged past the new UTC cutoff **in the offline clone only**, then verify again. This narrows the final cutover delta; it does not prove producer quiescence.
3. **Exact governed Root admission:** verify separately authorized permanent-retention policy, one-use exact SHA/arguments, rollback of active recent-only state, production freeze, health/drift, protective breaker, capacity, frozen 3-consumer identities, protected file/source custody, and no overlapping release. Do not treat a previous all-history archive approval as authority to purge.
4. **Controlled current-write handoff:** explicitly approved producer quiescence or an equivalent proved writer barrier; drain outstanding admitted outcomes, freeze source SQLite rowid high-water, complete the final delta, verify every record within retention window is present and no older records remain. If any producer can still write the original file, fail closed.
5. **Atomic live activation:** update the governed production data-path/mount configuration so all actual consumers reopen the compact recent-only database from the second drive. Verify current new events, retrievals, correlation/execution lookups, governance audit, independent health, rollback readiness and no old-source handles.
6. **Permanent source reclamation:** only after health acceptance remove redundant oversized local database, WAL and SHM through the reviewed Root release transaction with exact inode/proof preconditions; no old-event archive or unapproved backup. Verify actual free blocks/inodes.
7. **Ongoing retention:** run governed daily expiration against the second-drive database and periodically compact/rebuild it within free-space capacity. Bound wall time, concurrent write impact, rollback recovery, race and storage alerts.

## Recovery and restrictions

The permanent-retention release must not modify immutable audit authorization ledgers or other databases. It must not bypass a consumed or failed one-use Root action, production freeze, breaker, or independent Owner identity. No reboot/network disconnect. No service replacement without explicit exact-release approval for the required consumer handoff. A failed check leaves the source intact and reports whole-task incomplete.

Do not use online bulk DELETE and VACUUM on the root volume. This project is incomplete until a genuine cutover, the old local audit database's space reclamation and a recurring retention cycle have each been observed.

## Non-production code

- tools/audit_journal_30day_staging.py creates a recent-only file, an immutable initial manifest and local integrity evidence on the second disk.
- tools/audit_journal_30day_catchup.py prepares a separate offline catch-up copy; it cannot activate it.
- tests exercise 30-day UTC boundary, historical exclusion, live-source immutability, subsequent live events, staged expiration, wrong destination, schema and index integrity.

No destructive production Root tool is included in this initial preparation. Before implementation and release of the Root cutover, exact source identity, fresh approval and policy amendment must be independently accepted.
