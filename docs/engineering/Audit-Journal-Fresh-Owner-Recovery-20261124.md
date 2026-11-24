# Audit journal — bounded fresh Owner claim after expired pre-cutover release

**Status:** Engineering source only. No production installation, journal migration, incident-hold change, owner assertion, or root privilege grant is performed by merging this source.

**Objective:** Recover a stopped, never-cut-over November 23, 2026 journal release without replaying its consumed Owner grant. Install the **already reviewed** three source-controlled `AmbientCapabilities=CAP_SETUID` lines after a **new, independently authenticated, exact-action** Owner decision, then let the original installed audit-journal release worker perform event-preserving cutover, archive, cold restore, native health, maintenance, rollback tests and source-file reclamation.

## Live evidence and exact pins

- Protected original runtime LKG: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- Expired deployed journal code candidate: `20b32548402d160f9c6a5ee33a0a17592eb9fa68`, scope `6d815c67f58ec9fa5eb3e2367259a53d53baf30daaa460d45b4720019291d7e8`.
- Old claim has a Root-owned exact authenticated Owner plan, `started_at` and `recovery_started_at`, but no complete rollback and **zero** recorded consumer replacement steps. Its eight-hour execution and recovery budgets are expired. Preserve the claim and failed private records **byte-for-byte**.
- Live canonical SQLite: `/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3`, device 66306, inode 10261846, writer UID/GID 1000, mode 0600. Legacy catalog generation 0, no archive or initial cutover claim.
- Installed three audit-journal root services differ from protected Main **only** by missing `AmbientCapabilities=CAP_SETUID`. Root live bounded systemd tests reproduced `EPERM` without the line and passed UID1000 helper, no effective/ambient child capabilities and read-only SQLite state with the line.
- The archive mount `/srv/jason/archive` is separate from root and held 151,993,057,280 free bytes on November 24 after deletion of one superseded offline staging copy, confirmed in `journal-retention-30day-20261123/old-stage-cleanup-result-20261124.json`. **Must recheck at execution** that available space exceeds `live_db_size*3 + 4563402752`. The current canonical database is still ~47.4GB and growing.
- No matching independent production write entitlement is implied by an online chat instruction. Live MCP Owner-admin currently rejects `AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED`; the installed root verifier's Entra device-code plus exact typed action is the separately reviewed fallback.

## Fresh governed authorization and installation

The new `--fresh-owner-expired-recovery` mode of `tools/audit_journal_install.py` is Root-only, isolated Python, clean exact checkout, protected-Main review and migration-CI pinned. Its new helper `tools/audit_journal_fresh_owner_recovery.py` binds:

1. Exact historic Root plan/journal/adoption/catalog/policy **raw-byte hashes**, the three prior service-context attempts' Root-only approvals/transactions/retry records, and each target's exact before/after unit SHA. Previous private authorization receipt hashes are **derived and reverified only inside Root** and bound to the new consent scope; they are never embedded as high-entropy literals in public source. It refuses a missing or modified previous claim, mismatched repair/source, already cut-over catalog, running worker, unknown local active-file owner/inode, insufficient archive reserve, unreviewed release or existing new one-use grant.
2. Current protected production control files (freeze, incident hold and Root transition), original container/peer image identities and exact configurations, live database handle provenance, known drift only, native breaker **still OPEN** for the expected failed release, and disabled maintenance timer. An unknown failure or changed peer denies **before** Owner consent. These checks recur after Owner consent.
3. The fresh **consent** action `FRESH-AUTHORIZED-RECOVERY-OF-EXPIRED-DAILY-AUDIT-JOURNAL`, new protected Main commit SHA, rollback SHA and exact set of three service-unit files, three Root plan/adoption/journal files and the new Root evidence ledger. This is **not** another approval of the old `ADOPT-EXACT-DAILY-AUDIT-JOURNAL` string.
4. Independently verified licensed Owner Entra tenant and OID through the fixed installed verifier. A new one-use Root evidence record binds the action, separate consent-scope hash, exact code candidate, original immutable superseded scope, rollback and fresh journal scope. The old authorization is neither edited nor extended.
5. Transactional exact before-image replacement of only three hardened service unit files (adding the already reviewed CAP_SETUID line) and three existing Root0400 journal control records. Every other systemd unit, release policy, Docker image, provider, database file and global freeze is untouched by this helper.
6. The replacement release journal gets a **fresh, scoped 8-hour claim**, not the old failed timestamps, and is only queueable after transactional proof is durably marked `queued`. It then invokes only the existing `jason-audit-journal-release.service` through systemd. A failure before queue triggers transactional rollback to previous unit and Root-plan bytes. After queue, no silent replay; require separate scoped recovery with immutable evidence.

**The installed release executor itself**, not this helper, owns all SQLite data movement, verified archive sealing, cold restore, lineage, daily maintenance, and safe reclamation. The new helper is expressly prohibited from direct database mutation, service restart outside the single exact release activation, changing provider credentials, or manually clearing production drift/breaker.

## Test and acceptance

Synthetic and no-production-source tests require: wrong principal denial; missing, old or changed source claim; expired clock proof; altered Root histories; wrong or excessive unit capabilities; UID mismatch; unknown producer/config; unknown drift; missing timer, foreign DB handles, insufficient reserve; one-use record and no replay. CI must independently pass the complete Audit Journal Migration Preparation and protected Main acceptance workflows after merge.

**Runtime acceptance is mandatory**: fresh Root exact consent and one-use receipt, installed `AmbientCapabilities=CAP_SETUID` in all three units, release result accepted under new scope, catalog segmented/validated, all history archived with event parity and independent cold restore proof, new writes preserved, daily timer enabled and operational, native fast/full health and independent drift PASS, protected breaker closed through the original Root controller, no producer/peer drift, and demonstrably reclaimed root filesystem capacity. None of these is established by source tests, CI, PR merge, or a queued service start.

## Original Owner-admin ChatGPT path

A successful one-time native Entra Owner recovery **does not by itself activate** `JASON_AOT_ADMIN_APPROVER_PROFILE=jason-owner-v1` on `jason-mcp-pilot`. Once the native breaker is genuinely CLOSED and release gates pass, independently promote the separately reviewed MCP Owner-profile candidate with its own exact source/image rollback, signed Owner consent and live authenticated requester readback; do not reuse audit authorization or silently enable it under the production freeze.

Linked tracking issue: #2680. All previous exact-scope approvals and failure records remain immutable.
