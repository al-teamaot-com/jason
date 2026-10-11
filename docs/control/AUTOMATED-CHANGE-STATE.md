# Automated Change State

**Status:** Generated; do not hand-edit
**Authority:** Derived evidence only; this file does not grant authority or replace governing architecture or runbooks.
**Canonical structured source:** `docs/control/AUTOMATED-CHANGE-STATE.json`

This record is updated by Jason's post-success documentation reconciliation process. It deliberately separates validated source from production-deployed state.

## Latest validated source

- Revision: `626d42d72652c0e988feed09f0b4680dff08acc1`
- Status: `ci_passed`
- Workflow: `Validate Jason`
- Workflow run: `37790231076`
- Observed: `2026-10-08T16:00:12+00:00`

## Latest production alignment

- Revision: `46ced6edf06ca15ceab7ad0e70ece2b79a32151a`
- Status: `aligned_and_healthy`
- Runtime: `healthy`; restarts `0`
- MCP: `running`; restart policy `unless-stopped`
- Host release: `/opt/jason/releases/46ced6edf06ca15ceab7ad0e70ece2b79a32151a`
- Required host units active: `10`
- Failed systemd units: `0`
- Observed: `2026-10-07T23:27:55+00:00`

## Interpretation

A validated source revision is not proof of production deployment. Production is recorded only after the runtime, MCP, immutable host release, and required host services independently match the requested revision and are healthy.
