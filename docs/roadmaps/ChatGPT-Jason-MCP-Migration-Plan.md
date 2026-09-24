# ChatGPT Business + Jason MCP Migration Plan

**Status:** Active migration roadmap  
**Date:** 2026-09-08  
**Last reconciled:** 2026-09-16  
**Owner:** Jason Architecture Authority  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`  
**Target architecture:** `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`  
**Current checkpoint:** `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md`

## Objective

Move the primary technician experience from a custom Teams/Jason conversational stack toward **ChatGPT Business as the primary conversational surface with Jason exposed as a governed MCP/tool service**, while preserving all constitutional identity, authority, policy, approval, evidence, audit, provider, and Central Orchestrator boundaries.

## Execution status — 2026-09-16

The roadmap has advanced beyond the original read-only proving phase.

Durable current state:

- **MCP-001 — complete.** ChatGPT Business + Jason read-only MCP foundation is source-durable, authenticated, and live-proven.
- **MCP-002 — partially complete / residual isolation evidence remains.** Positive ChatGPT/Entra identity binding is proven. Some durable negative/isolation proof remains useful, but the read foundation is no longer the only active workstream.
- **MCP-003 — partially proven.** Multiple governed providers are usable from ChatGPT, including Autotask and Datto RMM reads. Formal cross-provider technician acceptance remains broader than the current action pilot.
- **MCP-004 — planned.** Legacy conversational-stack simplification remains deferred until replacement capability is sufficiently proven.
- **P7 governed actions — active.** The generic governed-action surface exists in Jason. Autotask bounded ticket update has been live-proven with readback. Datto RMM component execution is active at the Jason capability layer, but its first bounded provider attempt was denied by Datto with HTTP 403 and created no job.
- **Client action delivery — current blocker.** The configured Jason app/backend includes the generic governed execution action, but the current ChatGPT session is still delivered only the three read-oriented tools. Jason-specific app permission/cached action delivery must be corrected and re-verified without weakening Jason authorization.

Current production/backend self-report includes:

- `mode=governed-read-plus-actions`;
- `governed_execution=central-orchestrator`;
- `direct_provider_access=false`;
- `write_tools_enabled=true`;
- write/action capabilities:
  - `automation.component.execute`;
  - `service.ticket.note.create`;
  - `service.ticket.update`;
- write authority: `jason_exact_grant_plus_per_execution_approval`.

Current status is owned by `docs/control/CURRENT.md` and the 2026-09-16 checkpoint. Older phase checklists remain useful historical design context but must not override fresh runtime evidence.

## Guiding constraints

- Do not destroy the working Teams path during migration.
- Do not route ChatGPT directly to provider credentials or unrestricted provider APIs.
- Do not implement question-specific handlers.
- Do not duplicate ChatGPT reasoning with a second Jason-side model by default.
- Read-first proof remains the foundation; governed actions may be added only through the normal identity/authority/policy/approval path.
- ChatGPT app access or client confirmation never substitutes for Jason authority.
- Do not call an action operationally accepted until provider result and required readback/job verification succeed.
- Do not call the MCP path operationally complete until the actual client-delivered tool surface matches the approved backend profile.
- Preserve rollback at every material stage.

## P0 — Architecture and documentation freeze

**Status:** Foundation complete; legacy simplification remains deferred

- [x] Accept ChatGPT Business + Jason MCP as preferred primary conversational architecture.
- [x] Preserve constitutional boundary: ChatGPT reasons; Jason governs/executes.
- [x] Define Teams as secondary/fallback rather than preferred full conversational surface.
- [x] Define OpenClaw as optional/secondary infrastructure rather than primary brain.
- [x] Define duplicate OpenAI API reasoning as exception, not default.
- [x] Stop adding non-critical complexity to the legacy custom conversational state-machine path as the preferred architecture.
- [x] Capture production state before material topology/action-surface changes.

## P1 — MCP foundation

**Status:** Complete as MCP-001

**Goal:** A minimal Jason MCP service backed by existing governed capabilities.

- [x] Select/confirm supported MCP transport for ChatGPT Business custom app connectivity.
- [x] Define MCP server component contract.
- [x] Define MCP service registration in System Registry.
- [x] Implement health/readiness/service verification.
- [x] Expose capability-derived model-friendly read tools.
- [x] Map MCP tool calls to Central Orchestrator execution.
- [x] Prohibit direct connector/provider invocation from MCP layer.
- [x] Preserve capability/resource names and provider neutrality.
- [x] Return structured provenance-bearing results.
- [x] Implement bounded errors/fail-closed responses.
- [x] Add deterministic tests proving no secret/provider bypass.

### Read-only foundation surface

The accepted original read-only MCP surface was:

- `jason_mcp_status`
- `discover_capabilities`
- `execute_read_capability`

That foundation remains valid. The action pilot adds a separate generic governed execution entry point; it does not redefine the read tools as write-capable.

## P2 — Identity and workspace binding

**Status:** Positive path proven; residual negative/isolation evidence remains

**Goal:** A ChatGPT Business user invoking Jason is bound to a Jason principal before execution.

- [x] Determine supported ChatGPT custom MCP/app authentication mechanism for the AOT workspace.
- [x] Establish workspace/app trust configuration.
- [x] Map the proven authenticated user identity to a Jason principal.
- [x] Use the AOT Microsoft Entra tenant as the initial authentication boundary.
- [x] Preserve capability-specific authorization independently of app access.
- [x] Preserve organization/client scope in governed execution.
- [x] Define operational disable/rollback paths for the MCP service/app.
- [ ] Preserve additional durable negative/isolation proof for unknown/unbound identity, invalid tenant/workspace context, missing authority, and cross-client attempts where safely testable.

The residual evidence item must not be used as justification to bypass identity/authority controls for actions. Actions still require the same authenticated principal plus exact capability authority.

## P3 — ChatGPT Business pilot publication

**Status:** Read path proven; action delivery still being completed

**Goal:** Approved AOT technicians can use Jason from their normal ChatGPT Business workspace.

- [x] Create/configure custom Jason MCP app in ChatGPT Business.
- [x] Publish/enable it in the AOT workspace for the read pilot.
- [x] Confirm workspace visibility/access behavior for the proven pilot identity.
- [x] Prove a normal read request end to end.
- [x] Prove ordinary follow-up use within the ChatGPT session without Jason duplicating full chat memory.
- [x] Prove governed tool discovery and repeated tool invocation from ChatGPT.
- [x] Prove representative operational reads without question-specific MCP tools.
- [x] Prove exact collection-wide answers where complete governed provider evidence exists.
- [x] Configure the Jason app/backend with the generic governed execution action.
- [ ] Ensure `execute_governed_capability` is actually delivered to the current ChatGPT session under the intended Jason-specific app permission mode.
- [ ] Complete formal cross-provider technician acceptance beyond the current bounded provider tests.

## P4 — Cost optimization

**Status:** Observability foundation deployed; further policy refinement remains

**Goal:** Maximize value from existing ChatGPT Business seats and minimize duplicate API spend.

- [x] Measure Jason-side model/provider usage independently from ChatGPT subscription usage.
- [x] Establish visibility showing zero additional hosted-model usage when ordinary governed operations do not require it.
- [ ] Keep provider-doc/schema refresh out of per-turn model cost where possible.
- [ ] Cache stable provider documentation/schema/indexes where appropriate.
- [x] Keep pagination/count/filter/group operations deterministic where implemented.
- [ ] Define the complete set of explicit capabilities permitted to invoke Jason-side models.
- [ ] Maintain least-cost/default and escalation policy for any future governed Jason-side model use.
- [x] Add capability/provider/task-oriented usage telemetry foundations.
- [x] Add actor/source attribution telemetry foundations.
- [ ] Add optional per-tech/per-day/per-client soft/hard budget policy where useful.

## P5 — Provider expansion

**Status:** Multiple governed provider read surfaces are live; action surfaces remain provider-by-provider

**Goal:** Adding providers expands Jason's observable/action world without retraining conversational logic.

Current high-value provider state:

- Datto RMM — governed endpoint/site/component reads working; bounded component execution capability active in Jason but provider execution acceptance incomplete.
- Autotask — governed ticket/company/service-management reads working; bounded ticket update live-proven; ticket-note create capability active.
- Microsoft 365 / Graph — governed user reads available where authorized; broader tenant resource families remain future work.
- IT Glue — governed documentation/configuration reads available where authorized.

For each provider/capability family:

- [ ] capability/resource manifest current;
- [ ] governed credentials and secret separation appropriate to risk;
- [ ] documentation/schema source where useful;
- [ ] pagination/completeness behavior;
- [ ] deterministic collection analysis support;
- [ ] provenance/audit;
- [ ] client/tenant isolation;
- [ ] generic MCP exposure from capability metadata;
- [ ] unseen-question test;
- [ ] action-specific exact grant/approval/idempotency/readback where applicable;
- [ ] retirement/replacement criteria.

## P6 — Cross-provider technician workflows

**Status:** Provider access exists; formal technician workflow acceptance remains

**Goal:** ChatGPT composes Jason tools naturally rather than Jason encoding bespoke workflows.

Proving scenarios should include:

- endpoint state + related Autotask ticket context;
- Microsoft 365 user + endpoint association + security alert context;
- client/site comparison across management and PSA data;
- exact fleet counts/filtering by arbitrary provider-observed facts;
- follow-up questions using the same ChatGPT session context.

No scenario should require phrase-specific code.

## P7 — Governed actions

**Status:** Active; Autotask bounded update proven, Datto execution provider-blocked

**Goal:** Add carefully selected consequential tools without weakening the read foundation or governance model.

Prerequisites/controls:

- stable authenticated identity binding;
- client/resource scope;
- explicit exact action authority;
- risk classification;
- policy/preconditions;
- per-execution approval where required;
- idempotency/request digest semantics where applicable;
- separate execution/write credential when risk requires it;
- audit/evidence;
- provider result classification;
- durable-state/job readback;
- rollback/recovery where applicable;
- human-visible confirmation semantics where appropriate.

### Generic action entry point

The preferred model-facing pattern is `execute_governed_capability`, not provider-specific unrestricted write tools.

Backend registration, Jason capability activation, ChatGPT app catalog configuration, and actual session tool delivery are separate states and must each be verified.

### Autotask current acceptance

The bounded ticket-update path is live-proven under execution-plan binding and direct-update canonicalization.

Latest production acceptance (2026-09-24):

- ticket: `T20260905.0004` / Autotask ID `139815` / OWNI7JAN25;
- technician-friendly request: `ticket_id=139815`, `status=Complete`;
- canonical provider payload before authorization: `{"id":139815,"status":5}`;
- symbolic resolution: `Complete -> 5` through authoritative Autotask picklist metadata;
- provider: `autotask_ticket_update` / `autotask.ticket.update`;
- provider attempts: exactly one;
- execution-plan re-prepare: exact fingerprint match required before provider invocation;
- built-in post-write readback: verified;
- independent governed post-read: status `5` / Complete;
- direct provider access: disabled.

The generic MCP boundary now reconciles exact `ticket_id` / `ticketID` / `id` selectors, confirms the authoritative positive numeric Autotask ID through governed read, retains only explicitly requested allowed mutable fields, and fails closed on ambiguous identity or symbolic resolution before approval/execution-plan binding.

Status: **direct technician-friendly ticket updates production-proven under canonical intent + execution-plan binding**.

Do not treat this as unrestricted Autotask CRUD authority. Additional capability families or principals require their own governed activation/authority. Durable acceptance record: `docs/sessions/Jason-Direct-Ticket-Update-Canonicalization-Production-Acceptance-2026-09-24.md`.

### Datto RMM current acceptance

- Controlled endpoint: `AOT-50282`.
- Controlled component: `Get-DNS Settings AOT Ver 06042025-1`.
- Capability: `automation.component.execute`.
- First bounded provider attempt: HTTP `403`.
- Provider execution attempts: one.
- Broader-credential fallback: none.
- Datto job created: no.

Status: **Jason action path active; provider execution not yet accepted**.

Next step is to correct the dedicated Datto execution identity's minimum quick-job authority while preserving bounded Device Visibility and API Component Level. Do not broaden the read identity or add unrelated Global Settings/read permissions merely to observe the execution identity.

A successful retry requires new per-execution approval and governed job/readback verification.

## P8 — Legacy simplification

**Status:** Planned

**Goal:** Remove maintenance burden only after the ChatGPT/Jason replacement path is sufficiently proven.

Review for bypass/retirement:

- custom semantic routers;
- investigation state machines;
- duplicate conversation planners/renderers;
- duplicate Jason conversation memory not needed for governance;
- legacy OpenAI conversation calls used only to compensate for Teams transport;
- OpenClaw roles that no longer provide unique value.

Retain:

- Central Orchestrator;
- identity/authority;
- capability/resource catalog;
- execution policy/approvals;
- connectors/providers;
- secrets;
- evidence/provenance/audit;
- deterministic analysis;
- usage/cost telemetry;
- System Registry;
- Teams/OpenClaw components that still have justified secondary roles.

No retirement occurs until dependency review, tests, rollback, System Registry change, and observed verification are complete.

## Pilot success criteria

The broader technician pilot is successful when:

- technicians can use the experience fluidly from ChatGPT;
- normal follow-ups work through ChatGPT session context;
- Jason answers novel operational questions by composing governed tools rather than bespoke handlers;
- exact fleet/collection questions work when evidence exists;
- multiple providers can be combined in one conversational investigation;
- no provider credentials reach ChatGPT;
- identity/authority/client isolation are proven;
- reads/actions remain explicitly classified;
- actions require exact authority and approval as designed;
- provider denial fails closed without broader credential fallback;
- post-action verification proves durable result;
- every governed execution is auditable;
- duplicate Jason-side OpenAI calls are absent by default;
- Teams remains available as a controlled secondary path during pilot;
- rollback to prior production state is documented.

## Immediate next implementation sequence

1. Keep the 2026-09-16 governed-action checkpoint and `CURRENT.md` authoritative for resume.
2. Change the **Jason-specific** ChatGPT app permission from inherited **Allow low-risk actions** to **Allow read actions / ask before writes** and re-check the delivered tool catalog.
3. If `execute_governed_capability` becomes callable, do not repeat the already accepted Autotask mutation only for proof.
4. Correct the dedicated Datto execution identity's minimum provider-side quick-job authorization while preserving Device Visibility/API Component Level containment.
5. Run exactly one separately approved low-risk Datto component execution on the controlled endpoint/component pair.
6. Require governed job/readback verification before declaring Datto RMM execution accepted.
7. Preserve `direct_provider_access=false`, exact grants, per-execution approval, credential separation, and Central Orchestrator-only execution throughout.
8. Reconcile System Registry structured truth where the new logical capability/credential/deployment state requires registration or verification; do not infer lifecycle promotion from narrative docs alone.
9. Resume formal cross-provider technician acceptance and legacy simplification only after the action usability path reaches a stable checkpoint.
