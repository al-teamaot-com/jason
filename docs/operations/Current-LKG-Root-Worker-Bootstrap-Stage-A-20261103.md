# Current LKG root-worker bootstrap — Stage A — 2026-11-03

## Purpose

Break the protected-root bootstrap loop without introducing a new production unit delta.
The installed production root reconciler is still the exact LKG implementation and cannot
validate the newer open-breaker forward-recovery contract before candidate staging.

## Stage A boundary

This release keeps all current protected-main recovery code, but makes
`config/production-desired-state.json` byte-for-byte identical to production LKG
`1b28ddc9863aee563755cb57599cf211ee82ac19`.

The only declarations temporarily withheld are:

- `jason-openbao-identity-lifecycle.timer`
- `jason-openbao-identity-lifecycle.service`

Their implementation remains in source; Stage A does not declare, copy, activate, or require
those units. The existing LKG root worker therefore observes no desired-state unit delta and
may use the canonical stage-only installer to atomically install the reviewed newer protected
root migration helper and host reconciler.

## Safety and acceptance

- Exact-SHA Owner Teams approval and CCC remain mandatory.
- Production freeze remains in force except for the one exact authorized transaction.
- No provider mutation is authorized by this bootstrap.
- Stage A must verify the installed root worker/helper, runtime/MCP/host alignment, health,
  rollback readiness, drift, and production freeze restoration before becoming LKG.
- If Stage A cannot complete host verification, do not proceed to Stage B.
- Stage B is a separate exact reviewed release that restores the two intended identity-lifecycle
  desired-state declarations only after Stage A is production verified.

This is the two-release bootstrap pattern already required by Project Jason root-migration
governance; it does not weaken or bypass root policy validation.

## Legacy-root admission rule

The open-breaker compatibility preflight may admit Stage A even when the currently installed
root reconciler lacks the newer forward-recovery markers **only** when Git proves that the
exact candidate and exact rollback SHA contain byte-for-byte identical
`config/production-desired-state.json` blobs. This is intentionally stricter than comparing
only unit lists. Any desired-state byte difference fails closed and requires a compatible
installed root worker before production mutation. All ordinary exact-main, LKG, drift,
preproduction, manual scope, signed Owner/CCC, freeze, rollback, and post-production gates
remain mandatory.
