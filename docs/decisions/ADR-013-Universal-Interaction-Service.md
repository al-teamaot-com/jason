# ADR-013: Jason Universal Interaction Service

**Status:** Proposed source foundation, INERT. Review branch stacked on constitutional Teams PR #1549. No production registration, live call, callback activation, owner approval or deployment authorized.

**Problem:** Jason has several channels and workflows with similar presentation and approval mechanics (release, procurement, playbook, ticket notices). A Teams-only universal approver would repeat the mistakes of workflow-specific bots, authorization checks and card layouts whenever a new function or channel is added.

## Decision and constitutional mapping

Adopt one **provider-neutral universal interaction contract**. Workflow owns **what** it needs to ask or tell people. Jason's existing JKD identity, audience/authority and approved workflow policy own **who** may receive, answer, approve or escalate. Universal Interaction Service owns interaction schema, visual intents, channel capability negotiation, correlation and durable delivery/response evidence. A channel adapter owns **how** it presents and delivers the request. Approval is a type of interaction, never a separate permission from drawing a button.

This implements J-002 Articles II (authority remains human), IV (provider-neutral ontology), V (integration before innovation), VI (governed execution) and IX/XVI (audit and modularity). Teams is the first adapter via ADR-009 and ADR-012, not the core system identity.

| Boundary | Responsible system | Explicitly prohibited |
| --- | --- | --- |
| Calling workflow | Release, procurement, ticket, playbook: facts, questions, business state, continuations | Builds custom Teams transport or grants recipient/approver permissions |
| Existing Jason authority | JKD identity, organization/client scope, roles and delegated authority, AudiencePolicyEngine | Styling cards or guessing the next approver |
| Universal interaction core | Versioned schema; semantic presentation; one-use claim in **existing** orchestration journal; channel feature negotiation; normalized response handoff | Provider execution; new approval ledger; OAuth/Entra grants; proof of human action from delivery |
| Existing channel adapter | Existing Teams sender, binding and original signed callback; later portal/voice/email adapters | Discretionary cross-client routing or changing approval scope |
| Existing approval/workflow | ApprovalRequestService atomic pending transition, signed gateway actor, procurement validation, CCC release owner signoff | Trusting editable card details for authority |

## v1 contract

A caller sends a bounded, immutable `Interaction`: version `1.0`, interaction ID, originating workflow, correlation ID, organization/client, requester, kind, title, summary, facts, conditional fields, actions, semantic visual intent, optional existing persisted approval reference, and optional UTC expiry. No selected Microsoft object, email address, transport token, actor identity claim or channel is embedded. A separately authorized `AuthorizedRoute` supplies recipient, route authorization reference, audience class, purpose and allowed channels.

Kinds: notice, progress, questionnaire, approval and acknowledgement. Field types: text, paragraph, number, currency, boolean, select and date. Visual intents: information, action required, caution, critical and success. Actions are declarative intents: submit, approve, deny, acknowledge, request changes, escalate. Unknown schema versions/actions fail closed.

The service requires that all semantic constraints be representable on an authorized channel. Teams supports styled non-executable information today; registered existing approval callbacks and questionnaire callbacks are opt-in only. If a future voice/email adapter cannot represent a form/approval, it must fail or make an authorized, correlation-preserving handoff; it may not silently omit required fields, accessible descriptions, or authentication. Layout/theme details are set centrally. Teams' own renderer controls font-family and high-contrast behavior, so textual semantic cues are mandatory.

### Delivery and response evidence

- Delivery uses `OrchestrationInteractionJournal` over the existing `SQLiteOrchestrationEventStore`. A deterministic unique `event_id` atomically claims an interaction **before** a non-idempotent provider call. No second SQLite database/table or new approval engine.
- An accepted gateway reference is **provider-accepted only**. It is not demonstrated receipt on the user's device, notification visibility, an approved decision, executed action, or human presence.
- On an uncertain delivery/response, retain the atomic claim and persist `reconciliation_required`; never send or execute a second time blindly.
- `UniversalResponseHandoff` is a **disabled** reusable service behind a hypothetical existing verified ADR-009 callback. It cannot parse unauthenticated client JSON or mint a signed reply. It requires injected signed ingress verification and existing approver/authority checks; it sends validated form answers to the originating workflow. The original business workflow still applies quote/PO approval thresholds, vendor rules and supplier controls.
- An approval reference must identify an existing immutable pending `ApprovalRequest`; existing `JasonTeamsCommunicationService` re-renders its canonical card. No universal component decides that a production release is safe or records an accepted approval. Existing signed callback and atomic approval services remain authoritative.

## Existing Jason source reused

- `jason_runtime.teams_communication_service.JasonTeamsCommunicationService`: workflow send rights, live AOT identities/Microsoft bindings, internal-only audience, immutable ApprovalRequest card, AudiencePolicyEngine and ADR-012 Teams transport.
- `orchestrator.event_store.SQLiteOrchestrationEventStore`: append-only durable unique delivery and response claims, audit correlation, provider receipt/unknown states.
- `connectors.src.jason_connectors.approval_requests`: existing persisted records and eventual atomic decision service; not copied or replaced.
- `connectors.microsoft_graph.teams_approval_channel.render_approval_card`: already canonical approval UI.
- Existing protected ADR-009 gateway and `ApprovalInteractionDispatcher`, **not** an independent webhook or bot.

No production `build_runtime_application` hook, callback registry entry, new sender process, provider permission or Teams card has been activated in this change. The current explicit default is `approval_dispatch_enabled=False`, `callback_enabled=False`; actual production issuance remains paused pending provenance investigation #1553 and containment design #1554.

## Test evidence required before source acceptance

- Actual `JasonTeamsCommunicationService` invoked by the universal Teams adapter with real `AudiencePolicyEngine` and existing approval request model, with synthetic provider transport.
- Generic status with a styled, no-action Adaptive Card; preview includes the facts the audience policy reviews.
- PO form with conditional contact, currency, quantity, ticket/no-ticket and separate financial audience policy gate. A questionnaire without an already registered workflow callback MUST fail before claiming delivery.
- Existing persisted owner-style approval in a **test-only enabled** configuration: render the canonical saved card, leave the original ApprovalRequest pending, never execute a release.
- Test-only second portal channel: verify the same contract routes without a Teams provider or second approval system.
- No authorized route, cross-tenant/organization/client scope, expired request, unknown channel, mismatched receipt, already-claimed delivery, uncertain provider response => fail closed with no blind retry.
- Opaque signed-response boundary with actor/scope, one-use audit claim, conditional answer validation, workflow response delegation, existing approval callback delegation, replay, bad action and expiry.
- Cross-language JSON Schema validation rejects untrusted identity, transport, token and policy fields.

## Rollout restrictions and completion

This is a **source-only foundation** stacked on PR #1549. Do not merge/deploy it independently onto production main before #1549's constitutional review and integration. It does not test the real UTA Approve/Deny buttons. It does not resolve disputed Teams release approval provenance P0 #1553, pending governed high-impact containment #1554, or general conversation-intent misrouting #1552.

Before any activation: resolve provenance and containment; register only existing authorized workflow callbacks; establish independently verified actor and owner consent, expiry and replay; require owner-approved exact SHA/CCC/rollback; test one harmless real Teams Approve and one Deny plus no-authority and replay paths; compare portal/Teams UI and ensure customer-facing scripting follows existing policy. The first rollout must not mutate customer tickets, procurement records or releases as part of a UI smoke test.

**Future contract rule:** the next 100 workflows should normally require 100 declarative specs but **zero extra communication engines**. A new medium adds one adapter and capabilities, not a rewrite of every workflow or an alternative authority ledger.
