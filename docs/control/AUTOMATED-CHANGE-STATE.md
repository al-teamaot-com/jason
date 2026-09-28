# Automated Change State

**Status:** Generated; do not hand-edit
**Authority:** Derived evidence only; this file does not grant authority or replace governing architecture or runbooks.
**Canonical structured source:** `docs/control/AUTOMATED-CHANGE-STATE.json`

This record is updated by Jason's post-success documentation reconciliation process. It deliberately separates validated source from production-deployed state.

## Latest validated source

- Revision: `175bec8eaa73ba9adbb26612ca3a3596c7883464`
- Status: `ci_passed`
- Workflow: `Validate Jason`
- Workflow run: `36407277960`
- Observed: `2026-09-28T10:16:29+00:00`

## Latest production alignment

- Revision: `5e57a34ac2018bad032e3b4467c58f814023699f`
- Status: `aligned_and_healthy`
- Runtime: `healthy`; restarts `0`
- MCP: `running`; restart policy `unless-stopped`
- Host release: `/opt/jason/releases/5e57a34ac2018bad032e3b4467c58f814023699f`
- Required host units active: `10`
- Failed systemd units: `0`
- Observed: `2026-09-27T13:13:34+00:00`

## Interpretation

A validated source revision is not proof of production deployment. Production is recorded only after the runtime, MCP, immutable host release, and required host services independently match the requested revision and are healthy.
