# Project Jason — Current Resume Point

**Updated:** 2026-09-16  
**Status:** The bounded governed-action path for Autotask and Datto RMM through ChatGPT is live-proven. Datto is additionally cross-chat proven for fresh approval, single-attempt execution, terminal job verification, and governed component StdOut retrieval. Monitoring reconciliation for the current `e9c7a763...` MCP release is prepared in source and requires the existing monitoring-only deployment/verification before the observability portion of the current Section Goal is fully closed.  
**Canonical purpose:** Human-readable resume point. Volatile production facts still require fresh runtime evidence before consequential change.

## Durable operating principle

> **ChatGPT reasons. Jason governs and executes.**

ChatGPT is the primary technician conversational surface. Jason remains authoritative for identity, scope, grants, approval policy, provider isolation, Central Orchestrator execution, evidence, and audit. A ChatGPT tool call is a governed request, not provider authority.

## Current live MCP boundary

The production MCP service is `jason-mcp-pilot`.

The currently established live MCP code/image boundary is:

- source commit: `e9c7a76318aa12b150194875726b1ba54bf6d61b`;
- source message: `Accept bounded JSON arrays from provider reads`;
- image: `jason-mcp:generic-governed-e9c7a76318aa`;
- mode: `governed-read-plus-actions`;
- phase: `governed-action-pilot`;
- governed execution: Central Orchestrator;
- generic governed execution tool: enabled;
- `direct_provider_access=false`;
- write tools enabled;
- active write/action capabilities include `automation.component.execute`, `service.ticket.note.create`, and `service.ticket.update`;
- Datto follow-up reads include `automation.job.read` and `automation.job.output.read`;
- write authority: `jason_exact_grant_plus_per_execution_approval`.

Repository documentation/observability commits are newer than the deployed MCP code source. Do not equate branch HEAD with deployed MCP code without fresh runtime evidence.

## Autotask governed proof

The bounded controlled pilot used XYZ Test Company ticket `T20191013.0001` (Autotask ticket ID `8870`). Jason changed the reversible priority from `3` to `2` through `service.ticket.update`, and a later governed read independently confirmed `priority=2`.

This proves the bounded Autotask ticket-update path, not arbitrary Autotask CRUD. Activated capabilities, exact Jason grants, provider authority, and required per-execution approval remain authoritative.

## Datto RMM governed proof — execution and output

Governed Datto reads are working. The controlled endpoint is `AOT-50282` with device UID `69571572-83f7-1e33-9cdf-01717d4e74a4` at Atlantic Office Machines.

The controlled diagnostic component is `Get-DNS Settings AOT Ver 06042025-1`, component UID `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`, under allowlist `AOT governed diagnostic pilot`, with no variables.

The earlier same-day governed execution proof remains valid and is preserved at `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`; its completed job UID was `422d680b-a5ce-4473-b8e8-5d682ec85682`.

The later cross-chat proof deliberately treated the earlier execution approval as consumed. Fresh governed reads uniquely resolved the endpoint and component, and the AOT Owner then explicitly approved exactly one new non-disruptive diagnostic execution.

Jason executed one `automation.component.execute` request, one provider mutation, and one provider attempt. The provider accepted Datto job:

- job UID: `741a2d02-587d-4348-9f26-b4982d337732`;
- action correlation: `corr_mcp_action_d49b19600e6f4c50a60f43892af66458`;
- immediate result: `accepted`;
- immediate job state: `active`;
- `readback_verified=true`;
- `completion_verified=false` at action return because the job was asynchronous.

Jason issued no retry or second component execution. It used only `automation.job.read` until the same job reached terminal state `completed`:

- terminal read correlation: `corr_mcp_12eafe5022dc42cb8a42091be669d8cf`.

Jason then retrieved the actual component output through `automation.job.output.read`, bound to the exact job UID, device UID, component UID, and `stream=stdout`:

- output-read correlation: `corr_mcp_2c624f2cda234afab3be73b70906e8b0`;
- output matches: `1`;
- truncated: `false`.

The returned diagnostic data included:

- ZeroTier `192.168.193.90`;
- ZeroTier `10.148.127.90`;
- `vEthernet (NDA-External-VS)` `192.168.12.33`;
- gateway `192.168.12.1`;
- DNS `103.247.36.36`, `103.247.37.37`, `8.8.8.8`;
- Hyper-V Default Switch `172.23.176.1`.

The provider output endpoint returns a JSON array. Successful live output retrieval on `e9c7a763...` proves the bounded JSON-array transport fix is active and the previous `PROVIDER_TRANSPORT_FAILURE` is not present in this workflow.

Authoritative cross-chat/output proof: `docs/sessions/Jason-Datto-RMM-Cross-Chat-Output-Proof-2026-09-16.md`.

## Datto asynchronous execution rule

An approved Datto quick job may legitimately return `status=accepted`, `job_status=active`, `readback_verified=true`, `completion_verified=false`, and a durable `job_uid`. That is accepted asynchronous execution, not failure.

Do not issue a second provider mutation because the first job is still active. Use the returned `job_uid` with read-only `automation.job.read` until terminal state. If actual component output is required, retrieve it afterward through `automation.job.output.read` using the exact job UID, target device UID, component UID, and requested stream.

## Security boundary that remains mandatory

- `direct_provider_access=false`;
- Central Orchestrator remains the governed execution coordinator;
- provider credentials are never released to ChatGPT;
- read and write/execution identities remain separated where required;
- Datto execution remains bounded to approved component/target policy rather than arbitrary script text;
- failed authority/provider checks fail closed;
- provider actions do not retry through a broader credential;
- exact Jason grants and required per-execution approval remain mandatory;
- a consumed execution approval must not be reused;
- user-disruptive actions require explicit technician approval for the exact disruptive action.

## System Registry

Narrative proof does not itself promote System Registry lifecycle state. The prior wrap-up found no matching structured resource for this proof state and no governed registry write surface exposed to the ChatGPT session.

Therefore no registry state is being invented or manually promoted. Reconcile structured truth only through the authoritative governed registry registration/verification path when available.

## Grafana / production observability

The authoritative Grafana/Prometheus source is repository-provisioned under `infrastructure/showcase`, with monitoring deployment handled by `infrastructure/showcase/deploy_production_health_dashboard.sh`.

The existing `Jason Governed Actions` dashboard and `jason_datto_governed_execution_contract` remain the correct observability surface. The prior monitoring acceptance was live and passing for the earlier `8f1e864...` MCP release.

Because the live MCP has since advanced to `e9c7a763...`, the production-health image/source expectation required reconciliation. Source now pins the observability exporter unit to:

- `JASON_EXPECTED_MCP_IMAGE=jason-mcp:generic-governed-e9c7a76318aa`;
- `JASON_EXPECTED_MCP_SOURCE_REVISION=e9c7a76318aa12b150194875726b1ba54bf6d61b`.

This is an observability-only expectation update. It does not broaden action authority, provider identities, allowlists, targets, or execution scope and does not require an MCP restart/recreation.

The existing rollback-protected monitoring-only deployment must now be run and accepted before claiming the current `e9c7...` observability state is live/passing. The deployment contract must continue to report no changes to Jason runtime, MCP, OpenBao, or provider access/writes.

## Current Section Goal status

The requested cross-chat Datto workflow is complete through provider execution/output:

1. exact endpoint resolution — **proven**;
2. exact component resolution — **proven**;
3. fresh explicit per-execution approval — **proven and consumed**;
4. one governed diagnostic execution — **proven**;
5. exactly one provider mutation / one attempt / no retry — **proven**;
6. durable Datto job reference — **proven**;
7. terminal completion through governed read-only polling — **proven (`completed`)**;
8. actual component StdOut through `automation.job.output.read` — **proven**;
9. bounded JSON-array provider transport — **live-proven**;
10. `direct_provider_access=false`, Central Orchestrator, exact grants, and per-execution approval — **preserved**;
11. durable proof/runbook reconciliation — **complete in source**;
12. Grafana/Prometheus expectation reconciliation — **prepared in source; live monitoring-only deployment verification pending**.

## Remaining follow-ups — not provider blockers

- Run and verify the existing rollback-protected monitoring-only deployment for the current `e9c7...` observability expectation.
- Add first-class lifecycle/rotation tooling for the dedicated `datto_rmm.execution` secret identity so future rotation does not require rediscovery.
- Reconcile System Registry structured truth when an authoritative governed write/verification route exists.
- Normalize stale MCP source-revision environment metadata during a future controlled MCP recreation only if it remains stale; do not recreate MCP solely for cosmetic cleanup.
- Expand Datto execution beyond the exact current pilot only through a separate capability/allowlist/authority decision.
- Continue documentation-assurance work after Autotask/Datto/IT Glue governed update surfaces are available as planned.

## Read first in future sessions

1. `docs/control/JASON-FUNDAMENTALS.md`
2. this file
3. `docs/sessions/Jason-Datto-RMM-Cross-Chat-Output-Proof-2026-09-16.md`
4. `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`
5. `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`
6. `docs/operations/Runbook-ChatGPT-Business-Jason-MCP-Pilot.md`
7. current Git and fresh runtime evidence before asserting volatile production state

Conversation memory is context only. It is not authority.
