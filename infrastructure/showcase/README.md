# Jason Command Center Showcase

SHOWCASE-001 makes Project Jason visibly observable without changing runtime authority. The observability stack now covers host health, production runtime/MCP/OpenBao contract health, roadmap state, OpenClaw authority operations, model/API usage, and authenticated-user attribution.

## Components

- Grafana provides the human-visible dashboards.
- Prometheus stores showcase, host, production-health, usage, and attribution metrics and evaluates local alert rules.
- Node Exporter reports Linux host CPU, memory, filesystem, and related metrics.
- `status_exporter.py` exposes Jason-specific roadmap and legacy component-readiness metrics.
- `production_health_exporter.py` exposes secret-safe production runtime/MCP/OpenBao/host contract metrics on TCP 9467.
- `usage_exporter.py` exposes read-only model-cost, token, governed-request, and authenticated-user metrics from Jason's durable SQLite telemetry stores.
- `usage_attribution_exporter.py` exposes authenticated-user/capability attribution metrics.
- The machine-readable roadmap is stored in `07-Roadmap/Jason-Roadmap-Status.json`.
- Ollama provides the loopback-only local model runtime used by governed local-AI capabilities.

## Security boundary

- OpenBao remains on its existing deployment and is not reconfigured by this stack.
- Prometheus is bound to loopback only.
- Grafana is bound to TCP 3000 so the internal administrator can view the dashboards from the LAN.
- Grafana self-registration and analytics reporting are disabled.
- The Grafana administrator password is generated locally into `.env`; it is not committed to Git.
- Ollama is bound to loopback only.
- The status exporter is observational only. It reads roadmap state, Docker container state, local TCP readiness, and local model readiness.
- The production-health exporter is observational only. It reads Docker metadata, the unauthenticated OpenBao health endpoint, root mount state, failed-systemd state, and current-boot kernel error signatures. It never reads credential contents and never calls external providers.
- The usage exporter opens durable Jason telemetry databases in SQLite read-only/query-only mode. Missing sources fail closed and are reported unavailable rather than being created.
- Usage telemetry may export stable Jason identity IDs and Jason-owned display metadata needed for attribution; identity metadata is never used as an authority key.
- Prompts, model responses, OAuth/JWT tokens, API keys, provider credentials, OpenBao shares/AppRole values, and raw provider evidence are not exported to Prometheus or Grafana.
- Dashboard status never grants capability authority. Execution remains subject to normal Jason identity, authority, Central Orchestrator, provider authorization, information-release, policy, and audit boundaries.
- Production provider canaries are deliberately not implemented as direct API calls from monitoring. Future canaries must execute through Jason's governed read path and export only safe pass/fail/latency metadata.

## Install

From a clean repository worktree on the Jason host:

```bash
chmod +x infrastructure/showcase/install_showcase.sh
JASON_REPO_ROOT="$PWD" infrastructure/showcase/install_showcase.sh
```

`JASON_REPO_ROOT` allows the showcase to be deployed from an isolated worktree without modifying another checked-out Jason worktree. The full install script installs and verifies all exporters, refreshes Prometheus/Grafana provisioning, and prints the Grafana URL and generated local administrator credential.

For a production-health-only refresh that must not restart or recreate Jason runtime, Jason MCP, OpenBao, Ollama, or node-exporter, use the rollback-protected deployment:

```bash
chmod +x infrastructure/showcase/deploy_production_health_dashboard.sh
JASON_REPO_ROOT="$PWD" infrastructure/showcase/deploy_production_health_dashboard.sh
```

That deployment validates source/configuration first, installs only `jason-production-health-exporter.service`, refreshes only Prometheus and Grafana, verifies the Prometheus target/rules and Grafana dashboard, checks core container IDs for isolation, and rolls monitoring changes back if acceptance fails.

## Dashboards

### Jason Command Center

The provisioned `Jason Command Center` dashboard shows:

- Jason host availability;
- CPU use;
- memory use;
- root filesystem use;
- roadmap completion percentage and milestone table;
- OpenBao, OpenClaw Gateway, and local-LLM readiness;
- historical Autotask/CAP-003 readiness context;
- near-live model/API cost for today and month-to-date;
- rolling model attempts and token volume;
- cost by provider/model;
- unknown model-usage attempts and telemetry-source health;
- governed request volume;
- distinct active Jason identities; and
- request/capability attribution by authenticated identity.

### Jason Production Health

The `Jason Production Health` dashboard is the current operational view for the production v4 service boundary. It shows:

- `jason-runtime` running/healthy state;
- `jason-mcp-pilot` running state;
- OpenBao initialized/unsealed readiness;
- current-boot kernel/storage corruption-signature count;
- failed systemd unit count;
- root filesystem read/write state and capacity;
- accepted MCP image/source/profile/network/port/restart/requester-mode contract;
- duplicate watched MCP environment-entry count;
- required read-only credential mount contract;
- preserved pre-v4 rollback availability;
- currently firing Prometheus alerts; and
- host CPU/memory trend.

The accepted 2026-09-14 production MCP contract is image `jason-mcp:autotask-entra-67da8d80ca97-repaired`, source revision `67da8d80ca9703505d651e9e0935f5bd1aa7c651`, provider profile `itglue-autotask-entra-governed-catalog-v4`, network `jason-core`, port binding `10.87.246.157:8765 -> 8000/tcp`, restart policy `no`, and temporary Autotask requester mode `jason_managed`. These expected values are monitoring expectations only; they do not grant authority.

The v4 cutover currently has a known warning: duplicate Docker environment entries for source revision/profile/requester-mode were inherited from the old env file and then explicitly overridden. Live runtime composition and live provider reads prove the effective profile is v4, but the duplicate count remains visible until a controlled MCP recreation removes the ambiguity.

## Alerts

Prometheus evaluates `prometheus/alerts/jason-production.yml`. Current rules cover:

- production-health exporter missing/down;
- runtime unhealthy;
- MCP down;
- OpenBao not ready;
- MCP deployment contract drift;
- duplicate watched MCP environment values;
- credential mount contract drift;
- current-boot kernel/storage corruption signatures or unavailable kernel monitoring;
- failed systemd units or unavailable systemd monitoring;
- root filesystem not writable or state unavailable;
- missing pre-v4 rollback container; and
- root disk use above warning/critical thresholds.

Prometheus/Grafana rule evaluation does not itself send Teams/email/pages. External notification routing is a separate operational change and should be added deliberately.

## API usage and cost notes

The cost panels use the effective cost already recorded in Jason's append-only Model Usage Ledger. A provider-reported cost is preferred when present; otherwise the ledger's calculated cost is used. OpenAI token counts are provider-reported, but calculated dollar cost depends on configured model pricing; provider billing reconciliation can later be added without changing the dashboard contract.

## Local LLM

SHOWCASE-002 deployed CPU-only Ollama with `qwen3:1.7b` on the Jason host. Local inference remains a governed pilot rather than a high-throughput production service. CAP-003 projects only bounded business-relevant Autotask fields into the model context rather than sending entire raw provider objects.

## Operational source of truth

Current production state and open gaps are recorded in `docs/operations/Jason-Production-Status-2026-09-14.md`.

The monitoring contract and severity guidance are recorded in `docs/operations/Jason-Production-Monitoring-Baseline.md`.

Human-relevant output, foreign-key enrichment, and capability-aware answer behavior are recorded in `docs/architecture/Jason-User-Relevant-Output-and-Capability-Awareness.md`.
