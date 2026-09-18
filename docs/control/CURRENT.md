# Project Jason — Current Resume Point

**Updated:** 2026-09-16  
**Status:** The bounded governed-action path for Autotask and Datto RMM through ChatGPT is live-proven. Datto is additionally cross-chat proven for exact target/component resolution, fresh per-execution approval, one-attempt execution, terminal job verification, governed component StdOut retrieval, and current-release Grafana/Prometheus observability. The current Section Goal is complete.  
**Canonical purpose:** Human-readable resume point. Volatile production facts still require fresh runtime evidence before consequential change.

## Continuity control anchors

- **Extension construction control:** `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
- **Last durable success:** preserved in the governed production proof and observability sections below.
- **Production/runtime boundary:** use the recorded boundary below only as durable history; verify volatile production facts before consequential change.
- **Next safe actions:** complete source and CI reconciliation, then perform a fresh production deployment preflight before any production change.


## Durable operating principle

> **ChatGPT reasons. Jason governs and executes.**

ChatGPT is the primary technician conversational surface. Jason remains authoritative for identity, scope, grants, approval policy, provider isolation, Central Orchestrator execution, evidence, and audit. A ChatGPT tool call is a governed request, not provider authority.

## Current live MCP boundary

The production MCP service is `jason-mcp-pilot`.

The currently established live MCP code/image boundary is:

- source commit: `26704f0600bbc6c48c790c9b9ff501a3b5ec3aad`;
- image: `jason-mcp:generic-governed-26704f0600bb`;
- mode: `governed-read-plus-actions`;
- phase: `governed-action-pilot`;
- governed execution: Central Orchestrator;
- generic governed execution tool: enabled;
- `direct_provider_access=false`;
- write tools enabled;
- active write/action capabilities include `automation.component.execute`, `service.ticket.note.create`, and `service.ticket.update`;
- Datto follow-up reads include `automation.job.read` and `automation.job.output.read`;
- write authority: `jason_exact_grant_plus_server_governed_approval_policy`;
- Datto component approval policy: `server_classified_standing_safe_or_per_run`.

Repository documentation/observability commits are newer than the deployed MCP code source. Do not equate branch HEAD with deployed MCP code without fresh runtime evidence.

## Autotask governed proof

The bounded controlled pilot used XYZ Test Company ticket `T20191013.0001` (Autotask ticket ID `8870`). Jason changed the reversible priority from `3` to `2` through `service.ticket.update`, and a later governed read independently confirmed `priority=2`.

This proves the bounded Autotask ticket-update path, not arbitrary Autotask CRUD. Activated capabilities, exact Jason grants, provider authority, and required per-execution approval remain authoritative.

## Datto RMM governed proof — cross-chat execution and output

Controlled target:

- endpoint: `AOT-50282`;
- device UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`;
- site: Atlantic Office Machines.

Controlled diagnostic component:

- `Get-DNS Settings AOT Ver 06042025-1`;
- component UID `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`;
- allowlist `AOT governed diagnostic pilot`;
- variables: none.

The earlier same-day governed execution proof remains valid and is preserved at `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`; its completed job UID was `422d680b-a5ce-4473-b8e8-5d682ec85682`.

The later cross-chat proof deliberately treated the prior approval as consumed. Fresh governed reads resolved the exact endpoint and component. The AOT Owner then explicitly approved exactly one new non-disruptive diagnostic execution.

Jason executed one `automation.component.execute` request, one provider mutation, and one provider attempt. Datto accepted:

- job UID: `741a2d02-587d-4348-9f26-b4982d337732`;
- action correlation: `corr_mcp_action_d49b19600e6f4c50a60f43892af66458`;
- immediate result: `accepted`;
- immediate job state: `active`;
- `readback_verified=true`;
- `completion_verified=false` at action return because the job was asynchronous.

Jason issued no retry or second component execution. It used only `automation.job.read` until the exact job reached terminal `completed`:

- terminal read correlation: `corr_mcp_12eafe5022dc42cb8a42091be669d8cf`.

Jason then retrieved actual component StdOut through `automation.job.output.read`, bound to the exact job UID, device UID, component UID, and `stream=stdout`:

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
- exact Jason grants remain mandatory;
- Datto component approval classification is server-controlled and cannot be supplied or overridden by the caller;
- `standing_safe` is reserved for explicitly classified non-disruptive diagnostics and does not require a separate per-run technician approval;
- `per_run` requires explicit technician approval for the exact execution;
- unknown, missing, or invalid component classification fails closed;
- user-disruptive actions require explicit technician approval for the exact disruptive action.

## Grafana / production observability — current release accepted

The authoritative Grafana/Prometheus source remains repository-provisioned under `infrastructure/showcase`.

The production-health unit now expects the exact live MCP boundary:

- `JASON_EXPECTED_MCP_IMAGE=jason-mcp:generic-governed-26704f0600bb`;
- `JASON_EXPECTED_MCP_SOURCE_REVISION=26704f0600bbc6c48c790c9b9ff501a3b5ec3aad`.

The active Datto production scope contains exactly two server-classified `standing_safe` components:

- `Get-DNS Settings AOT Ver 06042025-1` — `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`;
- `Check Datto EDR/AV Status AOT Ver 12122025-1` — `8cb0f063-5875-452e-88ad-2e1748ed0fd0`.

No reboot component is included in the production component scope.

The latest rollback-protected monitoring-only deployment used repository head `cefa32e9b14db97fb8c6e703ad467a9eda33c32b` and reconciled production observability to the `26704f...` MCP release.

Acceptance returned:

- `PRECHECK=PASS`;
- `SOURCE_VALIDATION=PASS`;
- `PRODUCTION_HEALTH_EXPORTER=PASS`;
- `MONITORING_CONTAINERS=PASS`;
- `CORE_ISOLATION=PASS`;
- `PROMETHEUS_PRODUCTION_HEALTH=UP`;
- `PROMETHEUS_PRODUCTION_RULES=PASS`;
- `GRAFANA_PRODUCTION_HEALTH_DASHBOARD=PASS`;
- `METRIC_CONTRACT=PASS`;
- `RUNTIME_CHANGED=NO`;
- `MCP_CHANGED=NO`;
- `OPENBAO_CHANGED=NO`;
- `PROVIDER_ACCESS=NO`;
- `PROVIDER_WRITES=NO`.

Latest monitoring deployment source: `cefa32e9b14db97fb8c6e703ad467a9eda33c32b`.

Latest monitoring rollback directory: `/tmp/jason-production-health-rollback-20260916T173323Z`.

Production MCP rollback container: `jason-mcp-pilot-rollback-20260916T172806Z`.

Final read-only live metrics returned `1` for:

- `jason_mcp_contract{check="datto_execution_profile"}`;
- `jason_mcp_contract{check="datto_execution_scope"}`;
- `jason_mcp_contract{check="image"}`;
- `jason_mcp_contract{check="source_revision"}`;
- `jason_datto_governed_execution_contract`.

Grafana returned dashboard UID `jason-governed-actions` with title `Jason Governed Actions`.

Monitoring remains observational only. It does not call Datto directly and grants no provider or execution authority.

## System Registry

Narrative proof does not itself promote System Registry lifecycle state. The prior wrap-up found no matching structured resource for this proof state and no governed registry write surface exposed to the ChatGPT session.

No registry state was invented or manually promoted. Reconcile structured truth only through the authoritative governed registry registration/verification path when available.

## Current Section Goal — CLOSED

The requested cross-chat Datto workflow is complete:

1. exact endpoint resolution — **proven**;
2. exact component resolution — **proven**;
3. fresh explicit per-execution approval — **proven and consumed**;
4. one governed diagnostic execution — **proven**;
5. exactly one provider mutation / one attempt / no retry — **proven**;
6. durable Datto job reference — **proven**;
7. terminal completion through governed read-only polling — **proven (`completed`)**;
8. actual component StdOut through `automation.job.output.read` — **proven**;
9. bounded JSON-array provider transport — **live-proven**;
10. `direct_provider_access=false`, Central Orchestrator, exact grants, and the then-required fresh per-execution approval — **preserved in the historical proof**;
11. durable proof/current-state reconciliation — **complete**;
12. Grafana/Prometheus current-release observability — **live and passing**.

## Remaining follow-ups — not blockers

- Add first-class lifecycle/rotation tooling for the dedicated `datto_rmm.execution` secret identity so future rotation does not require rediscovery.
- Reconcile System Registry structured truth when an authoritative governed write/verification route exists.
- Expand Datto execution beyond the exact current pilot only through a separate capability/allowlist/authority decision.
- Establish the exact UID and separately authorize any future disruptive component, such as scheduled reboot, before adding it to production scope.
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
