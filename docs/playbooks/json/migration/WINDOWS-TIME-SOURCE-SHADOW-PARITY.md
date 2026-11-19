# Windows Time Source — PMv4 JSON shadow migration evidence

## Section Goal

Migrate and independently test **the currently enabled read-only Windows Time Source shadow implementation** (`windows_time_source@0.1.0`) without activating any PMv4 JSON version, disabling legacy code, altering protected Ticket Core, making provider writes, or changing Stage E.

Authoritative legacy source: `docs/playbooks/Jason-Windows-Time-Source-Self-Heal.md` (Git blob `5a6dd8624c30a5f90f3bc776141d1d2226a77e3b`). Currently enabled legacy registry entry is pilot `0.1.0`, `autonomy.activation=shadow`, **zero allowed write capabilities**. The Markdown also specifies *future separately authorized* self-healing behavior; that **broader authored behavior has not been migrated or accepted**.

## Versioned JSON source

`candidates/windows_time_source.v1.json`, version `0.1.0-migration.1`, immutable canonical fingerprint `b75a183d829f7cb98c4b53a8813919e47ece77698d4fd8d6a5a8ee98ea983b44`.

- Exact `management.alert.search` -> `endpoint.device.read` -> `endpoint.alert.history.search` under existing Central Orchestrator ObservePort; no additional mutation capability.
- Exact `comp_script_ctx` diagnostic signature, source parsing, hostname/UID and site binding. Missing facts fail closed.
- Reuses pure legacy `is_time_source_alert`, `parse_sources`, `_provider_time`, `_alert_items`, 30-day recurrence window and 3-event threshold in `json_windows_time_facts.py`; not a parallel classifier or provider client.
- Classification: `CURRENT_TIME_SOURCE_MISMATCH`, `RECURRING_FAILURE`, `WAITING_DEVICE_ACCESS`; unrelated alerts are skipped, inconclusive identity/history is held for human review. No provider resolution.
- `json_windows_time_projection.py` writes only to a private preproduction `SQLiteWindowsTimeSourceShadowState`, preserving exact legacy row fields, fingerprint, and `autonomy.windows_time_source_shadow` audit event format. No Autotask/DRMM writes.
- `json_windows_time_preprod.py` uses the generalized fingerprinted draft-only `build_json_readonly_preprod_candidate` and existing `GovernedAutonomyReadPort`, with a separately verified same-client site binding. The original DRMM read-only pilot remains supported by the same builder.
- `json_windows_time_sweep.py` is **isolated test/candidate code, not a production scheduler**; it reuses the exact existing legacy `SQLiteWindowsTimeSourceShadowState.last_run_at/mark_run` 15-minute cadence and enforces a bounded alert batch. A unique per-alert/per-cycle run ID permits fresh reread on the next cycle while preserving interrupted-run idempotency. Nothing wires this harness into production dispatch.

## Controlled independent acceptance evidence

Test suites:

- `implementation/runtime_service/tests/test_json_windows_time_source_migration.py` — same-source provider fixtures against actual legacy `WindowsTimeSourceShadowMaintenance._classify`; exact recurrence count, classification, text, fingerprint, UID, diagnostics, history, offline, stale 31-day exclusion, cross-site and host mismatch, duplicate alert, malformed payload, persisted local version draft, resumed steps. Exact shadow-state row and audit event comparison, including changed=false idempotency.
- `implementation/runtime_service/tests/test_json_windows_time_preprod.py` — exact fingerprinted draft loading in isolated original JSON registry and existing Central Orchestrator ObservePort via mocked service request factory; positive/current/recurring/waiting cases, invalid client site, modified SHA, active-version rejection, disabled-path zero side effects.
- `implementation/runtime_service/tests/test_json_windows_time_sweep.py` — full sweep summary and audit equivalence against existing legacy `run_once` across current, recurring, offline, unrelated, empty and multi-alert cases; cadence/restart and source-change recheck; explicit duplicate alert rejection, unknown site and alert batch limit.
- Existing legacy `implementation/runtime_service/tests/test_windows_time_source_shadow.py` regression tests remain unmodified and must pass.

All synthetic scenarios run with **no live provider calls**, no JSON activation and zero endpoint, Autotask, or alert mutations. An isolated draft copy may be staged only inside temporary test SQLite storage; the production JSON registry is untouched.

## Remaining full-playbook migration gates

The authored Windows Time Self-Heal Markdown covers approved diagnostic-component execution, supervised domain-member resync, domain hierarchy restoration, restart_w32time, exact alert resolution, 2 maximum attempts, normal 15-minute recheck and 24-hour aging, domain-controller/secure-channel/DNS/VM/GPO exclusions and provider readback. These are **not implemented** by this read-only JSON and remain separate, unapproved operational capabilities. The existing actual read-only shadow pilot behavior is matched, but **full original legacy playbook parity is incomplete**.

Live preproduction provider binding and dispatch coexistence are also unverified. **Do not count this playbook as fully migrated**, merge as full migration acceptance, activate the JSON version in production or retire legacy `windows_time_source` on the basis of synthetic tests.

## Rollback and production protection

Current production legacy dispatcher and JSON registry remain authoritative and unchanged. The isolated source candidate can be reverted by a source commit, without affecting running Core. A later governed activation would require exact accepted source SHA, supported capabilities, isolated provider shadow acceptance, an immutable approval, atomic dispatch choice preventing duplicate active paths, readback and rollback to legacy.
