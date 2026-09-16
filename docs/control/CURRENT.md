# Project Jason — Current Resume Point

**Updated:** 2026-09-16  
**Status:** ChatGPT Business remains the preferred primary technician conversational surface. Jason MCP is now operating in `governed-read-plus-actions` mode with Central Orchestrator execution, direct provider access disabled, Autotask governed read/write live-proven on a controlled test ticket, Datto RMM governed reads working, and Datto governed component execution active at the Jason capability layer but not yet provider-accepted because the first bounded quick-job attempt was denied by Datto with HTTP 403. The immediate client-side blocker is that this ChatGPT session is still being delivered only the three read-oriented Jason tools even though the configured Jason app/backend includes the generic governed execution action.  
**Canonical purpose:** Human-readable resume point. Current production/runtime facts must still be established from current Git, the System Registry, and fresh host/runtime evidence when required.

## Read first

1. `docs/index.md`
2. `docs/control/JASON-FUNDAMENTALS.md`
3. this file
4. `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`
5. `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`
6. `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`
7. `docs/engineering/interfaces/Jason-MCP-Construction-Guide.md`
8. `docs/operations/Runbook-ChatGPT-Business-Jason-MCP-Pilot.md`
9. `docs/operations/Autotask-Governed-CRUD-Pilot-2026-09-14.md`
10. `docs/operations/Jason-Datto-RMM-Component-Execution-Workstream-2026-09-14.md`
11. `docs/operations/System-Registry-Current-Operational-State.md`
12. `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
13. `docs/control/DOCUMENTATION-REGISTER.md`
14. current Git and fresh host/runtime evidence before asserting volatile production state

Conversation memory is context only. It is not authority.

## Active architecture

```text
Technician
    ↓
ChatGPT Business session
    ↓
ChatGPT conversation / reasoning / session context
    ↓
Jason governed MCP/tool service
    ↓
Jason identity / scope / authority / policy / approvals / audit
    ↓
Central Orchestrator
    ↓
Governed capabilities / connectors
    ↓
Approved providers
```

Durable principle:

> **ChatGPT reasons. Jason governs and executes.**

A ChatGPT tool request is a request for governed execution, not authority.

## Production/runtime boundary

### Current production checkpoint

The authoritative bounded checkpoint is `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`.

The current source workstream is `feature/jason-generic-governed-execution-20260915`.

The most recent production-host inspection recorded the live MCP as `jason-mcp-pilot` on image `jason-mcp:generic-governed-289bdfe957ed`, sourced from `289bdfe957ed6644f6ca25d70f0d558d54478cd3`.

The source branch subsequently advanced by one non-deployed code commit, `cbe0c42ccb16da1acba91d10151a64c360fe214a`, adding the OpenBao logical-secret mapping for `datto_rmm.execution`. Do not describe that commit as deployed merely because it is in Git.

A fresh live MCP status check on 2026-09-16 reported:

- mode: `governed-read-plus-actions`;
- phase: `governed-action-pilot`;
- governed execution: `central-orchestrator`;
- generic execution tool: enabled in the backend;
- direct provider access: disabled;
- write tools: enabled;
- active write capabilities:
  - `automation.component.execute`;
  - `service.ticket.note.create`;
  - `service.ticket.update`;
- write authority: `jason_exact_grant_plus_per_execution_approval`.

This backend capability state does not itself prove that every ChatGPT client session is currently receiving the generic execution tool.

## Last durable successes

### MCP governed read-path repair

The process-cached MCP runtime could reuse SQLite-backed identity/authority and orchestration stores from synchronous worker threads. Default SQLite thread affinity caused governed reads to fail before provider results were returned.

The repaired source sets `check_same_thread=False` on the affected long-lived SQLite stores. After deployment, governed Autotask and Datto RMM reads that had been failing began completing through Jason's normal identity/authority/Central-Orchestrator/provider path.

The final repair commit was `289bdfe957ed6644f6ca25d70f0d558d54478cd3`.

This is a bounded thread-affinity repair, not a general high-concurrency serialization design.

### Autotask governed read/write

The controlled company remains **XYZ Test Company**, company ID `1158`.

The controlled ticket is `T20191013.0001` (Autotask ticket ID `8870`, title `test ticket`).

The bounded governed pilot successfully changed its priority from `3` to `2` through `service.ticket.update` under Jason exact-grant + per-execution approval controls.

A fresh governed `service.ticket.search` on 2026-09-16 independently confirmed `priority=2`, proving the changed value remains durable.

Autotask governed read and the bounded ticket-update path are therefore live-proven. This does not authorize arbitrary provider CRUD beyond Jason's activated capability surface.

### Datto RMM governed read

A fresh governed endpoint search on 2026-09-16 resolved exactly one endpoint for `AOT-50282` at site `Atlantic Office Machines`.

A fresh governed component search confirmed the intended harmless pilot component `Get-DNS Settings AOT Ver 06042025-1` with provider component UID `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`.

Datto RMM governed endpoint/component reads are therefore working through Jason without direct provider access.

### Datto RMM governed execution attempt

The first bounded `automation.component.execute` pilot reached Datto through the governed path, but Datto returned HTTP 403. Exactly one provider execution attempt was made, no broader credential fallback occurred, and no Datto job was created.

The current blocker is provider-side authorization for the dedicated execution identity. Correct that identity's minimum quick-job authority while preserving the intended Device Visibility and API Component Level containment. Do not broaden `datto_rmm.readonly` and do not add unrelated read/global permissions merely to make the proof easier.

A successful retry still requires Jason exact grant, per-execution approval, and governed job/readback verification before Datto execution is accepted as operational.

## Current ChatGPT/Jason client blocker

The configured Jason app action catalog contains the generic governed execution action, and the MCP backend reports `generic_execution_tool=true`.

However, the current ChatGPT session is still being delivered only:

- `jason_mcp_status`;
- `discover_capabilities`;
- `execute_read_capability`.

`execute_governed_capability` is therefore not currently callable from this session.

The Jason app currently inherits the account-level **Allow low-risk actions** permission mode. The next client-side change is to set **Jason only** to **Allow read actions / ask before writes** (`ask_before_writes`), then reload/re-check the delivered Jason tool catalog.

That ChatGPT-side permission setting is not Jason authorization. Jason exact grants and per-execution approval remain mandatory for provider writes/actions.

Do not change the global ChatGPT app-permission setting for this workstream.

## Security boundary that must remain unchanged

- `direct_provider_access=false`.
- Central Orchestrator remains the governed execution coordinator.
- Provider credentials remain isolated and are never released to ChatGPT.
- Read and write/execution credentials remain separate.
- Autotask writes remain bounded to activated provider-neutral capabilities.
- Datto execution remains bounded to approved component/target policy rather than arbitrary script text.
- Missing/failed authority fails closed.
- Failed provider authorization does not retry as a broader identity.
- Provider writes/actions require Jason exact grant plus per-execution approval.

## System Registry state

The generated System Registry human view still reflects the earlier verified topology/lifecycle baseline and must not be manually rewritten to imply new logical capability lifecycle states.

The 2026-09-16 checkpoint is the durable narrative/proof record for the new governed-action state. A separate governed System Registry reconciliation is required if the registry model should add or transition the new Autotask/Datto execution capabilities, credential reference, or deployment verification evidence.

Until that structured reconciliation is performed, do not claim a System Registry lifecycle promotion merely from the narrative checkpoint.

## Historical records now superseded for current-state use

The following dated records remain valuable evidence but must not be treated as the current resume point:

- `docs/operations/Jason-Production-Status-2026-09-14.md`;
- `docs/operations/Autotask-Governed-CRUD-Pilot-2026-09-14.md`;
- `docs/operations/Jason-Datto-RMM-Component-Execution-Workstream-2026-09-14.md`.

They preserve the state and decisions that existed when written. Current state is owned by this file plus the 2026-09-16 checkpoint and fresh runtime evidence.

## Current workstream

The active workstream is **complete the governed-action usability path for Autotask and Datto RMM through ChatGPT without weakening Jason governance**.

The target stopping condition remains:

1. Autotask governed read works — **proven**.
2. Autotask governed write works with readback — **proven for bounded ticket update**.
3. Datto RMM governed read works — **proven**.
4. Datto RMM governed component execution succeeds with job/readback verification — **not yet proven; provider HTTP 403 is the blocker**.
5. `execute_governed_capability` is actually exposed to the ChatGPT session — **not yet true in this session**.
6. `direct_provider_access=false` and Jason exact-grant/per-execution approval controls remain intact — **currently true**.

Do not call the workstream fully functional until items 4 and 5 are also proven through the intended client/runtime/provider path.

## Next safe actions

1. Keep the 2026-09-16 documentation checkpoint durable and do not use the September 9 read-only resume point as current guidance.
2. Change the Jason-specific ChatGPT permission mode to **Allow read actions / ask before writes** and re-check the delivered action catalog.
3. If the generic governed execution tool becomes callable, preserve the already accepted Autotask result rather than repeating a mutation only for proof.
4. Correct the Datto execution identity's minimum provider-side authorization while preserving the bounded Device Visibility/API Component Level design.
5. Execute exactly one separately approved low-risk Datto diagnostic component on the controlled endpoint.
6. Require governed post-job/readback verification.
7. Reconcile System Registry structured truth only through its governed registration/verification process; do not manually promote lifecycle state from narrative evidence.
8. Once the ChatGPT action surface and Datto provider execution both succeed, update this file and the 2026-09-16 checkpoint before declaring the workstream operationally complete.

## Do not rediscover

1. ChatGPT Business owns ordinary conversational reasoning for the primary technician path.
2. Jason owns identity, authority, scope, policy, approvals, orchestration, provider boundaries, evidence, audit, and deterministic execution.
3. Provider credentials are execution mechanisms, not requester authority.
4. New provider capability should expand governed capability/resource surfaces rather than create phrase-specific question logic.
5. A successful provider page is not automatically a complete collection; bounded complete pagination matters.
6. Provider-native IDs are implementation evidence, not automatically user-relevant output.
7. System Registry lifecycle must not be promoted without its declared verification process.
8. Conversation memory is never the final operational record.
