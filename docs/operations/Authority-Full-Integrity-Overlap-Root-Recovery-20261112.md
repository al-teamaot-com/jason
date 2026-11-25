# Authority full-integrity timeout — bounded source repair and governed recovery

**Date:** November 12, 2026. **Status:** preproduction source candidate; NOT installed. This document does not authorize production changes, a breaker override, a full-integrity waiver or release approval.

## Verified production fault

- The independent daily `jason-openclaw-authority-full-integrity.service` performs a full SQLite `PRAGMA integrity_check` on **four** databases plus an authority SQLite online backup, verified restored copy, row-count reconciliation, delegation review and trusted key registry validation.
- The orchestration-audit database is approximately **36.65 GB**, with an approximately **873 MB WAL**. The authority database is approximately **4.11 GB**. Both are live AOT data; source testing must not modify, checkpoint, copy or run an unbounded extra scan against them.
- Success durations grew through November 8, with the last successful unit taking about 56 minutes. On November 9–12, the authoritative 3,600-second verifier timeout produced exit 124 and explicit `operational_health_timeout` failure; no valid fresh full proof was generated. These results **do not demonstrate database corruption**. The missing proof cannot be replaced with an SQLite quick-check, metadata read, fast-health result, an older PASS or an exception declaration.
- The previously approved temporary emergency degraded-health exception expired at **15:00 UTC November 12**. The authority-health oneshot failed and independent root drift opened the protected production breaker. The freeze and auto-promotion hold have remained intact. **Do not renew/extend the temporary exception, modify the failed systemd unit, clear root drift, or close the breaker without its real recovery evidence.**
- Exact production baseline at diagnosis: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. Protected main had independently advanced for Constant Contact OAuth work. The PMv4 A0 issuer remains OFF and no separate Stage A0 installation occurred.

## Minimal bounded source correction

`tools/openclaw_authority_operational_health.py` launches **only one** additional, finite helper thread for the unchanged full `PRAGMA integrity_check` of the large orchestration database. The main verifier concurrently performs the unchanged full integrity scans on the authority, replay and security-audit databases, delegation/registry checks, and existing authority backup/restore proof. All five required verification stages must complete before `status=pass`. No provider network or credentials are required. No new daemon, database checkpoint, WAL mutation, snapshot substitution, signer, approval service, retry loop or source of standing authority is added.

`tools/openclaw_authority_health_snapshot.py` preserves protected main's **5,400-second** strict subprocess timeout and the **5,700-second** systemd boundary. Completed stage timing markers are secret-free and added to a **failed** timeout report for diagnosis; they are not proof of overall completion. A source crash, missing output, malformed JSON or launch failure now replaces a possibly stale PASS with atomic failure evidence, retaining the separate last-success file only for genuine source exit-zero full PASS. All failure reports remain nonzero.

This reduces repeated sequential wall time without weakening integrity coverage. It is a **preproduction mitigation**, not a verified production-scale performance guarantee; two concurrent SQLite readers may increase transient I/O. If it still times out, the strict 5,400-second timeout failure and OPEN breaker remain in force.

**Adopted existing scoped cleanup contract from #2390 (also appears in drafts #2395 and #2404):** The parent wrapper now creates exactly one private `jason-authority-integrity-run-*` subdirectory under the already-approved independent `/srv/jason/archive` mount. Only that child receives the directory as its `--backup-temp-root`. On success, failure or timeout the parent cleans that invocation's backup/restore copies; it never removes prior or unrelated archive data. This prevents another orphaned multi-GB backup when a timed-out child cannot execute its own `TemporaryDirectory` cleanup. **Protected main independently incorporated the 90-minute timeout and 95-minute systemd limit on November 12. The integration preserves these already-approved source values; it does not extend them again.** A negative test creates partial scratch under the run root, simulates forced timeout, and verifies cleanup while preserving unrelated evidence.

**Separate active overlap #2394:** its proposed dynamic orchestration database path for a later governed second-drive migration is not adopted in this source fix. Until that migration is independently reviewed, signed, deployed and verified across both writers and host-health checks, the existing ledger path is retained without a silent fallback or split audit. The four overlapping PRs remain independent; this PR neither merges nor activates their other features.

## Offline acceptance completed before production

- Thread ordering tests require the orchestration full check to be active **before** the authority backup and confirm that the backup still executes exactly once.
- A separate test creates **four actual SQLite databases**, exercises all four full integrity checks, backup and restored-copy integrity, row counts, delegation and registry, and verifies cleanup.
- Corrupt orchestration integrity, bad backup integrity and missing orchestration database must **never** produce PASS.
- Timeout, unavailable subprocess, missing or malformed JSON must atomically publish failure, never leak untrusted stderr or replace last-success proof.
- The existing authority health, recovery, signer and release-manager regression suites remain mandatory; GitHub CI runs the new focused tests against the exact commit.

## November 13: Root one-shot already consumed by a genuine success

Read-only host audit establishes that the original v1 Owner recovery
`owner-full-sqlite-integrity-proof-90m-recovery-v1` was executed at
2026-11-12 11:56 EST. The separately preserved
`operational-full-health-last-pass.json` was written approximately
12:47 EST with **four SQLite integrity=ok**, backup/restore
integrity=ok and matching counts. Its root-owned one-shot ledger is
therefore *correctly consumed* and must not be reset or replayed.

The **next** normal daily full checker still used the original 60-minute
installed LKG, timed out at 2026-11-13 04:01 EST, and left the fast
authority-health service failed. The root production breaker is OPEN.
Healthy runtime/ticket scanning is not a release-health PASS.
This PR addresses the recurring sequential-scan performance issue in
**source only**; it does not authorize another 90-minute scan, a new
Owner one-shot ledger, a protected root repair, or Stage A0 installation.

The separate GitHub v1 root recovery workflow now verifies original
immutable signed policy and source against exact protected commit
`323ac1827cfe375bd58aa4f487400b911f8d23aa`, **not the moving
HEAD checkout**. The installed root-owned checker and snapshot still
match the original v1 byte digests. This corrects a false CI conflict
between an intentionally immutable consumed v1 root action and a later
independently reviewed v2 performance improvement. The current v1
policy, source hashes, ledger and production systemd configuration are
not changed; no future owner/recovery approval is inferred.

## Required source and production authorization sequence

1. Review the exact isolated source PR, its required CI and commit/scope SHA. **Source-only promotion requires a separately authenticated exact Owner decision**, without deploy or unfreeze.
2. With the breaker OPEN, the ordinary native release manager correctly cannot create/promote a managed candidate. Prepare a **separate root-governed, exact-source authority-health repair** using an existing controlled emergency/recovery mechanism. Before asking for mutation approval, identify exact protected source SHA, source files, root helper mode/ownership, immutable rollback bytes, safety/health bounds and whether any service start/restart could disrupt users. Do not use `sudo`, Docker, systemd or an alternate shell path to bypass the breaker.
3. Only after specific Owner approval may the root repair be installed. The first actual repaired full-integrity job must run under the existing bounded health service, not an unbounded interactive command, and must emit **fresh genuine PASS** with all four database integrity fields, backup and restore integrity, matching restored counts, key registry and provider-free evidence. Keep the failed health state if proof is incomplete.
4. With the actual health oneshot healthy and drift truly clean, collect **three distinct** root-owned drift observations at least 15 seconds apart, at least 90 seconds after breaker opening, with final evidence no older than 180 seconds. Revalidate through the existing native root mechanism with its normal attempt/transaction controls; never edit the breaker directly.
5. Recalculate the production LKG, source scope, immutable MCP/runtime candidates, freeze hash, auto-promotion hold, and exact rollback. Only then rebuild the managed PMv4 A0 issuer activation release record, complete preproduction acceptance, and present the **separate full release Owner decision** covering service replacements and any bounded reversible freeze exception. Actual A0 installation remains excluded.

## Production rollback and preservation

The expected unmodified baseline at diagnosis is `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`; MCP image `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`, runtime image `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`. The production freeze SHA-256 is `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`, and hold SHA-256 `11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0`. These are snapshot values, not perpetual permissions. Prior source and immutable root helper rollback must be reverified against actual live state at the later approval boundary.

**Current stop boundary:** No production root authority is available to apply a protected checker change under the OPEN breaker in this chat, and no exact Owner production-repair approval has been granted. No production commands in this source worktree install, unfreeze, restart, sign, deploy or activate anything.


## Concurrent PR coordination

Integration coordination: #2390 #2394 #2395 #2404 #2459

The precise source hunks and differences were checked against all five
active references. The independent archive-scratch cleanup from #2390
was adopted in the original branch before protected main independently promoted the 90-minute timeout and 95-minute systemd limit; larger
drafts #2395/#2404 carry that same cleanup plus unrelated Teams and
release controls. The future second-drive audit selection in #2394
remains its own explicitly governed dual-writer migration. #2459's
PMv4 Owner issuer remains a distinct source promotion and activation.
This technical coordination is not a production release, standing
authorization, or permission to merge unrelated open PRs.
