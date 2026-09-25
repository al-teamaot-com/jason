# Jason Autonomy Flight Recorder

## Purpose

The Flight Recorder is a read-only Grafana view of Jason's autonomous execution evidence. It answers, without clutter:

- what Jason ran;
- which ticket/device/client the governed execution targeted when that context is present;
- the playbook/version and capability;
- provider result, concise failure reason when unsuccessful, and attempt count;
- verification/readback result;
- full sanitized execution-plan/result/audit details on demand.

The dashboard is **evidence only**. It is not an authority source and cannot approve, promote, retry, or execute anything.

## UI

Dashboard UID: `jason-autonomy-flight-recorder`

Default view:

- Autonomous actions today
- Verified today
- Failed / blocked today
- Waiting / recheck
- Active autonomy
- one compact action-history table

The table keeps only operationally useful columns visible. The `Details` cell uses Grafana's native JSON viewer so execution IDs, correlation IDs, fingerprints, normalized plan/payload, provider output, and verification stay hidden until requested.

Routine shadow queue reads are excluded from the main history and action counters so reconciliation noise does not bury real actions. The JSON API can still expose read-only executions with `kind=read` for diagnostics.

## Data sources

The containerized `autonomy_flight_recorder_exporter.py` reads existing Jason SQLite evidence stores through read-only bind mounts:

- orchestration event store;
- governed execution ledger;
- JKD-001 authority/approval store;
- autonomy shadow run store.

It performs no Autotask, Datto, provider, runtime, or authority mutation.

Surfaces:

- `GET /metrics` — low-cardinality Prometheus gauges;
- `GET /api/actions?kind=action` — sanitized autonomous action records;
- `GET /api/actions?kind=read` — governed autonomous reads for diagnostics;
- `GET /api/actions/<execution_id>` — one full sanitized record;
- `GET /healthz` — exporter health.

## Secret/data handling

The exporter recursively redacts fields whose keys indicate credentials/secrets/tokens/passwords/API keys/authorization/cookies/private keys and strips common bearer/basic credential strings. Large strings are bounded before export.

High-cardinality ticket IDs, execution IDs, correlation IDs, fingerprints, command/component output, and normalized payloads are **not Prometheus labels**. They exist only in the JSON detail surface.

## Deployment

Run from a clean current checkout:

```bash
infrastructure/showcase/deploy_autonomy_flight_recorder.sh
```

The deployment starts/recreates only the Flight Recorder, Prometheus, and Grafana services in the existing observability Compose project. Jason Runtime, Jason MCP, and OpenBao are outside the deployment target and their container IDs are verified unchanged.
