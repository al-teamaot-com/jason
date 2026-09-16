# Jason Governed Execution Production Checkpoint — 2026-09-16

**Classification:** Evidence / bounded production checkpoint  
**Status:** Current checkpoint for the governed-action pilot  
**Owner:** Jason Architecture Authority / AOT Owner  
**Scope:** ChatGPT Business ↔ Jason MCP governed reads/actions for Autotask and Datto RMM  
**Authority note:** This record preserves evidence and resume state. It does not grant new provider, business, identity, or execution authority.

## Purpose

This record captures the durable state reached after the generic governed-execution MCP work, the cross-thread SQLite repair, live Autotask read/write validation, live Datto RMM read validation, and the first bounded Datto component-execution attempt.

It exists so a future human or AI session can continue without reconstructing the work from chat history. Current volatile runtime facts must still be re-verified when materially relied upon.

## Source and runtime distinction

Current source branch:

`feature/jason-generic-governed-execution-20260915`

Current branch head at this checkpoint:

`cbe0c42ccb16da1acba91d10151a64c360fe214a`

The immediately preceding repaired MCP source was:

`289bdfe957ed6644f6ca25d70f0d558d54478cd3`

The branch head is one commit ahead of that deployed repair. Commit `cbe0c42ccb16da1acba91d10151a64c360fe214a` adds the governed OpenBao logical-secret mapping for `datto_rmm.execution`; it must not be described as deployed merely because it exists in Git.

The most recent production-host inspection recorded the live MCP container as `jason-mcp-pilot` using image `jason-mcp:generic-governed-289bdfe957ed`, sourced from `289bdfe957ed6644f6ca25d70f0d558d54478cd3`. The container remained on the `jason-core` network and preserved the existing public binding. Datto RMM read and execution credential mounts were present without printing secret values.

## Live MCP state observed 2026-09-16

A fresh `jason_mcp_status` call returned:

- `status=ok`;
- `mode=governed-read-plus-actions`;
- `phase=governed-action-pilot`;
- `governed_execution=central-orchestrator`;
- `generic_execution_tool=true`;
- `direct_provider_access=false`;
- `write_tools_enabled=true`;
- active write capabilities:
  - `automation.component.execute`;
  - `service.ticket.note.create`;
  - `service.ticket.update`;
- write authority: `jason_exact_grant_plus_per_execution_approval`.

This is the authoritative live MCP self-report for the checkpoint. It does not mean every client session is currently exposing the generic execution action to ChatGPT.

## Cross-thread MCP repair

The governed read path previously failed before provider data was returned because process-cached runtime stores could be reused by synchronous MCP worker threads while SQLite connections still enforced their creating-thread affinity.

The repair set applied `check_same_thread=False` to the affected long-lived SQLite stores used by:

- durable identity/authority state;
- Teams identity binding state; and
- Central Orchestrator audit/event storage.

The final repair commit was `289bdfe957ed6644f6ca25d70f0d558d54478cd3` (`Fix MCP cross-thread orchestration audit access`).

After deployment of the repaired image, governed Autotask and Datto RMM reads that had previously failed began succeeding through the normal Jason identity/authority/Central-Orchestrator/provider path. No direct-provider bypass was introduced.

`check_same_thread=False` removes SQLite thread affinity; it does not itself provide a high-concurrency serialization design. The current pilot load is bounded. If MCP concurrency materially increases, per-thread connections or explicit synchronization should be evaluated rather than assuming this repair is a complete concurrency architecture.

## Autotask governed read/write proof

### Controlled target

The approved controlled company is **XYZ Test Company**, Autotask company ID `1158`.

The controlled test ticket is:

- ticket number: `T20191013.0001`;
- durable Autotask ticket ID: `8870`;
- title: `test ticket`.

### Governed mutation result

The bounded live Autotask pilot used `service.ticket.update` through Jason governance and changed the reversible ticket priority from `3` to `2`.

The operation remained inside the accepted controls:

- authenticated Jason requester identity;
- exact Jason grant;
- per-execution approval;
- Central Orchestrator execution;
- provider-specific write credential separation;
- no direct provider access;
- no arbitrary provider API surface;
- no due-date mutation;
- post-mutation verification required.

A fresh governed read on 2026-09-16 independently re-read `T20191013.0001` through `service.ticket.search` and returned `priority=2`, confirming the changed value remains durable. That read completed under correlation ID `corr_mcp_355db7371b3d4faa94ab74afe550a017`.

The exact original mutation correlation/audit identifier is intentionally not reconstructed from memory in this document. Jason's durable execution/audit evidence remains authoritative for that event.

### Current Autotask conclusion

Autotask governed reads are working through Jason, and the bounded `service.ticket.update` path has been live-proven with durable readback on the controlled test ticket.

This does not authorize unrestricted Autotask mutation. The active production write surface remains the bounded capabilities advertised by Jason and remains subject to Jason exact grants plus per-execution approval.

## Datto RMM governed read proof

A fresh governed search for hostname `AOT-50282` completed successfully through `endpoint.device.search`.

The exact current match was:

- device UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`;
- hostname: `AOT-50282`;
- site: `Atlantic Office Machines`;
- site UID: `9bb56523-cade-4ffb-bc34-696e788f0f4c`.

The search examined two provider pages across a provider-reported device population of 748 and returned exactly one hostname match. Correlation ID: `corr_mcp_4a13a3929ed4499197809bf55e11ba40`.

A fresh governed component search also confirmed the intended harmless diagnostic component remains present:

- component name: `Get-DNS Settings AOT Ver 06042025-1`;
- provider component UID: `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`;
- category: `scripts`;
- no component variables advertised.

That read completed under correlation ID `corr_mcp_81aa1b4fbcca48a8b94004f40faba7cd`.

The current read path therefore proves that Jason can deterministically resolve both the controlled endpoint and the intended pilot component without direct provider access.

## Datto RMM governed execution attempt

The first bounded governed Datto execution pilot targeted the controlled endpoint/component pair above through `automation.component.execute`.

The provider execution request reached Datto through the governed path but Datto returned HTTP `403`.

The failure classification is provider authorization, not a Jason read-resolution failure:

- the endpoint had been resolved through the governed read identity;
- the component had been resolved through the governed read identity;
- the dedicated Datto execution identity remained separate from `datto_rmm.readonly`;
- exactly one provider execution attempt was made;
- no retry as the read identity or another service identity occurred;
- no direct provider bypass occurred;
- no Datto job was created by the failed attempt.

The exact failed-execution correlation identifier is not reproduced here because it was not retained in this documentation catch-up context. Durable Jason audit evidence is authoritative if that identifier is needed later.

### Current Datto conclusion

Datto RMM governed reads are functional. Jason's governed `automation.component.execute` capability is active at the MCP capability layer, but the first live provider execution is not accepted as successful because Datto rejected the execution identity with HTTP 403.

Before retrying the live component pilot, the Datto execution API identity must have the minimum provider-side authority required for the quick-job operation while preserving the intended containment:

- dedicated execution Security Level / API permissions only;
- bounded Device Visibility for the pilot scope;
- API Component Level containing only explicitly approved component(s);
- no broadening of `datto_rmm.readonly`;
- no addition of unrelated Global Settings or read permissions merely to make proof easier.

A successful retry must still use the same Jason exact-grant + per-execution approval model and must verify resulting job state through the governed read path.

## ChatGPT/Jason action-surface state

The Jason app/action catalog visible in the ChatGPT configuration UI contains five actions, including `Execute governed capability`.

The live MCP image also reports `generic_execution_tool=true`, and source contains the generic governed execution MCP tool.

However, this ChatGPT session currently receives only three callable Jason tools:

- `jason_mcp_status`;
- `discover_capabilities`;
- `execute_read_capability`.

`execute_governed_capability` is therefore currently withheld from this session even though it exists in the configured Jason app catalog and backend MCP surface.

The Jason plugin currently inherits the account-level app permission mode **Allow low-risk actions**. The intended next client-side change is to set **Jason only** to **Allow read actions / ask before writes** (`ask_before_writes`) so reads can run normally while ChatGPT asks before a change. That client permission change must not be confused with Jason's own exact-grant and per-execution approval controls; both layers remain required.

No global ChatGPT app-permission change is required for this workstream.

## Security invariants preserved at this checkpoint

- `direct_provider_access=false`;
- Central Orchestrator remains the governed execution coordinator;
- read and execution/write credentials remain logically separated;
- provider credential material is not released to ChatGPT;
- Datto execution uses the separate `datto_rmm.execution` logical secret path;
- Autotask writes remain bounded to the activated provider-neutral capabilities;
- no arbitrary shell/script text execution interface has been introduced;
- exact grants and per-execution approval remain required for governed writes/actions;
- failed provider authorization does not fall back to a broader service identity;
- no secret values are preserved in this record.

## Documentation impact determination

This checkpoint changes the durable resume state and proves material behavior that was not represented by the September 9/14 narrative records.

Required documentation impact for this checkpoint:

- `docs/control/CURRENT.md` — update required;
- this session/proof record — required;
- dated Autotask and Datto workstream records — mark as historical/superseded for current-state use;
- `docs/operations/Jason-Production-Status-2026-09-14.md` — mark as historical snapshot so it is not read as current production state;
- System Registry — do not invent a lifecycle promotion from narrative evidence. Reconcile structured capability/credential/runtime state separately if the current registry model requires those logical entities or a new verification event.

No constitutional, architectural, or approval-model change is created by this checkpoint. The work uses the already accepted ChatGPT-reasons / Jason-governs-and-executes architecture and the existing identity/authority/approval boundaries.

## Current resume point

At this checkpoint:

1. Autotask governed read: **working**.
2. Autotask bounded governed ticket update: **live-proven**, with current readback confirming priority `2` on `T20191013.0001`.
3. Datto RMM governed read: **working**.
4. Datto RMM governed component execution capability: **active in Jason**, but the first provider execution attempt was **denied by Datto with HTTP 403** and created no job.
5. ChatGPT/Jason client action exposure: **not yet complete in this session** because `execute_governed_capability` is not currently delivered as a callable tool even though it exists in the configured app/backend surface.
6. Direct provider access remains disabled.

## Next safe sequence

1. Complete the documentation reconciliation from this checkpoint.
2. Change the Jason-specific ChatGPT app permission from inherited **Allow low-risk actions** to **Allow read actions / ask before writes** and re-check the delivered action catalog.
3. If `execute_governed_capability` is then callable, do not repeat the already successful Autotask mutation merely for proof. Use readback to preserve the accepted result.
4. Correct the Datto execution identity's minimum provider-side authorization without broadening the read identity or component allowlist.
5. Re-run exactly one separately approved low-risk Datto component execution on the controlled endpoint/component pair.
6. Require governed job/readback verification before calling Datto RMM write/execution operationally accepted.
7. Only after the end-to-end client path and provider execution both succeed should the workstream be declared fully functional for Autotask and Datto RMM governed read/write use.

## Not proven / do not claim

- Do not claim arbitrary Autotask CRUD authority beyond the activated bounded capabilities.
- Do not claim Datto RMM execution success from the HTTP 403 attempt.
- Do not claim `cbe0c42...` is deployed merely because it is the branch head.
- Do not claim the current ChatGPT session exposes `execute_governed_capability` until a fresh delivered tool catalog proves it.
- Do not claim System Registry lifecycle promotion unless the structured registry and its verification evidence are actually updated through the governed registry process.
- Do not describe the documentation catch-up itself as provider authorization or approval for another live mutation.
