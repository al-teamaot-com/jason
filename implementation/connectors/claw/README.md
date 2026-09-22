# Claw Connector

## Identity

**Claw** is the external legacy OpenClaw instance at AOT that Jason is progressively absorbing. It is intentionally distinct from Jason's internal `openclaw` ingress, Teams gateway, and runtime components.

Provider ID: `claw`

The provider name is part of the operational distinction:
- **Claw** = external legacy automation/data source.
- **OpenClaw** = Jason's internal OpenClaw integration/runtime components.

## Transport

Jason connects to Claw only through the governed HTTPS MCP bridge.

The connector:
- requires HTTPS;
- validates Claw with the configured private CA;
- authenticates with a bearer token resolved at runtime from OpenBao;
- uses MCP `tools/call` JSON-RPC;
- supports JSON and SSE-style MCP responses;
- never logs the bearer token or CA contents.

## Provider capabilities

The provider exposes these internal connector capabilities:
- `claw.capabilities.read` -> `openclaw_bridge_status`
- `claw.status.read` -> `openclaw_status_summary`- `claw.artifact.read` -> `openclaw_read_artifact`
- `claw.task_request.search` -> `openclaw_list_task_requests`
- `claw.task_request.create` -> `openclaw_create_task_request`

Jason maps those provider operations to provider-neutral canonical capabilities:
- `operations.source.capabilities.read`
- `operations.source.status.read`
- `operations.artifact.read`
- `operations.task.request.search`
- `operations.task.request.create`

The create capability is deliberately **BUILDING** and `mcp_action_enabled=false`. Initial activation is read-only.

## Artifact boundary

Artifact reads are additionally allowlisted in Jason. The connector never accepts arbitrary paths. Current keys are:
`automation_health`, `daily_ops_json`, `daily_ops_latest`, `gpt_insight_trace`, `heartbeat`, `kfs_dashboard`, `ops_snapshot`, `saas_alerts_log`, `saas_alerts_usage`, `status_board`, `today_memory`, `todo`, and `worklog`.

## Secret contract

Logical secret: `claw.runtime`

OpenBao path: `secret/data/connectors/claw/production/runtime`

Required fields: `mcp_url`, `bearer_token`, and `ca_cert_pem`.
The AppRole identity is provider-specific. Claw credentials are not shared with Datto, Autotask, Microsoft, or another connector.

## Governance

The initial provider lifecycle is governed read-first.

Read authority uses the existing JKD-001 `provider-read:claw` grant pattern. No read capability creates a task, invokes shell, browses, touches a device, or performs a direct external action.

The staged task-request write may only be activated after:
1. an explicit write authority model is approved;
2. the capability is moved from BUILDING to ACTIVE;
3. `mcp_action_enabled` is intentionally enabled;
4. a post-create queue readback verification is defined.

## Migration role

Claw is a temporary operational source during migration. Jason should use it to inventory automations, schedules, status, reports, logs, and task history. Existing Claw automations remain active until an individual workflow has been reproduced, verified, and explicitly cut over to Jason.
