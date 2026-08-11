# Jason Management Console

The Jason Management Console is the governed operational and administrative interface for Jason.

## UI strategy: Grafana first

Grafana is the preferred primary operations console for Jason. This follows Jason's integrate-before-innovate principle: use Grafana for dashboards, observability, status views, alerting, exploration, and operational navigation rather than maintaining a parallel custom dashboard stack.

Jason remains authoritative for identity, authorization, policy, approvals, capability resolution, configuration semantics, execution, and audit.

Grafana is therefore a client of Jason, not a control-plane bypass.

```text
Grafana
   |
   +--> dashboards / alerts / operational views
   |
   +--> Jason app pages when specialized management UX is required
                |
                v
       Jason Management API
                |
                v
           Orchestrator
                |
     +----------+-----------+
     |          |           |
 Identity    Policy      Approval
     |          |           |
     +----------+-----------+
                |
                v
       Capability Resolution
                |
                v
       Approved Provider
                |
                v
          Audit / Evidence
```

## Responsibility boundary

### Grafana owns

- system and component health visualization;
- capability and provider operational dashboards;
- audit and execution visualization;
- metrics, logs, traces, and alert presentation;
- platform stewardship dashboards;
- read-only operational exploration;
- navigation into Jason-specific management pages.

### Jason owns

- authenticated principal and organization context;
- identity-first authorization;
- capability visibility and grants;
- deterministic policy evaluation;
- risk classification;
- human approvals;
- configuration validation and mutation;
- secret lifecycle operations;
- provider selection and invocation;
- evidence and permanent audit records.

## Identity exchange boundary

Grafana must never create Jason principal or organization identifiers from browser input, dashboard variables, or arbitrary headers. The production path must validate an external identity through an approved adapter, resolve that identity against a governed Jason binding, and mint a short-lived Jason management token. The caller cannot choose its Jason principal or organization scope.

```text
TeamAOT identity provider
        |
        v
approved external-token validator
        |
        v
verified external identity
        |
        v
governed external-identity binding
        |
        v
short-lived signed Jason management token
        |
        v
Grafana server-side request
        |
        v
Jason Management API authorization
```

The exchange contract is provider-neutral. Microsoft Entra ID can be the first external identity provider without making Entra-specific claims or APIs constitutional. Signing-key material belongs behind Jason's secret/key-management boundary and is never stored in Grafana dashboard JSON or repository configuration.

## Initial scope

The first slice is read-only and operationally safe:

- System overview and health
- Capability registry
- Connector/provider status
- Governance and policy status
- Approvals requiring human action
- Audit and execution history
- Identity and access visibility
- Configuration inventory
- Secrets metadata only; never secret values
- Platform/dependency review status

Configuration changes are added only after corresponding governed management capabilities, authorization checks, validation, audit events, and approval requirements exist.

## Architectural rules

1. Grafana never invokes providers directly.
2. Grafana never invokes agents directly.
3. Grafana is not an authorization authority for Jason operations.
4. All consequential operations route through the central orchestrator and normal governance gates.
5. Missing authority, organization isolation, or capability resolution fails closed.
6. Secret values are never returned for display after storage.
7. Every state-changing operation must produce an auditable execution/event record.
8. The interface discovers capabilities and configuration schemas from Jason rather than hard-coding vendor-specific workflows where practical.
9. Read-only visibility arrives before write controls.
10. Grafana dashboards and provisioning should be stored as version-controlled artifacts where practical.
11. External identity is mapped to Jason identity through governed bindings; callers cannot self-assert principal or organization scope.
12. Management identity tokens are short-lived and signed; token issuance is separate from Grafana presentation logic.

## Planned Grafana navigation

```text
Jason
  Overview
  Capabilities
  Connectors
  Governance
  Approvals
  Audit
  Identity & Access
  Configuration
  Secrets
  Platform Stewardship
  System
```

Standard Grafana dashboards should be used where visualization is sufficient. A Jason Grafana app plugin may provide custom pages for management workflows that cannot be represented cleanly as dashboards.

## Files

- `management-api-v0.1.yaml` — initial read-only Management API contract.
- `grafana/README.md` — Grafana integration design and implementation sequence.
- `grafana/provisioning/dashboards/jason.yaml` — dashboard-as-code provisioning baseline.
- `grafana/dashboards/jason-overview.json` — initial Jason overview dashboard shell.
- `../../deploy/grafana/compose.yaml` — local Grafana deployment baseline.
- `../../deploy/grafana/.env.example` — non-secret environment template.
- `../../deploy/grafana/README.md` — bootstrap, security boundary, and production prerequisites.
- `../management_api/identity_exchange.py` — provider-neutral governed external-identity binding and short-lived management-token exchange contract.

The earlier standalone HTML/CSS/JavaScript prototype was intentionally retired before merge. Grafana now provides the UI foundation rather than Jason maintaining a second general-purpose dashboard framework.
