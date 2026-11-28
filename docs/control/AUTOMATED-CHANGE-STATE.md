# Automated Change State

**Status:** Generated; do not hand-edit
**Authority:** Derived evidence only; this file does not grant authority or replace governing architecture or runbooks.
**Canonical structured source:** `docs/control/AUTOMATED-CHANGE-STATE.json`

This record is updated by Jason's post-success documentation reconciliation process. It deliberately separates validated source from production-deployed state.

## Latest validated source

- Revision: `6a675b236a80cc2c284c3cbbb06477c779b783a0`
- Status: `ci_passed`
- Workflow: `Validate Jason`
- Workflow run: `45904975611`
- Observed: `2026-11-27T05:00:09+00:00`

## Latest production alignment

- Revision: `690250b4d21f32cce79cab9f5b4c18cf93e7e94a`
- Status: `aligned_and_healthy`
- Runtime: `healthy`; restarts `0`
- MCP: `running`; restart policy `unless-stopped`
- Host release: `/opt/jason/releases/690250b4d21f32cce79cab9f5b4c18cf93e7e94a`
- Required host units active: `10`
- Failed systemd units: `0`
- Observed: `2026-11-11T17:52:14+00:00`

## Interpretation

A validated source revision is not proof of production deployment. Production is recorded only after the runtime, MCP, immutable host release, and required host services independently match the requested revision and are healthy.
