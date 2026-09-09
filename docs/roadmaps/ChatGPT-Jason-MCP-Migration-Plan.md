# ChatGPT Business + Jason MCP Migration Plan

**Status:** Active P0 migration roadmap  
**Date:** 2026-09-08  
**Owner:** Jason Architecture Authority  
**Governing decision:** `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`  
**Target architecture:** `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`

## Objective

Move the primary technician experience from a custom Teams/Jason conversational stack toward **ChatGPT Business as the primary conversational surface with Jason exposed as a governed MCP/tool service**, while preserving all constitutional identity, authority, policy, approval, evidence, audit, provider, and Central Orchestrator boundaries.

## Guiding constraints

- Do not destroy the current working Teams path during migration.
- Do not route ChatGPT directly to provider credentials or unrestricted provider APIs.
- Do not implement question-specific handlers.
- Do not duplicate ChatGPT reasoning with a second Jason-side model by default.
- Do not enable consequential actions during the initial MCP proving phase.
- Do not call the MCP path operational until it is registered and verified in the System Registry.
- Preserve rollback at every material stage.

## P0 — Architecture and documentation freeze

**Status:** In progress

- [x] Accept ChatGPT Business + Jason MCP as preferred primary conversational architecture.
- [x] Preserve constitutional boundary: ChatGPT reasons; Jason governs/executes.
- [x] Define Teams as secondary/fallback rather than preferred full conversational surface.
- [x] Define OpenClaw as optional/secondary infrastructure rather than primary brain.
- [x] Define duplicate OpenAI API reasoning as exception, not default.
- [ ] Stop adding non-critical complexity to the legacy custom conversational state-machine path.
- [ ] Capture current production state before any topology changes.

## P1 — MCP foundation

**Goal:** A minimal local/development Jason MCP service backed by existing governed capabilities.

- [ ] Select/confirm supported MCP transport for ChatGPT Business custom app connectivity.
- [ ] Define MCP server component contract.
- [ ] Define MCP service registration in System Registry.
- [ ] Implement health/readiness endpoint or equivalent service verification.
- [ ] Expose capability-derived model-friendly read tools.
- [ ] Map MCP tool calls to existing Central Orchestrator execution.
- [ ] Prohibit direct connector/provider invocation from MCP layer.
- [ ] Preserve capability/resource names and provider neutrality.
- [ ] Return structured provenance-bearing results.
- [ ] Implement bounded errors/fail-closed responses.
- [ ] Add deterministic tests proving no secret/provider bypass.

### Initial read-only tool candidate set

Use existing governed capability surfaces where possible:

- managed endpoint search/read;
- endpoint audit/inventory;
- endpoint alert search/history;
- management site search;
- deterministic complete-evidence count/filter/group/list;
- additional already-governed reads only after contract review.

No action/write tools in this phase.

## P2 — Identity and workspace binding

**Goal:** A ChatGPT Business user invoking Jason can be bound to a Jason principal before execution.

- [ ] Determine supported ChatGPT custom MCP/app authentication mechanism for the AOT workspace.
- [ ] Establish workspace/app trust configuration.
- [ ] Map authenticated user identity to Jason principal.
- [ ] Enforce `teamaot.com` initial access policy where appropriate.
- [ ] Preserve capability-specific authorization independently of app access.
- [ ] Preserve organization/client scope.
- [ ] Define revocation/disable path.
- [ ] Test unknown user, disabled user, wrong workspace, missing identity, and cross-client attempts.

## P3 — ChatGPT Business pilot publication

**Goal:** Approved AOT technicians can add/use Jason from their normal ChatGPT Business workspace.

- [ ] Create/configure custom Jason MCP app in ChatGPT Business.
- [ ] Publish to an approved pilot scope.
- [ ] Confirm workspace visibility/access behavior.
- [ ] Prove a normal read-only request end to end.
- [ ] Prove follow-up conversational context without Jason duplicating chat memory.
- [ ] Prove multiple tool calls in one ChatGPT conversation.
- [ ] Prove novel wording without question-specific code.
- [ ] Prove exact collection-wide answer using deterministic Jason analysis.
- [ ] Prove cross-provider reasoning once a second provider read surface is ready.

## P4 — Cost optimization

**Goal:** Maximize value from existing ChatGPT Business seats and minimize duplicate API spend.

- [ ] Measure Jason-side OpenAI calls per ChatGPT-originated task.
- [ ] Target zero additional model calls for ordinary read/tool requests.
- [ ] Keep provider-doc/schema refresh out of per-turn model cost where possible.
- [ ] Cache stable provider documentation/schema/indexes.
- [ ] Keep pagination/count/filter/group operations deterministic.
- [ ] Define explicit capabilities that are permitted to invoke Jason-side models.
- [ ] Keep `gpt-5-nano` as least-cost default for any remaining routine Jason-side model call unless separately changed by policy.
- [ ] Define escalation criteria rather than user-visible model guessing.
- [ ] Add per-capability/provider/task cost telemetry.
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

The pilot is successful when:

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

1. Inspect current ChatGPT Business custom MCP/app requirements and supported authentication options.
2. Define Jason MCP server contract and System Registry entity.
3. Build read-only MCP adapter over existing Central Orchestrator/capability catalog.
4. Expose a small meaningful read tool set generated from capability metadata.
5. Prove locally without ChatGPT publication.
6. Configure identity binding and workspace trust.
7. Publish to a limited ChatGPT Business pilot.
8. Test natural technician conversations and measure cost/quality.
9. Expand providers only after the foundation is stable.
10. Simplify legacy conversational infrastructure only after replacement proof.
