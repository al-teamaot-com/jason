# Project Jason — Current Resume Point

**Updated:** 2026-09-16  
**Status:** The governed-action usability path for Autotask and Datto RMM through ChatGPT is live-proven for the bounded production pilots described below.  
**Canonical purpose:** Human-readable resume point. Volatile production facts still require fresh runtime evidence before consequential change.

## Durable operating principle

> **ChatGPT reasons. Jason governs and executes.**

ChatGPT is the primary technician conversational surface. Jason remains authoritative for identity, scope, grants, approval policy, provider isolation, Central Orchestrator execution, evidence, and audit. A ChatGPT tool call is a governed request, not provider authority.

## Current live MCP boundary

The production MCP service is `jason-mcp-pilot`.

The deployed code source used for the current live MCP image is:

- source commit: `8f1e864947a2e6e79bf47d3de14daacde7d73144`;
- source message: `Expose governed Datto job reference for readback`;
- image: `jason-mcp:generic-governed-8f1e864947a2`;
- image ID: `sha256:d709ca54b66d41e22bd1f67782cd5f6d681c4337bffb359b632523762a27788a`.

Documentation-only commits may be newer than the deployed code source. Do not equate repository HEAD with deployed code without checking the live image/source relationship.

A fresh live MCP self-report after deployment returned:

- `status=ok`;
- `mode=governed-read-plus-actions`;
- `phase=governed-action-pilot`;
- `governed_execution=central-orchestrator`;
- `generic_execution_tool=true`;
- `direct_provider_access=false`;
- `write_tools_enabled=true`;
- active write/action capabilities:
  - `automation.component.execute`;
  - `service.ticket.note.create`;
  - `service.ticket.update`;
- write authority: `jason_exact_grant_plus_per_execution_approval`.

The current ChatGPT session also received and successfully used `execute_governed_capability`; the earlier client-action exposure blocker is resolved.

## Autotask governed proof

The bounded controlled pilot used XYZ Test Company ticket `T20191013.0001` (Autotask ticket ID `8870`). Jason changed the reversible priority from `3` to `2` through `service.ticket.update`, and a later governed read independently confirmed `priority=2`.

This proves the bounded Autotask ticket-update path, not arbitrary Autotask CRUD. Activated capabilities, exact Jason grants, provider authority, and required per-execution approval remain authoritative.

## Datto RMM governed proof

Governed Datto reads are working. The controlled endpoint is `AOT-50282` with device UID `69571572-83f7-1e33-9cdf-01717d4e74a4` at Atlantic Office Machines.

The controlled diagnostic component is `Get-DNS Settings AOT Ver 06042025-1`, component UID `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`, under allowlist `AOT governed diagnostic pilot`.

On 2026-09-16, after explicit AOT Owner approval, Jason executed exactly one governed `automation.component.execute` request with no variables, reboot, or disruptive action. The provider accepted one Datto quick job on the first attempt. Immediate readback returned the durable job UID `422d680b-a5ce-4473-b8e8-5d682ec85682` with state `active`, `readback_verified=true`, and `completion_verified=false` because Datto execution is asynchronous.

Jason then used only the read-only `automation.job.read` capability until the same job reached terminal state `completed`.

Evidence identifiers:

- action correlation: `corr_mcp_action_a1405f1b1c604ab7b92c88032c02ed1b`;
- final governed job-read correlation: `corr_mcp_25120cdec51d4dbaa837bb6f9bb43b60`;
- final proof record: `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`.

The earlier HTTP 403 was a historical provider-authorization stage and is no longer a current blocker.

## Datto asynchronous execution rule

An approved Datto quick job may legitimately return:

- action result `status=accepted`;
- `job_status=active`;
- `readback_verified=true`;
- `completion_verified=false`;
- a durable `job_uid`.

That is accepted asynchronous execution, not failure. Do not issue a second provider mutation because the first job is still active. Use the returned `job_uid` with read-only `automation.job.read` until a terminal state is observed.

## Security boundary that remains mandatory

- `direct_provider_access=false`;
- Central Orchestrator is the governed execution coordinator;
- provider credentials are never released to ChatGPT;
- read and write/execution identities remain separated where required;
- Datto execution remains bounded to approved component/target policy rather than arbitrary script text;
- failed authority/provider checks fail closed;
- provider actions do not retry through a broader credential;
- exact Jason grants and required per-execution approval remain mandatory;
- user-disruptive actions require explicit technician approval for the exact disruptive action.

## System Registry

The narrative proof does not itself promote System Registry lifecycle state. A governed `system.registry.search` performed during this wrap-up returned no matching structured resource for this specific proof state, and no governed registry write surface is currently exposed to this session.

Therefore the System Registry was intentionally left unchanged rather than inventing lifecycle truth. Reconcile it only through its authoritative governed registration/verification path when that path is available.

## Grafana / production observability

The authoritative Grafana source is repository-provisioned under `infrastructure/showcase/grafana`, with the production-health deployment handled by `infrastructure/showcase/deploy_production_health_dashboard.sh`.

The 2026-09-16 wrap-up updates the production-health monitoring contract to the current governed MCP image and adds explicit secret-safe Datto governed-execution configuration visibility. Grafana remains observational only; dashboard state does not grant execution authority and does not directly call providers.

## Workstream status

The bounded governed-action usability goal is complete:

1. Autotask governed read — **proven**.
2. Autotask bounded governed ticket update with durable readback — **proven**.
3. Datto RMM governed read — **proven**.
4. Datto RMM bounded governed component execution — **proven**.
5. Durable Datto job reference returned to ChatGPT — **proven**.
6. Read-only terminal Datto job verification — **proven (`completed`)**.
7. `execute_governed_capability` delivered to ChatGPT — **proven**.
8. `direct_provider_access=false` and exact-grant/per-execution approval controls — **preserved**.

## Remaining follow-ups — not blockers to current bounded use

- Add first-class lifecycle/rotation tooling for the dedicated `datto_rmm.execution` secret identity so future rotation does not require rediscovery.
- Reconcile System Registry structured truth when an authoritative governed write/verification route exists.
- Expand Datto execution beyond the exact current pilot only through a separate capability/allowlist/authority decision; do not treat this proof as blanket Datto execution approval.
- Continue documentation-assurance work after Autotask/Datto/IT Glue governed update surfaces are available as planned.

## Read first in future sessions

1. `docs/control/JASON-FUNDAMENTALS.md`
2. this file
3. `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`
4. `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`
5. `docs/operations/Runbook-ChatGPT-Business-Jason-MCP-Pilot.md`
6. current Git and fresh runtime evidence before asserting volatile production state

Conversation memory is context only. It is not authority.
