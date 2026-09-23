# Jason Datto Component Control

Status: Production accepted 2026-09-18

## Purpose

Jason Component Control provides a governed, durable way to decide which Datto RMM components Jason may select and execute without a per-run technician approval.

## Grafana control page

Dashboard UID: `jason-component-control`

The page contains:

- the complete live Datto RMM component catalog;
- current autonomous/per-run policy state;
- safety eligibility and block reason;
- approval source and approval metadata;
- a checkbox list for all components currently eligible for autonomous use;
- **Select All Eligible**, **Select None**, **Refresh**, and **Apply Autonomous Approvals** controls;
- one confirmation before bulk approval/revocation changes are written.

At production acceptance the complete governed catalog contained 556 components. Three were already standing-safe and 435 were eligible for autonomous approval under the current server-side safety policy.

## Governance

The Grafana page changes Jason's approval registry only. It never executes a Datto component directly.

- Approval and revocation are owner-level control-plane actions.
- The durable registry records exact component UID/name, approving identity, timestamps, reason, and a metadata fingerprint.
- Jason re-resolves the live component before execution.
- If reviewed component metadata changes, durable autonomous approval becomes stale and execution falls back to per-run approval.
- Generic ad-hoc PowerShell and components identified as clearly disruptive/destructive are not eligible for autonomous promotion through this surface.
- Managed-endpoint validation, variable policy, auditing, and the general prohibition on autonomous user-disruptive actions remain in force.

## Bulk control

The backend supports a selected set of up to 1000 component names in one governed request. The Grafana page computes the delta between the checked set and the current authoritative registry, then sends one bulk approve/revoke operation. Server-side eligibility is re-evaluated; the UI cannot override a server safety block.

## Security

Grafana uses a server-side Infinity datasource named `Jason Component Control`. Its authorization header is stored in Grafana secure datasource storage. Browser JavaScript calls only Grafana's same-origin datasource proxy; the Jason control token is never embedded in dashboard JSON or returned to the browser.

Grafana is connected to both `jason-observability` and the external `jason-core` Docker network so the proxy reaches `jason-mcp-pilot:8000` without adding a new public Jason listener.

## Acceptance evidence

- Complete Datto catalog enumerated: 556 components across seven provider pages.
- Grafana Infinity query returned all 556 component rows.
- Shadow registry test changed `Detect Boot Type (BIOS/UEFI) [WIN]` from per-run to autonomous and back to per-run without touching production policy.
- Production MCP component-control endpoint returned 556 components, 3 autonomous, and 435 eligible at cutover.
- Grafana dashboard `jason-component-control` is provisioned with the live catalog table and Business Forms approval panel.
