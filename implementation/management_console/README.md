# Jason Management Console

The Jason Management Console is the governed web interface for configuring, observing, and administering Jason.

It is intentionally **not** a bypass around the orchestrator, Kernel, policy engine, or approval controls. The console is a client of governed Jason capabilities and management APIs.

## Initial scope

The first slice is read-only and operationally safe. It establishes the navigation and page model for:

- System overview and health
- Capability registry
- Connector/provider status
- Governance and policy status
- Approvals requiring human action
- Audit and execution history
- Identity and access visibility
- Configuration inventory
- Secrets metadata (names/status only; never secret values)
- Platform/dependency review status

Configuration changes will be added only after the corresponding governed management capabilities, authorization checks, validation, audit events, and approval requirements exist.

## Architectural rules

1. The console never invokes providers directly.
2. The console never invokes agents directly.
3. All consequential operations route through the central orchestrator and normal governance gates.
4. Missing authority, organization isolation, or capability resolution fails closed.
5. Secret values are never rendered into the browser after storage.
6. Every state-changing operation must produce an auditable execution/event record.
7. The UI should discover capabilities and configuration schemas from Jason rather than hard-code vendor-specific workflows where practical.
8. Read-only visibility should arrive before write controls.

## Proposed navigation

```text
Dashboard
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

## Foundation implementation

This directory begins with a static prototype so the information architecture can be reviewed before a framework or deployment choice becomes architectural baggage.

Files:

- `prototype/index.html` — management console shell and dashboard prototype
- `prototype/styles.css` — visual baseline
- `prototype/app.js` — navigation/demo behavior
- `management-api-v0.1.yaml` — initial read-only API contract for the console

The prototype contains no production credentials and performs no live operations.
