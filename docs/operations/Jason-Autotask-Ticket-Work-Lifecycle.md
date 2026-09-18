# Jason Autotask Ticket Work Lifecycle

Status: Production accepted 2026-09-18  
Source revision: `5854cf670e33df473a37890ad9c28b7069510b3e`

## Purpose

When Jason begins substantive work on an existing Autotask ticket, ticket ownership and operational state must be made explicit before troubleshooting proceeds. This is a standing Owner-approved administrative lifecycle transition and is not a substitute for approval of disruptive or otherwise separately gated remediation.

## Default start-work transition

For the exact resolved Autotask ticket, Jason must:

1. Move the ticket to queue **Jason**.
2. Set status to **In Progress**.
3. Set Work Type to **Remote Support**.
4. Preserve an existing primary configuration item/device association.
5. If no configuration item is linked, attempt deterministic device correlation from ticket context.
6. Preserve existing Ticket Type / Issue Type / Sub-Issue Type unless triage or the playbook has sufficient evidence for an exact supported classification.
7. When classification is supplied, resolve the exact live Autotask picklist labels before update; never hard-code tenant picklist IDs.
8. Require post-mutation readback for every field changed.

## Device association rule

Jason may associate a configuration item only when all of the following are true:

- ticket context yields one exact endpoint selector;
- governed DRMM search resolves exactly one endpoint with the exact hostname;
- the Autotask configuration is active;
- its `referenceTitle` exactly matches the endpoint hostname;
- its `referenceNumber` exactly matches the DRMM device UID;
- its company ID matches the ticket company; and
- exactly one configuration satisfies the complete relationship.

Hostname-only matching, first-match selection, inactive configurations, cross-company matches, and ambiguous candidates are not sufficient for an Autotask write. If deterministic correlation is unavailable, Jason leaves the configuration association unchanged and continues only when the playbook can safely proceed without inventing device identity.

## Classification rule

- Existing Ticket Type / Issue Type / Sub-Issue Type are preserved by default.
- Jason may set them when ticket evidence, alert semantics, or an approved playbook produces exact classification labels.
- Issue/Sub-Issue labels are resolved from live Autotask Ticket picklist metadata.
- Sub-Issue resolution is constrained to its resolved parent Issue Type.
- Work Type **Remote Support** is resolved from live active Autotask Billing Codes with ticket/labor use type; the numeric billing code is not hard-coded.

## Approval and governance

The ticket-work-start transition is a standing Owner-approved administrative action. Jason does not ask for a second approval merely to claim a ticket it has begun working. This standing policy is limited to the server-controlled start-work fields and does not authorize arbitrary ticket edits.

All normal governance remains in force:

- authenticated requester and exact Jason grant;
- Central Orchestrator execution;
- provider-native requester impersonation for Autotask writes;
- one bounded provider mutation attempt;
- post-mutation readback verification;
- `direct_provider_access=false`;
- disruptive/user-impacting actions still require explicit approval for that instance.

## Production acceptance

Controlled acceptance used XYZ Test Company ticket `T20260914.0026` / Autotask ID `140439`. Pre-change values were captured before mutation. The governed start-work transition completed with one provider attempt and built-in readback verification. Independent readback showed:

- queue ID `29683489` = **Jason**;
- status `8` = **In Progress**;
- billing/work-type ID `29682801` = **Remote Support**.

A repeated identical start-work transition also completed with the same verified state, demonstrating idempotent administrative behavior.

The controlled XYZ Test Company does not have a current DRMM-managed endpoint suitable for a safe live device-association acceptance. Device association therefore remains production-enabled but fail-closed and is covered by deterministic regression tests until a naturally occurring ticket provides an exact relationship suitable for live acceptance.

## Observability

- `Jason-Roadmap-Status.json` tracks the production-accepted lifecycle as milestone `OPS-TICKET-WORK-001`.
- The **Jason Governed Actions** Grafana dashboard carries the production acceptance proof and current policy summary.
- Per-run ticket-start counters are intentionally not exposed yet because a production playbook-event writer is not active. Add counters only when the orchestration path records authoritative ticket-start outcomes.
- `SUPPORT-CONN-002` is open: intermittent MCP `UNAVAILABLE / Connection failed` was reproduced during this acceptance while the MCP container remained healthy and immediate retries succeeded. Do not treat the dashboard's MCP process-health indicator as proof that the end-to-end client transport is healthy.

## Dashboard deployment verification

Production observability was refreshed on 2026-09-18 after the lifecycle acceptance:

- the status exporter emits `jason_roadmap_item_info{milestone="OPS-TICKET-WORK-001",status="complete",...} 1`;
- Prometheus returned exactly one live series for that completed milestone;
- Grafana's stored `jason-governed-actions` dashboard is version `2`;
- the loaded proof panel is **Governed Production Proof — through 2026-09-18**;
- the loaded panel includes both the Autotask ticket-work lifecycle acceptance and the open `SUPPORT-CONN-002` MCP transport warning.

No per-run ticket-work counters were added because the production playbook-event writer is not yet active. This is intentional: dashboards must not imply event telemetry that Jason does not actually persist yet.
