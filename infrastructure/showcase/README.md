# Jason Command Center Showcase

Project Jason's observability stack provides human-visible operational status without changing runtime authority. Grafana is provisioned from repository JSON under `infrastructure/showcase/grafana/dashboards`; Prometheus stores and evaluates secret-safe metrics; exporters read only local Jason/host state.

## Security boundary

- Grafana and Prometheus are observational only. Dashboard state never grants Jason or provider authority.
- Monitoring does not call Autotask, Datto RMM, IT Glue, or other production providers directly.
- Provider credentials, OAuth/JWT material, OpenBao AppRole values, prompts/responses, and raw provider evidence are not exported.
- `direct_provider_access=false`, Jason identity/authority, Central Orchestrator routing, exact grants, provider authorization, approval policy, and audit remain authoritative independently of monitoring state.

## Production-health deployment

For a monitoring-only refresh from a clean repository worktree:

```bash
chmod +x infrastructure/showcase/deploy_production_health_dashboard.sh
JASON_REPO_ROOT="$PWD" infrastructure/showcase/deploy_production_health_dashboard.sh
```

The deployment is rollback-protected. It validates source/configuration, installs only `jason-production-health-exporter.service`, refreshes only Prometheus and Grafana, verifies the Prometheus target/rules and Grafana provisioning, and confirms that Jason runtime, Jason MCP, OpenBao, Ollama, and node-exporter container identities did not change.

The script can safely recover the existing Grafana compose credential from the already-running Grafana container when the original mode-600 `.env` file is unavailable; secret values are not printed.

## Current production MCP monitoring contract

The 2026-09-16 accepted governed-action production boundary is monitored against:

- MCP image `jason-mcp:generic-governed-8f1e864947a2`;
- deployed code source `8f1e864947a2e6e79bf47d3de14daacde7d73144`;
- provider-read profile `itglue-autotask-entra-governed-catalog-v4`;
- Autotask requester mode `jason_managed`;
- network `jason-core`;
- port binding `10.87.246.157:8765 -> 8000/tcp`;
- restart policy `no`;
- exact Datto governed-execution profile `owner-diagnostic-v1`;
- exact controlled Datto allowlist/component/device/class scope used for the production proof;
- required read-only OpenBao credential mounts, including bounded Autotask write and Datto execution identities.

The source-revision contract accepts the exact runtime source environment value when current, and also accepts the commit-encoded current image tag. This prevents a preserved historical `JASON_SOURCE_REVISION` environment value from falsely overriding the stronger immutable deployed image identity.

## Exporters

### Production health exporter

`production_health_exporter.py` exposes secret-safe metrics on TCP 9467, including:

- runtime/MCP/OpenBao health;
- current MCP image/source/profile/network/port/restart/requester-mode contract checks;
- Datto bounded execution profile/scope checks;
- required credential mount contract;
- `jason_datto_governed_execution_contract`, a configuration-readiness gauge for the exact bounded Datto pilot;
- environment duplicate counts;
- kernel/systemd/root-filesystem health;
- preserved MCP rollback availability.

`jason_datto_governed_execution_contract=1` means the current MCP deployment matches the approved bounded configuration and required credential mounts. It is not a provider canary and does not mean a new execution is authorized.

### Other exporters

- `status_exporter.py` provides roadmap/legacy component-readiness and OpenClaw authority metrics.
- `usage_exporter.py` provides read-only model usage/cost and governed-request metrics from durable telemetry.
- `usage_attribution_exporter.py` provides authenticated-identity/capability attribution metrics.

## Grafana dashboards

### Jason Governed Actions

`jason-governed-actions.json` is the focused operational view for the current governed-action boundary. It shows:

- MCP availability;
- full production MCP contract state;
- credential mount contract;
- bounded Datto governed-execution contract;
- rollback availability;
- firing alerts;
- individual MCP contract checks; and
- the dated 2026-09-16 bounded production proof context.

The proof panel records that `Get-DNS Settings AOT Ver 06042025-1` on `AOT-50282` was accepted as one provider mutation/one attempt after explicit approval and was later verified `completed` through read-only `automation.job.read`. It intentionally does not treat that historical proof as authority for another execution.

### Jason Production Health

`jason-production-health.json` remains the broader host/runtime/MCP/OpenBao health dashboard. Its `MCP Contract` stat automatically includes the new Datto execution profile/scope checks because they are part of `jason_mcp_contract`.

### Jason Command Center

`jason-command-center.json` remains the broad host, roadmap, component, cost/usage, and attribution view.

## Alerts

Prometheus rules under `prometheus/alerts/jason-production.yml` remain fail-closed for runtime, MCP, OpenBao, deployment-contract, secret-mount, host-kernel/systemd/filesystem, rollback, and disk-capacity problems. Because the Datto profile/scope checks are part of `jason_mcp_contract`, drift is included in the existing `JasonMCPContractDrift` rule.

Prometheus/Grafana rule evaluation does not itself send Teams/email/pages. External notification routing is a separate operational decision.

## Current evidence

Current production state: `docs/control/CURRENT.md`.

Final bounded Datto proof: `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`.

Resolved governed-action checkpoint: `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`.
