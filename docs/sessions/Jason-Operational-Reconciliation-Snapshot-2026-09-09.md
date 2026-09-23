# Project Jason — Operational Reconciliation Snapshot

**Observed:** 2026-09-09T17:52:33Z  
**Host:** Jason  
**Classification:** Evidence / point-in-time host observation  
**Mode:** Read-only

## Purpose

Record the bounded host facts used to reconcile Project Jason documentation on 2026-09-09.

This snapshot does not replace the System Registry. It provides observed evidence needed to bring the registry and current-work documentation back into alignment.

## Protected main worktree

Path:

`/home/al/projects/jason`

Observed branch:

`feature/jason-runtime-service`

Observed local HEAD:

`8eda576b6e79227e888462df0e1ef857f99f546c`

The worktree contained extensive tracked and untracked active development changes. It must not be reset, cleaned, stashed, switched, or repurposed for the documentation-reconciliation workstream.

The local filesystem also contained a retired `07-Operations` documentation root, causing documentation-control validation to fail in that worktree. That failure is not authority to delete or clean unrelated active work.

## Accepted live dashboard worktree

Path:

`/home/al/projects/jason-dashboard-usage-telemetry-20260909`

Observed HEAD:

`ecc265ee59645154f0bc86b5aa0dc5a2e375f022`

Observed state:

- detached;
- clean.

This worktree is the accepted live monitoring source and must not be updated merely to perform documentation reconciliation.

## Observed services

The host snapshot observed:

- `jason-runtime` running and healthy;
- `jason-teams-gateway` running;
- `openclaw-openclaw-gateway-1` running and healthy;
- `jason-mcp-pilot` running from `jason-mcp:source-727c3fa`;
- `jason-prometheus` running;
- `jason-grafana` running;
- `jason-usage-exporter.service` active;
- `jason-usage-attribution-exporter.service` active.

## Public MCP observation

Unauthenticated access to `https://mcp-jason.teamaot.com/mcp` returned HTTP 401, consistent with the protected read-only MCP boundary.

## Grafana observation

Grafana health reported:

- database: `ok`;
- version: `12.2.1`.

## System Registry observation

The current production registry contained 24 entities.

Relevant registered entities included the Jason runtime, direct Teams gateway, OpenBao, OpenClaw gateway, OpenClaw/Jason bridge, and the Teams gateway credential reference.

The registry did not yet contain current entities representing:

- the Jason MCP service;
- Prometheus;
- Grafana;
- the usage exporter;
- the usage-attribution exporter.

This is a documented operational-state reconciliation gap.

## Interpretation

The observed services are evidence of running components. They must not simply be called `active` or `verified` in the System Registry without the required declared-state records, verification methods, lifecycle events, evidence references, and authority metadata required by J-103.

## Next use of this proof

Use this snapshot as bounded evidence while creating the governed System Registry reconciliation. Do not use it as justification for runtime deployment or service changes.
