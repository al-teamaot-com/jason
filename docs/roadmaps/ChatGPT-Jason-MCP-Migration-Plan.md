# ChatGPT Business + Jason MCP Migration Plan

**Status:** Active migration roadmap  
**Date:** 2026-09-08  
**Last reconciled:** 2026-09-09  
**Owner:** Jason Architecture Authority  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`  
**Target architecture:** `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`

## Objective

Move the primary technician experience from a custom Teams/Jason conversational stack toward **ChatGPT Business as the primary conversational surface with Jason exposed as a governed MCP/tool service**, while preserving all constitutional identity, authority, policy, approval, evidence, audit, provider, and Central Orchestrator boundaries.

## Execution status — 2026-09-09

The roadmap has advanced beyond its original planning checklist.

Durable current state:

- **MCP-001 — complete.** ChatGPT Business + Jason read-only MCP foundation is source-durable, publicly reachable through the approved AWS Caddy/ZeroTier edge, authenticated through Microsoft Entra, limited to the exact three-tool governed read-only surface, proven through harmless live reads, and represented as verified System Registry topology.
- **MCP-002 — active.** Positive ChatGPT/Entra/workspace identity binding is proven. Remaining work is durable negative/isolation evidence for unknown or unbound identity, invalid tenant/workspace context, missing authority, and client/scope isolation where those cases can be safely exercised.
- **MCP-003 — planned.** Cross-provider ChatGPT technician proof has not yet been completed as the primary workstream.
- **MCP-004 — planned.** Legacy conversational-stack simplification remains deferred until the replacement path is sufficiently proven.

Accepted MCP source checkpoint:

`727c3fa6cbcb59dab32f77632393bc5407826ed0`

Accepted live MCP image:

`jason-mcp:source-727c3fa`

Accepted observability deployment checkpoint:

`ecc265ee59645154f0bc86b5aa0dc5a2e375f022`

System Registry reconciliation now represents and verifies the MCP service, AWS/ZeroTier public edge, Prometheus, Grafana, usage exporter, usage-attribution exporter, and their deployment extension.

The phase checklists below remain useful as the original governed implementation plan, but they are not a more current source than `docs/control/CURRENT.md`, `docs/roadmaps/Jason-Roadmap-Status.json`, the System Registry, and dated proof records. Do not re-run completed discovery or foundation work merely because an older checkbox remains unchecked.

## Guiding constraints

- Do not destroy the current working Teams path during migration.
- Do not route ChatGPT directly to provider credentials or unrestricted provider APIs.
- Do not implement question-specific handlers.
- Do not duplicate ChatGPT reasoning with a second Jason-side model by default.
- Do not enable consequential actions during the initial MCP proving phase.
- Do not call the MCP path operational until it is registered and verified in the System Registry.
- Preserve rollback at every material stage.

## P0 — Architecture and documentation freeze

**Status:** Foundation complete; legacy simplification remains deferred

- [x] Accept ChatGPT Business + Jason MCP as preferred primary conversational architecture.
- [x] Preserve constitutional boundary: ChatGPT reasons; Jason governs/executes.
- [x] Define Teams as secondary/fallback rather than preferred full conversational surface.
- [x] Define OpenClaw as optional/secondary infrastructure rather than primary brain.
- [x] Define duplicate OpenAI API reasoning as exception, not default.
- [x] Stop adding non-critical complexity to the legacy custom conversational state-machine path as the preferred architecture.
- [x] Capture current production state before further topology changes.

## P1 — MCP foundation

**Status:** Complete as MCP-001

**Goal:** A minimal Jason MCP service backed by existing governed capabilities.

- [x] Select/confirm supported MCP transport for ChatGPT Business custom app connectivity.
- [x] Define MCP server component contract.
- [x] Define MCP service registration in System Registry.
- [x] Implement health/readiness endpoint or equivalent service verification.
- [x] Expose capability-derived model-friendly read tools.
- [x] Map MCP tool calls to existing Central Orchestrator execution.
- [x] Prohibit direct connector/provider invocation from MCP layer.
- [x] Preserve capability/resource names and provider neutrality.
- [x] Return structured provenance-bearing results.
- [x] Implement bounded errors/fail-closed responses.
- [x] Add deterministic tests proving no secret/provider bypass.

### Accepted read-only tool surface

The proven MCP surface is exactly:

- `jason_mcp_status`
- `discover_capabilities`
- `execute_read_capability`

No action/write tools exist in this phase.

## P2 — Identity and workspace binding

**Status:** Active as MCP-002

**Goal:** A ChatGPT Business user invoking Jason can be bound to a Jason principal before execution.

- [x] Determine supported ChatGPT custom MCP/app authentication mechanism for the AOT workspace.
- [x] Establish workspace/app trust configuration.
- [x] Map the proven authenticated user identity to a Jason principal.
- [x] Use the AOT Microsoft Entra tenant as the initial authentication boundary.
- [x] Preserve capability-specific authorization independently of app access.
- [x] Preserve organization/client scope in governed execution.
- [x] Define operational disable/rollback paths for the MCP service/app.
- [ ] Preserve durable negative/isolation proof for unknown/unbound identity, invalid tenant/workspace context, missing authority, and cross-client attempts where safely testable.

## P3 — ChatGPT Business pilot publication

**Status:** Positive read-only pilot path proven; cross-provider proof remains

**Goal:** Approved AOT technicians can use Jason from their normal ChatGPT Business workspace.

- [x] Create/configure custom Jason MCP app in ChatGPT Business.
- [x] Publish/enable it in the AOT workspace for the current read-only pilot.
- [x] Confirm workspace visibility/access behavior for the proven pilot identity.
- [x] Prove a normal read-only request end to end.
- [x] Prove ordinary follow-up use within the ChatGPT session without Jason duplicating full chat memory.
- [x] Prove governed tool discovery and repeated tool invocation from ChatGPT.
- [x] Prove representative operational reads without question-specific MCP tools.
- [x] Prove exact collection-wide answers where complete governed provider evidence exists.
- [ ] Prove the formal cross-provider technician scenario required for MCP-003.

## P4 — Cost optimization

**Status:** Observability foundation deployed; further policy refinement remains

**Goal:** Maximize value from existing ChatGPT Business seats and minimize duplicate API spend.

- [x] Measure Jason-side model/provider usage independently from ChatGPT subscription usage.
- [x] Establish visibility showing zero additional hosted-model usage when ordinary governed reads do not require it.
- [ ] Keep provider-doc/schema refresh out of per-turn model cost where possible.
- [ ] Cache stable provider documentation/schema/indexes where appropriate.
- [x] Keep pagination/count/filter/group operations deterministic where implemented.
- [ ] Define the complete set of explicit capabilities permitted to invoke Jason-side models.
- [ ] Maintain least-cost/default and escalation policy for any future governed Jason-side model use.
- [x] Add capability/provider/task-oriented usage telemetry foundations.
- [x] Add actor/source attribution telemetry foundations.
- [ ] Add optional per-tech/per-day/per-client soft/hard budget policy where useful.

## P5 — Provider expansion

**Goal:** Adding providers expands Jason's observable/action world without retraining conversational logic.

Priority read surfaces:

1. Datto RMM — existing foundation, normalize for MCP.
2. Autotask — production read adapter and ticket/company/contact/resource queries.
3. Microsoft 365 / Graph — users, licensing, sign-ins, groups, device/identity state where authorized.
4. IT Glue — configuration/documentation reads where authorized.
5. Additional AOT stack providers by governed priority.

For each provider:

- [ ] capability/resource manifest;
- [ ] governed credentials;
- [ ] documentation/schema source where useful;
- [ ] pagination/completeness behavior;
- [ ] deterministic collection analysis support;
- [ ] provenance/audit;
- [ ] client/tenant isolation;
- [ ] MCP exposure from generic capability metadata;
- [ ] unseen-question test;
- [ ] retirement/replacement criteria.

## P6 — Cross-provider technician workflows

**Goal:** ChatGPT composes Jason tools naturally rather than Jason encoding bespoke workflows.

Proving scenarios should include:

- endpoint state + related Autotask ticket context;
- Microsoft 365 user + endpoint association + security alert context;
- client/site comparison across management and PSA data;
- exact fleet counts/filtering by arbitrary provider-observed facts;
- follow-up questions using the same ChatGPT session context.

No scenario should require phrase-specific code.

## P7 — Governed actions

**Goal:** Add carefully selected consequential tools after read-only MCP operation is stable.

Prerequisites:

- stable identity binding;
- stable client isolation;
- explicit action authority;
- risk classification;
- policy/preconditions;
- approvals where required;
- idempotency;
- audit/evidence;
- rollback/recovery;
- human-visible confirmation semantics where appropriate.

Candidate action classes may include:

- Autotask ticket updates/creation;
- governed email sending;
- approved Microsoft administrative actions;
- approved DRMM actions;
- other capabilities only through normal governance.

ChatGPT app access alone must never grant action authority.

## P8 — Legacy simplification

**Goal:** Remove maintenance burden only after MCP proves the replacement path.

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

- technicians report the experience as comparably fluid to ordinary ChatGPT use;
- normal follow-ups work through ChatGPT session context;
- Jason answers novel operational questions by composing governed tools rather than bespoke handlers;
- exact fleet/collection questions work when evidence exists;
- at least two providers can be combined in one conversational investigation;
- no provider credentials reach ChatGPT;
- identity/authority/client isolation are proven;
- reads/actions are clearly separated;
- every governed execution is auditable;
- duplicate Jason-side OpenAI calls are absent by default;
- Teams remains available as a controlled secondary path during pilot;
- rollback to the prior production topology is documented.

## Immediate next implementation sequence

1. Finish MCP-002 with durable negative/isolation evidence for the ChatGPT/Entra/workspace identity boundary.
2. Keep the existing MCP surface read-only while that proof is completed.
3. Close MCP-002 only when the evidence supports the required identity/authority/client-isolation claims.
4. Begin MCP-003 cross-provider technician proof using reusable governed capabilities rather than question-specific MCP tools.
5. Continue usage/cost/actor telemetry as an observational control; treat runtime-side attribution activation as a separate governed deployment decision.
6. Simplify legacy conversational infrastructure only after replacement proof and dependency review support it.
