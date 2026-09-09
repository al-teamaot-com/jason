# Project Jason — Command Center Usage Attribution Deployment Proof

**Date:** 2026-09-09  
**Classification:** Evidence / deployment proof  
**Status:** Accepted deployment checkpoint

## Purpose

Preserve the accepted deployment state for the Jason Command Center usage and actor-attribution telemetry work without implying that later source-only instrumentation has been promoted into the production runtime.

## Accepted deployed source

Accepted live dashboard/telemetry deployment commit:

`ecc265ee59645154f0bc86b5aa0dc5a2e375f022`

Accepted deployment result:

- source identity: PASS;
- precheck: PASS;
- exporters: PASS;
- monitoring containers: PASS;
- runtime/service isolation: PASS;
- Prometheus Jason usage target: UP;
- Prometheus Jason usage-attribution target: UP;
- Jason Command Center dashboard: READY;
- Jason Usage & Attribution dashboard: READY;
- secret surface: PASS;
- dashboard telemetry deployment: PASS.

Rollback backup preserved at:

`/tmp/jason-usage-dashboard-rollback-20260909T164404Z`

## Live components

The accepted deployment uses:

- `jason-usage-exporter.service`;
- `jason-usage-attribution-exporter.service`;
- `jason-prometheus`;
- `jason-grafana`.

Grafana is the human-facing Command Center surface. The exporters are observational. They do not grant capability authority and do not perform provider-side execution.

## Current source after deployment

Usage-attribution source work continued after the accepted deployment.

Current source-controlled telemetry/attribution checkpoint:

`e245fef72d220cce1fea63cb811a10c8196657b8`

This later source includes the conservative telemetry-quality correction for correlation-attributed model usage and passes the scoped Showcase Telemetry CI.

That source has not replaced the accepted live dashboard worktree or triggered a runtime deployment as part of this proof.

## Attribution boundary

Usage attribution is accounting/audit metadata. It does not grant authority, select client or organization scope, select provider authority, expose provider credentials, or create write authority.

Correlation-derived actor attribution is reported conservatively as inferred when the actor association is derived rather than ledger-native.

## Runtime boundary

The dashboard deployment intentionally did not restart or replace:

- `jason-runtime`;
- `jason-mcp-pilot`;
- `jason-teams-gateway`;
- OpenClaw;
- provider-facing execution services.

Runtime-side attribution instrumentation that exists in source remains a separate future activation decision.

## Live reconciliation observation

A 2026-09-09 read-only host snapshot subsequently confirmed:

- `jason-grafana` running;
- `jason-prometheus` running;
- `jason-usage-exporter.service` active;
- `jason-usage-attribution-exporter.service` active;
- Grafana database health `ok`;
- Grafana version `12.2.1`;
- the accepted live dashboard worktree remained detached and clean at `ecc265ee59645154f0bc86b5aa0dc5a2e375f022`.

## Related implementation documentation

- `infrastructure/showcase/README.md`
- `implementation/usage_attribution/README.md`

## Authority boundary

This proof establishes the accepted observability deployment checkpoint only. The System Registry remains the authoritative owner of declared/effective operational topology once the corresponding entities and lifecycle evidence are reconciled.
