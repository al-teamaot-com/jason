# Grafana / Observability Configuration Assurance

**Status:** Production-proven 2026-09-27
**Owner:** Jason Technology Steward  
**Purpose:** Prevent Grafana dashboards, provisioning, and required telemetry from silently drifting away from the authoritative GitHub source.

## Problem addressed

Historically, the production Grafana and Prometheus containers could be launched from an arbitrary Git worktree because the Compose file uses relative bind mounts. A worktree could therefore become an accidental production dependency. A dashboard change that existed only as an uncommitted worktree edit could remain visible for a time and later disappear after a redeploy, cleanup, or rebind.

The OpenAI API cost panels exposed this defect: the panels and the corresponding OpenAI organization usage/cost exporter implementation existed in historical worktree state but were not present in authoritative `main`.

## Authoritative boundary

Production observability is deployed from an immutable release:

- releases: `/opt/jason/observability/releases/<source-sha>`
- current pointer: `/opt/jason/observability/current`

Grafana dashboard and provisioning bind mounts must resolve into the current immutable release. A developer checkout or `/home/al/jason-worktrees/...` path is never an accepted production mount source.

GitHub remains authoritative. The immutable release is only a deployment artifact of an exact accepted Git revision.

## Dashboard manifest

`config/observability/grafana-dashboard-manifest.json` is the machine-readable dashboard contract. It records every repository-managed dashboard's:

- UID;
- title;
- repository path;
- SHA-256 digest.

It also declares required Grafana datasources and required Prometheus dependencies for critical dashboard functions. The OpenAI usage/cost chain explicitly requires:

- the usage-attribution target to be up;
- authoritative OpenAI usage source availability;
- authoritative OpenAI cost source availability;
- rolling 24-hour cost;
- recent 7-day cost;
- month-to-date cost.

`tools/update_grafana_manifest.py` regenerates dashboard identity/hash entries deterministically after an intentional dashboard source change. CI tests reject a manifest that no longer matches the repository dashboard files.

## Assurance states

`tools/grafana_assurance.py` emits exactly one top-level state:

- `PASS` — required source files, hashes, immutable mounts, Grafana health, dashboard UIDs/titles, datasources, and required Prometheus dependencies all match;
- `DRIFTED` — deterministic evidence proves a required element differs or is missing;
- `NOT_PROVEN` — the checker cannot obtain enough evidence to decide safely.

The checker is read-only. It never rewrites dashboards, reloads Grafana, modifies datasource state, or silently repairs drift.

## Continuous monitoring

The production control consists of:

- `jason-grafana-assurance.service` — deterministic one-shot assurance;
- `jason-grafana-assurance.timer` — runs assurance every five minutes;
- `jason-grafana-assurance-exporter.service` — serves the latest assurance state on port `9474`;
- Prometheus job `jason-grafana-assurance`;
- alerts `JasonGrafanaConfigurationDrift` and `JasonGrafanaAssuranceUnavailable`;
- `Grafana Configuration Assurance` and `Grafana Assurance Age` panels on `Jason Production Health`.

The latest report is stored at:

`/var/lib/jason/observability/grafana-assurance.json`

No secret values are exported in the report or Prometheus labels.

## Deployment and rollback

`tools/install_observability_assurance.sh <source-revision>` creates the immutable release and invokes the existing rollback-protected usage-dashboard deployment from that release.

The underlying deployment validates:

1. required source/configuration files;
2. clean Git source or an immutable `SOURCE_REVISION` marker;
3. usage and usage-attribution exporters;
4. OpenAI usage/cost telemetry availability;
5. Prometheus/Grafana health;
6. Grafana dashboard provisioning;
7. secret-surface checks;
8. the complete Grafana Configuration Assurance contract.

A failure before deployment acceptance invokes the existing rollback path and rebinds Prometheus/Grafana to the previous Compose source while restoring the prior exporter units.

After deployment acceptance, the installer persists the verified assurance report, installs the assurance service/timer/exporter, and enables continuous monitoring.

## Change discipline

Dashboard changes must follow:

`branch -> source change -> manifest regeneration -> tests -> PR -> protected CI -> immutable release -> deploy verification -> assurance PASS`

Editing a production-mounted dashboard file or relying on an uncommitted worktree is prohibited. `allowUiUpdates: false` remains enabled for the provisioned dashboard provider. Additional Grafana UI-created dashboards may exist, but they are not considered repository-managed or durable until exported, reviewed, committed, and added to the manifest.

## Failure handling

Drift detection does not authorize repair. A failed assurance run creates operational evidence and alerts. Remediation proceeds through the normal governed change path. This preserves the System Registry / constitutional rule against silent topology or configuration repair.
## Production acceptance — 2026-09-27

Production activation is complete and accepted at source revision `f61ef43228d1f5072d425e11e5303ca3bb143079`.

Accepted production evidence:

- `/opt/jason/observability/current` resolves to `/opt/jason/observability/releases/f61ef43228d1f5072d425e11e5303ca3bb143079`;
- Grafana dashboard and provisioning mounts resolve directly into that exact immutable release;
- Prometheus configuration, file-discovery, and alert-rule mounts resolve directly into the same immutable release;
- all 21 required dashboard source files match the manifest hashes and identities;
- all 21 required dashboards are readable through the Grafana API with expected UID/title identity;
- all 6 declared telemetry dependencies pass;
- authoritative OpenAI 24-hour, 7-day, and month-to-date cost metrics are present;
- `jason-grafana-assurance-exporter.service` is active on dedicated port `9474`;
- toner telemetry remains independently active on port `9473`;
- Prometheus reports the `jason-grafana-assurance` target healthy on `host.docker.internal:9474`;
- `jason-grafana-assurance.timer` is enabled and active on the five-minute cadence;
- persisted `/var/lib/jason/observability/grafana-assurance.json` reports `PASS`.

Two non-disruptive recovery/alert acceptance checks were also completed:

1. Prometheus `promtool` evaluated synthetic `DRIFTED` and `NOT_PROVEN` inputs and proved that `JasonGrafanaConfigurationDrift` and `JasonGrafanaAssuranceUnavailable` both reach firing state after their configured five-minute `for` interval.
2. A disposable fresh Grafana `12.2.1` container was started with only the immutable provisioning/dashboard sources. After provisioning completed, 21/21 required dashboards were recovered with no missing UIDs; the disposable container was then removed.

The first cold-recovery inventory was intentionally treated as not proven because Grafana health became available before dashboard provisioning had completed. Rechecking only after the provisioning completion log produced the accepted 21/21 result. Future recovery tests must wait for provisioning completion, not only HTTP health.

This closes the Grafana/observability reliability workstream. Future dashboard changes remain subject to the normal immutable-release, manifest, CI, deployment-verification, and five-minute assurance controls.
