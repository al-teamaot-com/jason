# Grafana Integration for Jason

Grafana is the preferred operational user interface for Jason.

## Why Grafana

Jason should not maintain a custom implementation of capabilities Grafana already provides well: dashboards, operational exploration, alerting, metrics, logs, traces, variables, navigation, and version-controlled dashboard provisioning.

The integration must preserve Jason's control boundaries. Grafana presents state and requests governed actions; Jason determines whether those actions are authorized and how they are executed.

## Integration model

### Phase 1 - read-only operations

Expose governed Jason management state through the Management API and render it in Grafana:

1. Kernel and orchestrator health.
2. Capability registry inventory and status.
3. Provider/connector inventory and health.
4. Audit and execution history.
5. Pending approvals.
6. Configuration metadata.
7. Secret metadata, excluding values.
8. Platform Stewardship dependency status.

No production write is enabled in this phase.

### Phase 2 - observability data plane

Publish stable operational metrics, logs, and traces to suitable observability backends and use Grafana's native data-source model for high-volume operational telemetry.

The Management API remains appropriate for governed business/control-plane state. It should not become a high-volume metrics transport merely to feed dashboards.

### Phase 3 - Jason Grafana app

Add a Jason app plugin only where normal dashboards are insufficient. Candidate pages include:

- approval review;
- configuration management;
- identity/capability grants;
- secret lifecycle metadata and rotation requests;
- capability/provider detail pages;
- Platform Stewardship review workflow.

The app may submit requests to Jason's Management API, but it must never call operational providers directly.

### Phase 4 - governed writes

State-changing UI controls are enabled only when a corresponding Jason capability exists and is governed end-to-end:

```text
Grafana UI
   -> Jason Management API
   -> Orchestrator
   -> Identity / organization isolation
   -> Policy and risk classification
   -> Human approval when required
   -> Governed capability resolution
   -> Provider execution
   -> Audit / evidence
```

## Data-source boundary

Use the most native Grafana path for each kind of information:

| Information | Preferred path |
| --- | --- |
| Metrics | Prometheus-compatible or approved metrics backend |
| Logs | Loki-compatible or approved log backend |
| Traces | Tempo-compatible or approved trace backend |
| Governed Jason inventory/state | Jason Management API |
| Audit analytics | Approved audit store/data source, with Management API for authoritative detail |
| Configuration mutation | Jason Management API -> governed capability |
| Secrets | Metadata only through Jason; never raw secret values |

No particular observability backend is constitutional. The architecture remains portable.

## Dashboard-as-code

Grafana dashboard and provisioning artifacts should be version controlled. Generated/exported dashboard JSON is an implementation artifact, not a replacement for Jason's canonical architecture and policy documentation.

The initial dashboard provider is in `provisioning/dashboards/jason.yaml` and the dashboard shell is in `dashboards/jason-overview.json`.

## Security rules

- Treat Grafana authentication and RBAC as presentation-layer controls, not as a replacement for Jason authorization.
- Jason independently validates principal, organization, capability, risk, and approval requirements.
- Never place provider credentials or Jason secret values in dashboard JSON.
- Prefer server-side/proxied authenticated calls rather than browser-held provider credentials.
- Record consequential requests in Jason even if Grafana also logs the UI interaction.
- Fail closed when Jason cannot establish authority or organization isolation.

## Immediate implementation sequence

1. Keep `management-api-v0.1.yaml` as the contract for governed operational state.
2. Implement the first live read-only endpoints in Jason.
3. Deploy Grafana in the Jason environment or attach an approved existing instance.
4. Provision the Jason folder and overview dashboard from source control.
5. Connect health, capabilities, providers, and audit data.
6. Add alert rules only after the source signals and ownership are defined.
7. Evaluate a Jason app plugin after the read-only dashboard proves the information architecture.

This sequence deliberately avoids prematurely building a custom frontend or enabling control-plane writes.
