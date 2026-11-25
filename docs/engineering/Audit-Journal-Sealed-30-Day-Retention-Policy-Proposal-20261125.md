# Proposed governance exception: 30-day permanent orchestration event retention

**Review only. Not activated. No production writer changes or historical deletion.**
This is separate from the audited sealed-archive reader lifecycle release (PR #2730).

## Owner objective and policy conflict

The Owner directed permanent removal of orchestration events with occurred_at strictly older than UTC now minus 30 days, not merely moving them from Drive 1 to Drive 2. Current Jason Canon calls Audit a permanent record and the orchestration store append-only. An exception must be approved through authoritative governance and a separately authenticated exact-release scope before any destructive Root operation.

The production system now has a compact live segmented SQLite journal and a large independently sealed historical archive on Drive 2. Purging the live database alone would **not** meet the Owner objective, because the sealed archive retains both older and possibly recent history. The primary reader-fix release does not delete historical data. The 30-day cutoff must apply consistently to:
1. the active canonical orchestration_events table;
2. every Root-custodied sealed/pending historical orchestration_events segment; and
3. redundant copies of those same expired event records, but only within an independently approved exact set of locations.

Separate Owner approval receipts, immutable Root release ledgers, provider records, customer records, recovery logs and security records remain outside the deletion scope. This distinction is a requested policy exception, not a statement that the current Canon already permits it.

## Exact proposed rule and release

Proposal config: config/jason-orchestration-30day-retention-proposal-v1.json.
One separately scoped destructive action: PURGE-EXACT-ORCHESTRATION-EVENTS-OLDER-THAN-30D.

At the precise Root writer-quiescence barrier instant, compute cutoff as UTC now - 30 days. Rows with occurred_at before cutoff are expired; rows at or after are retained. Prove event ID / execution / correlation parity for every retained row, not only a count. Malformed or timezone-naive events deny rather than being guessed. Require a catalog generation snapshot, every segment's Root-owned exact inode/device, content SHA-256, schema, PRAGMA integrity, WAL closure, row counts and min/max timestamp. The catalog does **not** itself contain date bounds, so each closed archive must be read to establish them. Caller-provided estimates are not authorization.

For any mixed-age sealed segment, build a standalone, indexed, read-only-verifiable retained-only replacement on Drive 2; validate integrity, every retained event payload and event_id parity, filters/proofs, and restore/readback. For a segment consisting entirely of expired events, mark it eligible for bounded deletion only after the same approved Root acceptance and no open handles. Leave entirely recent segments unchanged. Never unlink an entire archive if it contains any records inside the retention window.

Publish the new exact Root-owned catalog generation and validated reader identities only inside a serialized governed transaction. All three protected consumer roles must preserve expected image mounts/identities and successfully read active/retained historical data; require live event append and all native full/fast/drift checks. After full acceptance, remove the superseded expired database copies (not the retained recent-only data) and measure actual free blocks on the correct physical drive. Retain immutable approval/transaction/expiration *receipts* without retaining the expired event payloads. Prior to accepted purge, rollback may restore exact before-images; after accepted purge, rollback must **never resurrect expired history**. Its safe recovery restores functional readers and recently retained data only.

## Ongoing, not one-time

Authorize a separate guarded daily 30-day maintenance policy which checks each active/history segment at an explicit UTC cutoff, bounds memory/space/wall time, performs source-bounded re-seal + read parity, observes archive and active read health, and verifies genuinely reclaimed blocks. No direct bulk DELETE or VACUUM on a nearly-full system drive. No service restarts, global unfreeze, breaker overrides, unauthorized Root actions or provider mutations. The pre-existing tools/audit_journal_30day_staging.py and tools/audit_journal_30day_maintenance.py operate **offline only**; they are not currently production Root executors and must not be assumed installed.

## Safety and rollout requirements

- Independent governance amendment resolving permanent-record/append-only conflict before final approval.
- New exact source SHA, scope and rollback bound to independent licensed Owner signature, one-use immutable Root claim, freeze/breaker/drift admission, and protected Main CI.
- No deletion until the separate PR #2730 reader-lifecycle repair is accepted and the stale-history handles are gone. One action cannot silently authorize the other.
- Native Root release must fail closed for changed archive hash, wrong event counts, missing reader parity, open handles, old policy, unreviewed source, inadequate capacity, or unsettled provider outcomes.
- Never make the historical archive disappear as an implicit side-effect of a reader health fix.

Source-only prepare code tools/audit_journal_30day_sealed_plan.py accepts an inventory of verified or estimated sealed-segment event partitions and produces a non-activating SHA-bound release proposal. It neither opens nor writes the actual production database. Ten isolated tests prove exact mixed-history handling, older-only behavior, protected outside scope, strict UTC, wrong hash/count denial, and no self-authority.

**Completion condition:** Independent Owner-signed production policy release, genuine 30-day archival + live event parity, actual purged expired records (not just moved), continuing daily cleanup, root/secondary disk blocks reclaimed, stable service and maintenance health. None of those production deletion actions are reported as done by this engineering proposal.
