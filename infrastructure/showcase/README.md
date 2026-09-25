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

The current production boundary is no longer the 2026-09-16 v4 pilot. The accepted 2026-09-25 contract is:

- provider-read profile `itglue-autotask-entra-procurement-mail-contract-attachment-catalog-v8`;
- Central Orchestrator authoritative;
- `direct_provider_access=false`;
- generic governed execution enabled;
- exact write/action profiles may be active when separately approved;
- attachment reads active under v8;
- `service.ticket.attachment.create` active only through the dedicated writer profile and exact approval-required authority;
- required OpenBao credential mounts present;
- runtime/MCP source/profile drift checked against the currently accepted deployment rather than a hard-coded historical v4 image.

Use `docs/control/CURRENT.md` and live container labels/health as the current volatile source boundary. Historical 2026-09-16 Datto proof remains evidence, not the current monitoring contract.

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
- `resolution_memory_exporter.py` provides aggregate Resolution Memory availability/case metrics without raw case content.
- `security_control_exporter.py` provides aggregate secret-safe authority/execution-plan/fail-closed control metrics.
- `client_posture_exporter.py` provides aggregate client-posture classification counts without client identity labels.

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

### Jason Security & Learning

`jason-security-learning.json` shows Resolution Memory/security-control state, source lifecycle, durable autonomy state, and security dispositions. Evidence is explicitly not authority.

### Jason Client Security Posture

`jason-client-security-posture.json` shows aggregate posture-review counts (`confirmed_good`, `confirmed_gap`, `unknown`, `not_applicable`, `evidence_unavailable`) without exposing client identity/evidence payloads.

### Jason Command Center

`jason-command-center.json` remains the broad host, roadmap, component, cost/usage, attribution, and operating-context view.

## Alerts

Prometheus rules under `prometheus/alerts/jason-production.yml` remain fail-closed for runtime, MCP, OpenBao, deployment-contract, secret-mount, host-kernel/systemd/filesystem, rollback, and disk-capacity problems. Because the Datto profile/scope checks are part of `jason_mcp_contract`, drift is included in the existing `JasonMCPContractDrift` rule.

Prometheus/Grafana rule evaluation does not itself send Teams/email/pages. External notification routing is a separate operational decision.

## Current evidence

Current production state: `docs/control/CURRENT.md`.

Final bounded Datto proof: `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`.

Resolved governed-action checkpoint: `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`.
