# Grafana / Observability Configuration Assurance — Production Acceptance — 2026-09-27

## Goal

Close the production reliability gap in Project Jason's Grafana/Prometheus observability layer so dashboards cannot silently depend on mutable worktrees or Grafana database-only state, and so dashboard/telemetry drift is detected continuously.

## Root causes found

The investigation identified four separate reliability defects:

1. production Grafana/Prometheus bind mounts pointed at a mutable historical feature worktree;
2. eight live dashboards existed only in Grafana's database and had no authoritative Git source;
3. OpenAI dashboard panels could exist while their required organization usage/cost metrics were absent;
4. Docker bind mounts created through the mutable `/opt/jason/observability/current` symlink remained pinned to the prior resolved release after the pointer changed.

During activation two additional installer defects were corrected: the deployment script lacked an executable mode, and the assurance exporter initially reused toner exporter's established port `9473`. Grafana assurance now uses dedicated port `9474`.

## Accepted source and deployment boundary

- authoritative source revision: `f61ef43228d1f5072d425e11e5303ca3bb143079`;
- release directory: `/opt/jason/observability/releases/f61ef43228d1f5072d425e11e5303ca3bb143079`;
- current pointer resolves to that exact release;
- Docker bind mounts use the exact release directory, not a developer worktree or mutable symlink path.

## Production verification

Independent readback after deployment showed:

- Grafana Configuration Assurance report status: `PASS`;
- required dashboards: `21`;
- Grafana dashboards passing: `21`;
- source dashboard files passing: `21`;
- declared metric dependencies: `6`;
- metric dependencies passing: `6`;
- Grafana assurance exporter service: active;
- Grafana assurance timer: active;
- Prometheus `jason-grafana-assurance` target: `up` on `host.docker.internal:9474`;
- toner exporter remains on `9473`;
- OpenAI cost metrics restored and present for rolling 24-hour, recent 7-day, and month-to-date windows.

## Alert acceptance

A disposable Prometheus `v3.7.3` `promtool` rule test evaluated the production alert expressions against synthetic assurance states.

Accepted result: `SUCCESS`.

The test proved both:

- `JasonGrafanaConfigurationDrift` fires after five minutes when assurance is `0` and deterministic drift is `1`;
- `JasonGrafanaAssuranceUnavailable` fires after five minutes when the state is `NOT_PROVEN`.

No production assurance state or alert source was modified for this test.

## Dashboard cold-recovery acceptance

A disposable Grafana `12.2.1` container was started on an isolated test port and attached to the existing observability network with only the immutable provisioning and dashboard source directories mounted read-only.

The first API inventory occurred after HTTP health but before dashboard provisioning completed and therefore recovered only 4/21 dashboards. This was correctly rejected as insufficient recovery evidence. Grafana logs subsequently recorded `finished to provision dashboards`.

After provisioning completion, the API inventory showed:

- expected dashboards: `21`;
- recovered dashboards: `21`;
- missing dashboards: `NONE`;
- extra dashboards: `NONE`.

The disposable recovery container was removed immediately after acceptance. No production Grafana database, dashboard, datasource, or runtime state was changed.

## Result

**PRODUCTION ACCEPTED / WORKSTREAM CLOSED.**

Project Jason's Grafana/Prometheus observability layer is now Git-authoritative, immutable-release deployed, continuously reconciled every five minutes, alert-covered, and cold-recovery proven for the full 21-dashboard inventory. Future dashboard changes must use the established branch -> manifest -> CI -> immutable release -> deployment verification -> assurance PASS process.
