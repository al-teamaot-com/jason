# Automated Change State

**Status:** Generated; do not hand-edit
**Authority:** Derived evidence only; this file does not grant authority or replace governing architecture or runbooks.
**Canonical structured source:** `docs/control/AUTOMATED-CHANGE-STATE.json`

This record is updated by Jason's post-success documentation reconciliation process. It deliberately separates validated source from production-deployed state.

## Latest validated source

- Revision: `c4a0c71ed618ac974a3ad04aef3a5a688c421d2e`
- Status: `ci_passed`
- Workflow: `Validate Jason`
- Workflow run: `37007509371`
- Observed: `2026-10-02T12:38:01+00:00`

## Latest production alignment

- Revision: `c4a0c71ed618ac974a3ad04aef3a5a688c421d2e`
- Status: `aligned_and_healthy`
- Runtime: `healthy`; restarts `0`
- MCP: `running`; restart policy `unless-stopped`
- Host release: `/opt/jason/releases/c4a0c71ed618ac974a3ad04aef3a5a688c421d2e`
- Required host units active: `10`
- Failed systemd units: `0`
- Observed: `2026-10-02T12:40:33+00:00`

## Interpretation

A validated source revision is not proof of production deployment. Production is recorded only after the runtime, MCP, immutable host release, and required host services independently match the requested revision and are healthy.
