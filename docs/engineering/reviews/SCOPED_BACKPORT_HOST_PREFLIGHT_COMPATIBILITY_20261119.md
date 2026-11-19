# Scoped Backport root repair: host preflight compatibility (2026-11-19)

## Exact observed blocking conditions

After merged source-only PR #2647 (`5fe7259fec040e254e2154b18bd2b64a6b002dbd`), review of the actual Jason host confirmed:

- All four newly installed root-owned Scoped Backport units have permissions `0444`, matching the audited installation; the new root repair expected `0644` and would unconditionally reject them before Entra Owner authorization.
- PMv4-D previously approved root policy overlay `/srv/jason/archive/engineering-artifacts/pmv4-d-runbook-read-0467f3b29d2f6cbc0415ef9017627eb3c4a02915/policy-target.json` uses `max_stopped_rollback_containers = 21` to preserve approved PMv4 Ticket Core and Runbook allowances; the new root repair expected the obsolete `20`.
- The installed LKG `/opt/jason/current/tools/production_drift_guard.py` bytes match protected historical revision `d1b8c196dadd4b672ec8ba47075f27bb61c98d63` exactly.
- Root-owned production desired-state remains private. These observations do not claim that the new root repair has been executed or that the breaker is closed.

## Narrow source-only fix

Use the exact previously approved `0444` unit-file mode for root `read_root` verification; still require root ownership, one link, no symlink, and exact root-install-policy SHA-256. Require the approved PMv4-D rollback-retention setting **21** and preserve its value unchanged. Deny 20 and any other unexpected value. Do not write production, alter the freeze, remove/restart units, change authority or bypass root admission. Add positive and fail-closed regression checks to the existing protected security workflow test file.

## Release path

Merge only after protected required checks succeed, then obtain fresh root-only `--check` evidence using the latest clean protected-main worktree and CI-reviewed immutable exact source. An authenticated Owner on `al@Jason` must still explicitly authorize any exact privileged root correction. Independently revalidate the production breaker after native drift PASS, then run catalog V2 under its separate approvals, with image readback, native paired rollback and PMv4 isolation checks. Never replay the old scoped/cat Owner evidence.
