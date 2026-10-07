# Automated Change State

**Status:** Generated; do not hand-edit
**Authority:** Derived evidence only; this file does not grant authority or replace governing architecture or runbooks.
**Canonical structured source:** `docs/control/AUTOMATED-CHANGE-STATE.json`

This record is updated by Jason's post-success documentation reconciliation process. It deliberately separates validated source from production-deployed state.

## Latest validated source

- Revision: `8c29070005d44d429cd27b552ad9c271121bc1d1`
- Status: `ci_passed`
- Workflow: `Validate Jason`
- Workflow run: `37633678984`
- Observed: `2026-10-07T14:27:11+00:00`

## Latest production alignment

- Revision: `7e8f97cf1a69ce1ce2b1339c27f858a6a06c3ba9`
- Status: `aligned_and_healthy`
- Runtime: `healthy`; restarts `0`
- MCP: `running`; restart policy `unless-stopped`
- Host release: `/opt/jason/releases/7e8f97cf1a69ce1ce2b1339c27f858a6a06c3ba9`
- Required host units active: `10`
- Failed systemd units: `0`
- Observed: `2026-10-07T13:53:48+00:00`

## Interpretation

A validated source revision is not proof of production deployment. Production is recorded only after the runtime, MCP, immutable host release, and required host services independently match the requested revision and are healthy.
