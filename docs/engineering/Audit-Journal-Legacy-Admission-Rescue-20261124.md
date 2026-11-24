# P0 legacy admission restoration after interrupted journal migration rollback

**Engineering source only.** No live operation or Owner approval occurs by writing or merging this code.

The original 2026-11-24 licensed-Owner `FRESH-AUTHORIZED-RECOVERY-OF-EXPIRED-DAILY-AUDIT-JOURNAL` queued under scope `ac1fd3d27c31875cdb263c614aaea11fae72f54d0bc2df9db79dc0f28d1ecac3`, but its Docker 29 readback rejected the `OomKillDisable=None -> False` normalization and its own rollback failed. Separately governed ticket-core restore PR #2717, then Owner action `RESTORE-EXACT-PMV4-TICKET-CORE-AFTER-AUDIT-ROLLBACK`, succeeded. By 08:01 EST `jason-pmv4-ticket-core` and `jason-runtime` were both running and healthy, and `jason-mcp-pilot` running.

**However, UID1000 read-only SQLite inspection of the still-legacy 47.4GB audit DB revealed two active, exact historic maintenance triggers:** `audit_journal_maintenance_admission` blocks `orchestration.request.received` and `audit_journal_maintenance_invoking` blocks `orchestration.capability.invoking`. This means a healthy Docker container alone does **not** restore normal ticket processing. The first failed journal release had set the legacy maintenance barrier and never completed `self.barrier(False)`.

The original triggered schema was read-only verified:
- Admission SQL fingerprint: `c29b47ffd6a24eeccfc967d6192d0ecf217af570b1ce566e7a2f60b4b53169ac`.
- Invoking SQL fingerprint: `e5ff3d44da5e6ac6098ee9adbb3a64cc477850ffbd7744106c2b4783077139fc`.
- Both triggers are on the exact `orchestration_events` table; no other `audit_journal_maintenance_%` trigger exists.
- The legacy database inode, owner, size and separate archive filesystem remain consistent; catalog generation0, pending/archive empty, journal release unit failed and timer disabled.

## Governed emergency repair

Reviewed exact Owner action: `RESTORE-EXACT-LEGACY-AUDIT-ADMISSION-AFTER-FAILED-MIGRATION`.

The new `tools/audit_journal_install.py --restore-exact-legacy-admission` runs from a clean SHA-pinned protected-Main source closure, uses the existing licensed Microsoft Entra Owner verifier, Root transaction locks and independent protected CI attestor. The `audit_journal_legacy_admission_rescue.py` code authenticates and binds:
1. Exact failed original Owner plan and scope, legacy catalog, pinned immutable writer and before-producer evidence, and incomplete journal's two permitted steps only.
2. Exact Root-only previous ticket-core rescue authorization and successful result, original container ID and healthy current configuration, other consumers running and original.
3. Frozen global policy/breaker, no new segmented journal, failed release service, disabled timer, and exact existing two trigger SQL digests.
4. New source SHA and rollback SHA, exact database identity and scope, only two explicitly named DDL operations, one-use protected Root evidence and no standing authority.

**Only after fresh independent Entra Owner consent and repeat full Root readback** does this action store a one-use Root approval. It then invokes isolated Python as **UID1000/GID1000** (not Root SQLite) to perform a single **atomic `BEGIN IMMEDIATE` transaction**, re-verify both source trigger SQL digests, execute:
`DROP TRIGGER audit_journal_maintenance_admission`;
`DROP TRIGGER audit_journal_maintenance_invoking`;
then `COMMIT`. It reads back absence independently and persists the protected success receipt. Ambiguous execution is not retried. No event row changes, archive writes, source credential changes, ticket/provider writes, systemd restarts, native breaker resets or cleanup of the existing failed release are authorized.

This is narrowly scoped **restoration of normal legacy admission**, not a claim that the migration is complete. The previous failed journal and all rollback backups remain for a separately reviewed, exact reconstruction and successful rollforward.

## Acceptance and regression coverage

- 14 dedicated tests cover exact prior Owner scope, triggered SQL, previously completed ticket-core rescue, fake mutation denials, correct and malformed SQLite trigger schema, atomic two-trigger transaction, zero event-row modifications, and wrong Owner rejection before SQL writes.
- Source/CI and Root custody preflights enforce fail-closed behavior; real privileged execution requires new exact Owner consent. Tests never mutate the production SQLite.
- After live execution, confirm read-only SQLite `sqlite_master` shows both triggers absent; run a safe platform governed read and an approved ticket health scan, without injecting a ticket or changing its status.
- Full journal objective remains open until interrupted release reconciliation, immutable rollback proof, new exact release, full archive restore and parity, timer and native drift acceptance, and >40GB root disk reclamation are verified.
