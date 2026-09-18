# Jason Governed Execution Production Checkpoint — 2026-09-16

**Classification:** Evidence / bounded production checkpoint  
**Status:** Resolved / superseded by final Datto proof for current-state use  
**Owner:** Jason Architecture Authority / AOT Owner  
**Scope:** ChatGPT Business ↔ Jason MCP governed reads/actions for Autotask and Datto RMM  
**Authority note:** This record preserves sequence and evidence. It grants no new provider, business, identity, or execution authority.

## Current resolution

This checkpoint originally captured an intermediate state in which the first bounded Datto RMM component-execution attempt reached Datto but was rejected with HTTP 403 and the current ChatGPT session had not yet received the generic governed execution tool.

Both conditions were subsequently resolved on 2026-09-16.

The current authoritative resume point is `docs/control/CURRENT.md`. The final Datto end-to-end proof is `docs/sessions/Jason-Datto-RMM-Governed-Execution-Proof-2026-09-16.md`.

## Final live MCP boundary

The code source deployed for the completed proof is:

- branch: `feature/jason-generic-governed-execution-20260915`;
- deployed code commit: `8f1e864947a2e6e79bf47d3de14daacde7d73144`;
- commit message: `Expose governed Datto job reference for readback`;
- image: `jason-mcp:generic-governed-8f1e864947a2`;
- image ID: `sha256:d709ca54b66d41e22bd1f67782cd5f6d681c4337bffb359b632523762a27788a`.

The immediately previous live MCP was preserved as a rollback container during cutover.

Post-deployment MCP self-report remained:

- `status=ok`;
- `mode=governed-read-plus-actions`;
- `phase=governed-action-pilot`;
- `governed_execution=central-orchestrator`;
- `generic_execution_tool=true`;
- `direct_provider_access=false`;
- `write_tools_enabled=true`;
- active actions: `automation.component.execute`, `service.ticket.note.create`, `service.ticket.update`;
- write authority: `jason_exact_grant_plus_per_execution_approval`.

The generic `execute_governed_capability` tool was delivered to this ChatGPT session and used successfully. The earlier client-delivery blocker is therefore historical.

## Autotask bounded proof

The controlled target remained XYZ Test Company ticket `T20191013.0001` (Autotask ticket ID `8870`). The bounded `service.ticket.update` pilot changed priority from `3` to `2`, and a later governed read independently confirmed the durable value `priority=2`.

Autotask governed reads and the bounded ticket-update path are live-proven. This does not authorize arbitrary Autotask CRUD.

## Datto read proof

Governed `endpoint.device.search` resolved the controlled endpoint:

- hostname: `AOT-50282`;
- device UID: `69571572-83f7-1e33-9cdf-01717d4e74a4`;
- site: Atlantic Office Machines;
- site UID: `9bb56523-cade-4ffb-bc34-696e788f0f4c`.

The controlled diagnostic component remained:

- `Get-DNS Settings AOT Ver 06042025-1`;
- component UID `afb858ae-e0d5-4c7b-b0da-8617a22b60d4`;
- allowlist `AOT governed diagnostic pilot`;
- no variables for the proof execution.

## Historical 403 stage

The first bounded execution attempt was rejected by Datto with HTTP 403. That event proved the Jason path failed closed: one provider attempt, no retry through a broader identity, no direct provider bypass, and no created job.

The dedicated execution identity was then corrected to the required bounded provider authority without broadening the read identity or arbitrary component scope. The HTTP 403 is no longer a current blocker.

## Asynchronous verification correction

A later provider-side execution showed that Datto quick jobs can remain active beyond the original synchronous verification window. Jason was corrected so a quick job that has been durably created and read back is returned as accepted when still asynchronous rather than falsely classified as failure.

The MCP action projection was also corrected so bounded non-secret `job_uid` and `completion_verified` fields are returned to ChatGPT. That allows the already-active read-only `automation.job.read` capability to complete terminal verification without another mutation.

The projection correction is commit `8f1e864947a2e6e79bf47d3de14daacde7d73144`.

## Final explicitly approved Datto execution

The AOT Owner explicitly approved one execution of `Get-DNS Settings AOT Ver 06042025-1` on `AOT-50282`.

Jason executed exactly one `automation.component.execute` request through the governed generic action surface.

Immediate action result:

- provider: `datto_rmm_component_execution`;
- provider attempts: `1`;
- result status: `accepted`;
- immediate job status: `active`;
- `readback_verified=true`;
- `completion_verified=false` because the provider job was asynchronous;
- durable job UID: `422d680b-a5ce-4473-b8e8-5d682ec85682`;
- action correlation: `corr_mcp_action_a1405f1b1c604ab7b92c88032c02ed1b`.

No reboot, forced logoff, process termination, network interruption, or other disruptive action was requested.

## Final governed terminal verification

Jason then used only read-only `automation.job.read` calls against the returned job UID. No second component execution occurred.

The final read returned:

- job UID: `422d680b-a5ce-4473-b8e8-5d682ec85682`;
- job name: `Jason - Get-DNS Settings AOT Ver 06042025-1`;
- terminal status: `completed`;
- final read correlation: `corr_mcp_25120cdec51d4dbaa837bb6f9bb43b60`.

This completes the bounded Datto RMM governed execution proof.

## Preserved security invariants

- `direct_provider_access=false`;
- Central Orchestrator remains authoritative;
- provider credentials remain isolated from ChatGPT;
- Datto execution uses a separate bounded execution identity;
- exact Jason grants plus required per-execution approval remain mandatory;
- no arbitrary shell/script-text execution surface was introduced;
- one provider mutation / one attempt was used for the final proof;
- asynchronous status was verified through read-only governed job reads;
- provider failure does not trigger broader-credential fallback;
- user-disruptive actions remain prohibited without explicit approval for the exact disruptive action.

## System Registry treatment

Narrative proof is not a lifecycle promotion. During final wrap-up, governed System Registry search returned no matching structured resource for this specific proof state and no governed registry write surface was exposed to this session.

No registry state was invented or manually promoted. Structured reconciliation remains a follow-up for the authoritative registry workflow.

## Production observability follow-up

Repository inspection identified the authoritative Grafana/Prometheus production-health stack under `infrastructure/showcase`. The final wrap-up updates that monitoring contract to the current MCP release and adds secret-safe visibility for the bounded Datto governed-execution configuration. Monitoring remains observational and does not directly call providers or grant authority.

## Final checkpoint conclusion

The governed-action usability workstream reached its bounded stopping condition on 2026-09-16:

1. Autotask governed read — proven.
2. Autotask bounded governed write with durable readback — proven.
3. Datto governed read — proven.
4. Datto bounded governed component execution — proven.
5. Durable job UID returned through the MCP action surface — proven.
6. Terminal completion through read-only `automation.job.read` — proven.
7. Generic governed execution tool delivered to ChatGPT — proven.
8. Direct-provider bypass remained disabled — proven.

Future expansion must be separately governed; this proof is not blanket Datto or Autotask mutation authority.
