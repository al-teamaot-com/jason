# One reviewed release: close sealed historical readers and restore maintenance

**Stage: source and exact-scope design only. No Root or production deployment.**
Incident: November 25, 2026; issue #1948.

## Reproduced production failure

The 44 GiB original history has been sealed into a single root-owned archive on Drive 2. The canonical active journal has already been compacted to roughly 188 MiB, and Drive 1 has roughly 52 GiB free. Three live consumer processes (ticket-core, runtime and MCP) each held an open read-only descriptor to that sealed SQLite archive. Root maintenance reported JOURNAL_LEGACY_HANDLE_STILL_OPEN and exited 1 while its timer remained active. The three real consumer services remained online. Releasing the archive to maintenance is a prerequisite for successful scheduled rotation but is NOT authorization to erase historical audit data.

The underlying SegmentedOrchestrationEventStore cached each read-only sealed SQLite connection for the entire store lifetime (up to the archive cache limit). Closing the cursor only for pending archives left closed/sealed archive descriptors pinned. In addition, the separate forward recovery Root worker held a connection across a failed acceptance retry; that source problem was already fixed in protected Main PR #2729, but its installed production source must be independently inventoried rather than presumed updated.

## Implemented source change

The revised implementation/orchestrator/segmented_journal.py opens one verified read-only historical SQLite connection per query; it uses contextlib.closing to close both cursor and connection after success, early return or exception. It never caches sealed SQL connections. It preserves bounded filter memory-map caching, catalog generation/epoch controls, immutable sealed-only SQLite URI behavior, event ordering/duplicate detection, journal admission and provider safeguards. No change to current active database writer logic, provider calls or data-retention policy.

The three regression cases in tools/tests/test_audit_journal_archive_handle_lifecycle.py originally FAILED against the pre-fix Main: sealed read, exception during query, and repeated segment rotations. All three pass after the correction. Full audit-journal suite: 581 passed on Jason's development worktree; eight exact-release packet tests also passed.

## One exact-action governed release (not three independent approvals)

Action: RELEASE-EXACT-AUDIT-READER-HANDLE-CLOSURE. A preproduction manifest is compiled by tools/audit_journal_reader_release_packet.py, binding the final reviewed Main SHA and both exact audited Python source digests, current Root-worker digest, sealed-archive SHA, root policy/freeze hashes, all THREE original consumer image IDs and container identities. Only one freshly authenticated licensed Owner approval is required for the full, independently verified exact scope after Root admission. The Owner's earlier permission to interrupt three named services is not standing privilege nor approval to overwrite Root source; only the protected exact-action approval permits a production release.

Root operator must reuse the independently authenticated Owner signer, trusted source and one-use transaction, immutable Root-custodied images and before-files, production freeze/drift/breaker checks, Docker-29 comparison, and existing container mounts/restart policies. This is a high-risk audited runtime/root-worker deployment. This source packet is not an executable grant, nor a bypass of the current protected release admission. Do not install undeclared systemd units or relax sandbox/NoNewPrivileges.

Ordered implementation: capture complete exact before-image and signatures; verify Owner, Main CI and production controls; build/test independent Docker images; install reviewed Root recovery worker if the PR #2729 version is not installed; replace only the three named consumer images in a bounded sequential health-gated transaction with automatic exact original image/config rollback; verify real archived and active reads and no stale descriptors; let native maintenance execute its genuine cycle; inspect successful exit and catalog generation; check new current event and provider-independent audit evidence; run native full/fast integrity and independent drift; persist accepted proof. No stopped services unless exact replacement images, rollback and unexpired authority are all ready.

The release must automatically restore the precise original Root worker and each exact consumer original image and configuration on any failed gate, reverify active reads, preserve original sealed/current events, leave failed Owner evidence immutable and never replay prior consumed grants. If a provider readback, timer, journal parity or breaker gate fails, mark the whole release NOT ACCEPTED, not merely installed.

## Production acceptance

1. No SQLite FD to the sealed archive remains after normal, early-return or exception-path lookup in any of the three running consumer processes. Prove by inode/device Root census.
2. Historical event ID and correlation/execution lookup parity, active journal read, genuine later new event, no fabricated provider outcome.
3. Three original service roles healthy, expected exact data mounts/user identities, no Docker config drift.
4. Maintenance service actually succeeds and later scheduled rollover/rotation is observed. Timer enabled alone is insufficient.
5. Native full/fast integrity, independent drift, Root transaction accepted, global production freeze unchanged and no unrelated production mutations.

## Separate permanent deletion boundary

The entire historical archive remains retained for this release. This release does not apply a 30-day TTL, erase archival rows, modify Root grant ledgers, or recreate a legacy 44 GiB database. The permanently destructive 30-day retention policy is a separate exact Root action and requires a separately reviewed governance exception. Never combine those different effects into a generic deployment grant.

Engineering deliverables are reviewed source, regression tests, immutable typed release packet, protected CI and before/after Root proof. Production deployment requires a registered governed executor and fresh verified Root admission. Source merge alone is not deployment.
