# Authority-health audit-store path correction (source only, November 17, 2026)

**State:** source-only correction. NOT DEPLOYED. Do not clear a release breaker or replace a live health snapshot from this document.

## Verified diagnosis

At November 17, 2026, 12:29 PM EST, the existing `jason-openclaw-authority-health.service` failed with exit code 2. The protected production drift watchdog opened the circuit breaker with problem kind `failed_system_unit`. The service override still executes `/usr/local/lib/jason/owner_emergency_fast_health.py`, whose local emergency degraded-health permission expired on November 12, 2026. It reports an actual failure, not a harmless warning.

The check expects `/var/lib/jason/openclaw/orchestration-events.sqlite3`, which does not exist. The real, regular 0600 `al:al` orchestration audit database is `/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3` on the live runtime's separate `governed-ticket-shared` bind mount. A read-only SQL schema lookup succeeded there without provider credentials, restart, mount change, or file creation. The existing full-proof snapshot refers to the legacy location; it must be regenerated under a separately authorized and properly bounded full integrity check after this path fix is installed.

## Exact source change

The one `DEFAULT_ORCH` declaration in `tools/openclaw_authority_operational_health.py` now points to the verified live governed-ticket-shared database. Both frequent-health and full-health modules import this single constant, preventing silent path disagreement. Two regression tests pin the same path for both modules. Their fail-closed checks are unchanged: missing/unreadable DB, unsafe file mode, bad/stale full proof or registry remain failures. No fallback to a legacy path or symlink was added.

**Production constraints:** Existing emergency override is expired and must NOT be renewed merely to make CI green. Installing these source bytes or updating the systemd override, rerunning a full integrity proof on the large audit database, clearing the protected breaker and deploying the independent-component release-control mechanism are **separate governed actions**, not authorized by this source-only change. The watchdog can only be reconciled through verified existing release controls. Preserve the Owner production freeze and protected runtime/MCP/PMv4.

Tests: `test_openclaw_authority_operational_health.py`, `test_openclaw_authority_fast_health.py`, and `test_release_authority_fast_health_handoff.py` — 67 passed locally.
