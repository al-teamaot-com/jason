# Automated Change State

**Status:** Generated; do not hand-edit
**Authority:** Derived evidence only; this file does not grant authority or replace governing architecture or runbooks.
**Canonical structured source:** `docs/control/AUTOMATED-CHANGE-STATE.json`

This record is updated by Jason's post-success documentation reconciliation process. It deliberately separates validated source from production-deployed state.

## Latest validated source

- Revision: `851f666323d7943c2706b1d913a4b2e556cc4b93`
- Status: `ci_passed`
- Workflow: `Validate Jason`
- Workflow run: `41217091615`
- Observed: `2026-10-31T16:00:10+00:00`

## Latest production alignment

- Revision: `3d62c211bbc861636658e0d7b6cbb5363d12a47e`
- Status: `aligned_and_healthy`
- Runtime: `healthy`; restarts `0`
- MCP: `running`; restart policy `unless-stopped`
- Host release: `/opt/jason/releases/3d62c211bbc861636658e0d7b6cbb5363d12a47e`
- Required host units active: `10`
- Failed systemd units: `0`
- Observed: `2026-10-29T17:55:52+00:00`

## Interpretation

A validated source revision is not proof of production deployment. Production is recorded only after the runtime, MCP, immutable host release, and required host services independently match the requested revision and are healthy.
