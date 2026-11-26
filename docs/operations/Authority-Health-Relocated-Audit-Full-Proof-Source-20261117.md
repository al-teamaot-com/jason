# Governed full-authority proof for relocated audit journal — source-only

**Date:** 2026-11-17. **State:** Engineering candidate only. No production installation, no health-unit change, no integrity scan, no breaker revalidation.

## Observed failure and exact scope

The production authority-health one-shot is failed and the protected production breaker is **open**. Its expired root emergency override imported the old frequent health implementation which probes `/var/lib/jason/openclaw/orchestration-events.sqlite3`. That pathname is absent; the live 0600 `al:al` database exists at `/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3`, and read-only SQLite schema lookup succeeded. Prior full-health PASS refers to the **old** pathname and must not be accepted as fresh evidence. User approved investigating and preparing the scoped repair, including a bounded real 41 GB integrity proof, with no systemd/runtime/provider/freeze changes except by independently authenticated, signed, trusted root controls.

The fast read-only probe source correction was merged as PR #2530, reviewed source SHA `a8628601b02c878005b2ca6bfd906fadb41d5f02`. It deliberately did not alter the existing root-recovery-pinned full-checker `tools/openclaw_authority_operational_health.py`. Its SHA-256 remains `4d9aec6c2d8a3695cd88b3abfadcf4e66f35c45376550c0d5f4a8fd762896781`.

## Why the existing root helper cannot be used unchanged

The installed root-only `/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py` is signed and one-use, but its admission requires `operational-full-health.json` to show exactly a previous **timeout** (`failures=["operational_health_timeout"]`, exit 124). The current artifact is `status=pass` against the obsolete path, making that action `NOT_THE_REVIEWED_TIMEOUT`. The signed helper's existing snapshot wrapper does not forward `--orchestration-audit` to the existing checker. Forcing the old helper, deleting the full-pass record, rewriting its installed manifest, changing its preconditions, or creating a symlink to the new live database would bypass exact-action governance. **Do not do any of those.**

## Source-only companion

`tools/openclaw_authority_live_audit_full_snapshot.py` is an isolated, fail-closed utility that will run **only** after a fresh, separately signed root installer places it at the trusted root-owned path `/usr/local/lib/jason/authority-health-live-audit/openclaw_authority_live_audit_full_snapshot.py` and stages the existing pinned full checker alongside it. The utility:

- Executes the unchanged full checker with exact `--orchestration-audit /var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3`, plus a parent-owned archive scratch directory, under 5,400 seconds.
- Checks the live audit file is regular, non-symlink, UID 1000, mode 0600; verifies all four actual integrity results, real authority backup/restore parity, registry keys, no expired delegation, no provider contact or credentials, and the exact audit path.
- Uses the existing atomic full-health snapshot writer; replaces stale PASS with a genuine FAIL on timeout/exception/invalid evidence and always cleans the scoped temporary archive.
- Cannot be launched from a mutable worktree through its CLI. It cannot authorize itself, install root code, restart units, consume owner proof, remove expired emergency overrides, edit breakers, change the freeze, or deploy any service.

**Production install and root recovery are NOT delivered by this source PR.** A new governed one-use **health-path relocation** root transaction must be independently engineered and admitted with exact protected-main CI, fresh signed Owner proof, root-pinned source/manifest, root ownership, legacy+new transaction locks, state-before/state-after receipts, the original MCP/runtime/PMv4 baseline, and narrow rollback. It may root-install this scoped wrapper and adjust only the health check units as separately authorized; after a real proof PASS it may remove the expired override and invoke **native** drift/breaker revalidation. It must fail closed and preserve the freeze on any failure.

Tests `test_openclaw_authority_live_audit_full_snapshot.py` plus existing snapshot, full checker, fast-health and signed root-repair regressions: 74 passed, 1 skipped. No production database was scanned during these tests.
