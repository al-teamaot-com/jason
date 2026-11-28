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

### Source-only input validation follow-up

Require unique catalog segment identities and an exact one-to-one statistics
inventory. A duplicate segment must never mask an unrelated statistics entry.
Require a genuine timezone offset, not merely a non-null tzinfo object.
Regression fixtures reproduce both prior planner defects; these checks do not
make caller-supplied statistics authoritative.

The currently installed no-restore archive maintenance is healthy. The root
disk has recovered from its earlier critical pressure. Permanent expiry remains
disabled pending the explicit governance exception, independently verified
segment data, and separate destructive release approval. Do not scan or rewrite
the entire historical database solely to prepare a policy proposal.

## November 27 — recorded Owner policy direction and protected-event boundary

The requesting Owner explicitly authorized permanent deletion of orchestration
events older than 30 days while preserving protected approval, security and
customer records. Record that policy direction in the existing disabled
proposal. Do not treat the chat statement as an independently authenticated
exact root release receipt or as activation of the destructive executor.

The actual canonical event schema carries organization, principal, capability,
execution and correlation IDs and immutable payload. The current emitter
includes approval_id, authority_context_id, idempotency_key and policy or
information-release evidence. Thus event age and table name alone cannot
distinguish ordinary expired lifecycle telemetry from protected evidence.
This is a material limitation of the older age-only staging/maintenance
tools: do not deploy them to live data under this approval.

Each segment must now have a positively established partition of recent,
protected-old and eligible-old rows, with a bound classification proof.
All unknown/ambiguous events and required protected or unresolved execution/
correlation evidence must be retained, even if older than 30 days. Preserve
full retained row identity and payload parity across active and sealed
segments, not only a count. A mixed archive with any protected-old rows may
never be deleted as a whole. The proof producer and native transaction must
derive eligibility independently from authenticated current sources; an
untrusted developer-supplied digest or count is not proof. The revised
planner is still source-only and cannot authorize anything.

Current root readback: segmented catalog generation 8, four sealed segments,
no-restore maintenance successful, native breaker closed and drift passing.
No archive deletion, catalog mutation, policy activation, or service stop
was performed. Native destructive executor, independent protected-record
classification evidence, protected release and recurring maintenance
acceptance remain mandatory.
