# P0 audit journal: exact recovery after two consumed repairs (November 23, 2026)

Status: source-only candidate. No production cutover or storage reclamation has been verified.

## Verified incident

The canonical orchestration journal is still a legacy SQLite database larger than 43 GiB plus WAL on a 98%-used system filesystem. /srv/jason/archive is mounted on a different disk with approximately 168 GiB free. The archive segment directory is empty, catalog generation is zero, and the maintenance timer is inactive.

The original approved migration f0f71c46e054f46f6cba1f945a404f148f441501 failed its journal writer handoff under runuser/PAM and began an approved rollback. A previous exact context attempt 4ba98e05e4512d7accb77595b8e8c05086d8b0a6 was fully rolled back. Owner-authenticated subsequent candidate b9274191a79bda16bb687a866b4458bda6bf6361, scope 7dc2fc5b4a67ae9e8a896934525ce65be4815ad9184612a161d3e50b54fe9f94, also rolled back. Root read-only evidence from November 23 shows the b927 transaction has 21 actions, outcome rolled_back, and a present retry.json: its one bounded retry was consumed. Repeating either previous command is denied by design.

The b927 failure was traced to an unconditional systemctl reset-failed on a collected, inactive, unloaded release unit. Source fix #2706 checks real state and only resets an actual failed, stopped worker; it also improves bounded diagnostics. The present candidate includes that correction.

## Scope of this source repair

- Require a fresh exact protected candidate and independently authenticated Owner action/scope approval. The Owner's broader objective consent does not turn an expired/consumed one-use receipt into an executor.
- Require original f0f adoption and both prior context ledgers to remain Root-owned, hash-consistent, and immutable. Verify 4ba rolled-back before-images and its unconsumed retry state; verify b927 fully rolled-back before-images and exact consumed retry marker.
- Check b927's frozen source digests, original Owner identity, rollback identity, transaction entries, exact predecessor link, recorded retry scope/time, and preserved production source/peer identity.
- Bind preceding immutable approval, transaction and retry SHA-256 evidence into newly reviewed execution scope and recheck immediately before any replacement.
- Enforce existing freeze, native drift, breaker, source/CI, release-lock, backup, rollback, archive-disk, identity, no-open-handle and protected-consumer gates. Do not change provider actions or ticket state.
- Do not mutate any previous authorization.json, transaction.json, retry.json or audit data. The new candidate gets its own single-use ledger. No marker deletion, bypass, direct SQLite trim, generic root authority or production config workaround.

## Required acceptance

1. Protected Main review/CI and isolated Root fixtures pass, including wrong scope/Owner/predecessor, modified source, missing/altered retry, queued transaction, changed original data, and recovery failures.
2. Fresh Root preflight proves three audit producers/readers and current data/peer/health identity; a newly generated exact scope and rollback are independently verified and approved once by the licensed Owner.
3. Governed Root installer stages immutable source and desired state, runs genuine native health/readmission, queues fixed release and verifies restored/audit-aware consumers.
4. Old data and ongoing outcomes are preserved; archives are integrity checked and cold restored on archive disk. Verify full event parity, historical read routing, rollback reconstruction, real daily rollover and subsequent writes.
5. Only after archive parity, no open old handles, Root custody and restore proof may redundant local source be reclaimed. Verify root disk free blocks and inode headroom and check production health/drift, breaker and ticket processing.

Any failed step is blocked, not completed. Original one-use ledgers and failure evidence stay immutable. Do not run repair-before-cutover for b927 again, or resume-context-repair with its consumed retry.
