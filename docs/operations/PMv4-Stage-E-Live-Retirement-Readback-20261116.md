# PMv4 Stage E: PMv3 retirement readiness — live negative evidence

**Date:** November 16, 2026. **Status:** NOT READY. This is a source-only, read-only inventory and fail-closed retirement gate. It installs/disables no services, migrates no work, issues no approval, and modifies no production desired-state policy.

## Verified live state

- Protected GitHub main: `8c2064193d74cc41b52369681febbc0a74fa96f7`. Original production source: `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- Protected production Ticket Core `jason-runtime` and MCP `jason-mcp-pilot` remain running; original freeze and promotion incident hold remain unchanged. The original embedded Ticket Core child owns the current SQLite dispatch lock; recent scanned ticket counts are fresh and reported zero duplicate provider items.
- All three PMv3-era **user timers** remain active and enabled: `jason-support-repair-worker.timer`, `jason-release-manager.timer`, `jason-release-approval-only.timer`. The services may be inactive between firings/under freeze, which does not mean the timers are retired.
- Three old root **system units** remain active and enabled: `jason-release-control-transition.timer`, `jason-release-control-readback.timer`, `jason-release-host-reconcile.path`.
- Three continuing safety units remain active and enabled: `jason-production-drift-watchdog.timer`, `jason-boot-recovery.timer`, `jason-openclaw-authority-health.timer`. These protections must remain until independently proven replacement parity.
- The checked-in `config/production-desired-state.json` **still requires** all enumerated PMv3 user and root transition units. Deactivating them now would induce unwanted desired-state drift. Installed protected root active desired-state policy is not readable by the current unprivileged connector; no equality to the checked-in source is assumed.
- PMv4 A1 isolated shadow deployment/rollback remains unaccepted; Stage C external Ticket Core and dedicated ledger not installed; Stage D independent Runbook Management control surface and schema migration not deployed; PMv4 release controller and monitoring/rollback parity not accepted.

## Source-only guard

`tools/pmv4_e_retirement_readiness.py` reads the **source** desired-state list, `systemctl is-active/is-enabled` (never stop/disable/reset), exact protected Docker `inspect` running flags, and **aggregate** latest SQLite ticket scan (no client ticket data). It returns `status=not_ready_for_pmv3_retirement` and explicit blockers. Unknown legacy unit status, failed monitoring timer, nonrunning protected container, missing/stale ticket scan, source policy mismatch and missing release parity cannot become a readiness PASS. It does not create an Owner decision or authorize removal of any PMv3 unit.

The independent test suite simulates source/list readback and denies mutating shell/host commands, stale or duplicate ticket scans, missing protected policy and inaccessible user units. No CI execution can reach the production ticket DB or protected desired-state directory.

## Release exit requirements

1. Accept independent Ticket Core owner cutover with one ledger and one physically shared lock, two provider-backed scheduled scans and proven rollback while legacy PMv3 release process is intentionally unavailable.
2. Accept independent JSON Runbook Management hot lifecycle using one existing versioned DB, actor/fingerprint/audit receipts, Owner-bound activation and no provider authority escalation.
3. Accept component-scoped PMv4 release controller, independent Owner authorization, emergency recovery, monitoring/exporter and back-compat status/notification behavior.
4. Inventory and coordinate each PMv3-dependent timer/agent/API/alert. Publish **exact** replacement desired-state policy only after live parity verification. Preserve root drift/boot and security recovery until new readback proves nonregression.
5. Review actual protected root desired state and approved source/rollback SHA, obtain a fresh exact Owner production decision, execute **one serialized, audited** old/new unit delta with restoration on failure.
6. Verify post-retirement all old PMv3-only execution references are absent, but legacy immutable audit/rollback history retained, all required service health and ticket workflows continue, no surprise timers or duplicated work and no pay-per-token API fallback.

**Current Stage E disposition:** NO-GO. This source-only assessment is NOT an invitation to stop legacy release, approval, support-repair, drift, boot or reconciliation services.

## November 18, 2026 independent read-only recheck

At 05:33 EST, the host read-only retirement gate returned
`status=not_ready_for_pmv3_retirement` with seven explicit blockers:
legacy source policy and live execution units remain required; the
replacement release/engineering controller parity is not accepted;
Stage C independent Ticket Core and Stage D independent Runbook Management
are not accepted; a root-protected live desired-state readback and
an exact Owner retirement authorization are outstanding.

All six legacy user/root release and work units remain active/enabled;
drift, boot and authority monitoring timers remain active/enabled;
both protected containers are running. The observed latest ticket
scan had zero duplicates. Thirteen focused negative/positive tests PASS.
This is NOT production acceptance or permission to remove legacy timers.
The current native production breaker is separately OPEN due to a
catalog bootstrap-recovery service failure; restoration of that breaker
is a prior release boundary, not a reason to retire PMv3 prematurely.
