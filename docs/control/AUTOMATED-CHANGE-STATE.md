# Automated Change State

**Status:** Generated; do not hand-edit
**Authority:** Derived evidence only; this file does not grant authority or replace governing architecture or runbooks.
**Canonical structured source:** `docs/control/AUTOMATED-CHANGE-STATE.json`

This record is updated by Jason's post-success documentation reconciliation process. It deliberately separates validated source from production-deployed state.

## Latest validated source

- Revision: `b8cf77f75b95ec9d62c399ac9f1f8a85f7221f16`
- Status: `ci_passed`
- Workflow: `Validate Jason`
- Workflow run: `37646099902`
- Observed: `2026-10-07T15:49:07+00:00`

## Latest production alignment

- Revision: `2e2afe489581307f3ce930e51b3c2c05ab2d3e0c`
- Status: `aligned_and_healthy`
- Runtime: `healthy`; restarts `0`
- MCP: `running`; restart policy `unless-stopped`
- Host release: `/opt/jason/releases/2e2afe489581307f3ce930e51b3c2c05ab2d3e0c`
- Required host units active: `10`
- Failed systemd units: `0`
- Observed: `2026-10-10T15:11:49+00:00`

## Interpretation

A validated source revision is not proof of production deployment. Production is recorded only after the runtime, MCP, immutable host release, and required host services independently match the requested revision and are healthy.
