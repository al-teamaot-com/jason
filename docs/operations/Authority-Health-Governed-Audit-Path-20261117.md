# Source-only authority-health audit path correction — November 17, 2026

**Status:** NOT deployed, no protected breaker recovery, no new production proof.

## Verified live issue

At 12:29 PM Eastern, the installed `jason-openclaw-authority-health.service` was failing, and the protected drift watchdog opened the release circuit breaker. Its read-only probe expects a now-missing legacy location: `/var/lib/jason/openclaw/orchestration-events.sqlite3`. The live 0600 `al:al` orchestration journal exists instead at `/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3`, with a successful read-only SQLite schema probe. The temporary emergency-health drop-in expired on November 12. Do **not** extend it, clear the breaker, create a symlink, rewrite immutable root recovery manifests, or restart services on this evidence alone.

## Exact source-only correction

Only `tools/openclaw_authority_fast_health.py` changes its *frequent read-only* `DATABASES["orchestration_audit"]` to the verified live journal. The root-recovery-pinned `tools/openclaw_authority_operational_health.py` remains **byte-for-byte unchanged**, preserving the installed immutable full-integrity recovery source hash and all existing approvals. The unmodified full checker already has an explicit `--orchestration-audit` CLI parameter; a future separately governed full proof must supply that exact live path, validate all actual databases and backup/restore parity, and write newly verified evidence. The old full-proof snapshot is not accepted as new proof after the fast path is fixed.

Regression tests verify both the fast path and the existing full-checker CLI override; the previous hash-pinned root policy remains untouched. This change is not authority to stage a new systemd override, alter the current root recovery policy, remediate a 41 GB SQLite database, revalidate the production breaker, activate PMv4, or deploy the independent financial service.

## Required downstream controls

1. Separately authorize and install the exact fast-health path correction through the governed release process.
2. Independently authorize a bounded full integrity proof that passes `--orchestration-audit /var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3` to the existing pinned checker; audit actual integrity/backup/restore results, not a synthetic PASS.
3. Only after true health PASS, use the existing protected drift-watchdog and circuit-breaker revalidation, preserving the owner freeze. Then separately install the approved independent-component release controls through a trusted signed root installer (currently absent).

This PR cannot resolve the live failed unit by itself; the old emergency drop-in must be retired only under its own exact-scope protected production authorization.
