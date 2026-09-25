# AOT KFS Toner Readiness — Production Operations

**Status:** Production, read-only observability  
**Deployed:** 2026-09-25  
**Dashboard:** `AOT Toner Readiness`  
**Exporter:** `jason-toner-exporter.service`  
**Prometheus job:** `jason-toner`

## Purpose

Provide AOT with a morning operational view that answers:

> **Which toner should we ship today?**

The current production implementation is observational only. It reads existing KFS history, calculates toner risk, exposes metrics to Prometheus, and presents the results in Grafana. It does **not** create Autotask tickets, create or modify purchase orders, send customer communications, or change KFS/provider state.

## Production architecture

```text
Nightly KFS collector
        |
        v
jason-kfs-postgres
        |
        | read-only analysis
        v
jason-toner-exporter.service
        |
        | Prometheus metrics on TCP 9473
        v
jason-prometheus
        |
        v
AOT Toner Readiness (Grafana)
```

The exporter refreshes its cached KFS analysis every 15 minutes. Prometheus scrapes the cached metrics rather than triggering a KFS database query on every scrape.

## Data sensitivity and access boundary

Toner readiness is an internal AOT operational dashboard. Unlike aggregate security/posture metrics, toner metrics intentionally contain customer-identifying operational labels needed to fulfill toner shipments, including customer name, device identifier/serial, toner color, part number, action state, and telemetry state.

These metrics contain no provider credentials, OAuth/JWT material, secrets, raw provider payloads, or autonomous authority. Prometheus and Grafana for this dashboard must remain inside AOT's protected observability boundary and must not be exposed publicly or treated as customer-facing reporting without a separate review.

## Current production logic

The current model uses:

- KFS toner-level history by customer, device, color, and part number;
- recent median toner decline rate normalized per day;
- current toner percentage;
- KFS successful-run history;
- device and individual toner-stream freshness;
- probable cartridge-replacement events;
- customer identity and toner part-number completeness.

Current action bands are:

- `ship_today`: toner <=5%, or projected depletion <=7 days;
- `ship_soon`: toner <=15%, or projected depletion <=14 days;
- `watch`: not yet actionable;
- `needs_review`: telemetry, identity, part-number, or trend evidence is insufficient to make a shipping recommendation safely.

These thresholds are operational starting points and should be tuned using observed AOT results.

## Hard telemetry safety gate

**No fresh telemetry = no Ship Today or Ship Soon recommendation.**

Freshness is measured against successful KFS collections, not calendar days:

- `current`: device and toner appear in the latest successful collection;
- `stale`: device missed one successful KFS collection;
- `not_reporting`: device missed two or more successful collections;
- `long_term_missing`: no fresh device telemetry for at least 7 days;
- `toner_stale`: device is current but that toner stream did not update in the latest successful collection;
- `collection_stale`: the latest successful KFS collection itself is older than 36 hours.

Any non-current state forces the affected toner to `needs_review`. A stale historical toner level must never remain actionable as though it were current.

## Cartridge replacement detection

A probable toner replacement is currently inferred when:

- the previous toner level is <=15%;
- the next reading is >=90%; and
- the increase is at least 60 percentage points.

A transition from <=10% to >=95% is treated as higher-confidence evidence.

Example:

```text
4% -> 100%
```

This event gives AOT a practical confirmation signal that toner was likely installed. Over time, replacement events can be compared with earlier Jason shipping recommendations and Autotask toner-order activity.

## Validation loop

The intended closed-loop validation sequence is:

1. Jason/Grafana recommends `ship_today`.
2. Compare the recommendation with the Autotask toner order / purchase-order record.
3. Observe the later KFS probable replacement event.
4. Measure recommendation-to-order and recommendation-to-replacement timing.
5. Track misses, early recommendations, duplicate avoidance, model/color reliability, and customer-specific behavior.

Autotask order correlation is not yet active in the production dashboard. It is the next planned enrichment layer before any order/ticket automation is considered.

## Seasonality

Seasonality is intentionally **not yet active**. Production currently reports `seasonality_status=insufficient_history` rather than inventing a seasonal adjustment.

The future model must learn seasonality separately for each customer/device. Holiday labels are context, not assumptions. For example, one customer may slow during Thanksgiving while another may increase usage. The model should learn weekday, holiday, monthly, and recurring busy/slow patterns from that customer's actual meter history.

The intended future chain is:

```text
historical meter usage
    -> customer/device seasonality
    -> future page-volume forecast
    -> observed toner yield
    -> projected toner demand
    -> shipping recommendation
```

## Dashboard interpretation

Primary sections are:

- **Ship Today** — fresh, sufficiently mapped toner streams meeting the current urgent threshold;
- **Ship Soon** — fresh, sufficiently mapped toner streams likely to require action in the next 7–14 days;
- **Needs Review** — stale/missing telemetry or incomplete identity/part-number evidence;
- **Watch** — currently not actionable;
- **KFS Collector Age** — freshness of the latest successful collector run;
- **Devices Not Current** — KFS devices that are not reporting currently;
- **Toner Streams Not Current** — individual toner streams that are stale even if the device itself still reports;
- **Detected Cartridge Replacement Events** — low-to-full transitions found in the analysis window.

## Service and file locations

Production source:

- `infrastructure/toner-intelligence/toner_intelligence.py`
- `infrastructure/toner-intelligence/toner_snapshot.py`
- `infrastructure/toner-intelligence/toner_metrics.py`
- `infrastructure/toner-intelligence/toner_exporter.py`

Observability integration:

- `infrastructure/showcase/systemd/jason-toner-exporter.service`
- `infrastructure/showcase/prometheus/file_sd/jason-toner.json`
- `infrastructure/showcase/prometheus/prometheus.yml`
- `infrastructure/showcase/grafana/dashboards/jason-toner-readiness.json`
- `infrastructure/showcase/deploy_toner_readiness.sh`

Runtime state/cache:

- `~/.local/state/jason/toner-intelligence/snapshot.json`

## Service operation

The exporter runs as a persistent user-level systemd service under the existing Jason user systemd manager.

Useful checks:

```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user status jason-toner-exporter.service
curl -fsS http://127.0.0.1:9473/metrics | head
curl -fsS 'http://127.0.0.1:9090/api/v1/query?query=up%7Bjob%3D%22jason-toner%22%7D'
```

Expected healthy conditions:

- user service is `active` and `enabled`;
- `jason_toner_exporter_refresh_success 1`;
- Prometheus `up{job="jason-toner"} = 1`;
- Grafana can read `jason-toner-readiness.json`.

## Deployment

From canonical `main`:

```bash
JASON_REPO_ROOT="$PWD" infrastructure/showcase/deploy_toner_readiness.sh
```

The deployment validates tests, Python syntax, Grafana JSON, Prometheus configuration, exporter metrics, Prometheus target health, and Grafana dashboard visibility.

Prometheus is recreated when the scrape configuration changes because its bind-mounted `prometheus.yml` can otherwise retain the previous inode after a Git fast-forward/replacement.

## Current production evidence — 2026-09-25

At final deployment verification:

- `jason-toner-exporter.service`: active and enabled;
- Prometheus `up{job="jason-toner"}`: `1`;
- current `ship_today` metric count: `35`;
- unit tests: 11 passed;
- Prometheus metrics validation: passed;
- production Git tree: clean;
- deployment commit: `9043480` (`Recreate Prometheus when toner scrape config changes`).

The exact Ship Today/Ship Soon/Needs Review counts are volatile operational data and must not be treated as permanent documentation.

## Explicit non-goals / current limitations

The production toner-readiness system currently does **not**:

- create toner orders;
- create or update Autotask tickets;
- create or modify Autotask purchase orders;
- notify customers;
- infer customer holiday behavior without enough history;
- claim stale toner data is actionable;
- automatically resolve missing customer mapping or missing part numbers;
- grant Jason any additional provider authority.

Any future write/action workflow must remain separately governed and approved under Jason's normal authority model.

## Historical design record

The initial nonproduction design and acceptance criteria remain preserved in:

`docs/operations/KFS-Toner-Intelligence-Nonproduction-2026-09-25.md`

That document is historical design evidence and should not be used as the current production operating source.
