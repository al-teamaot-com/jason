# Teams Communications + Universal Approval: existing-system migration inventory

**Date:** 2026-10-18. **Source pin:** `ad11c311251254d38da2c1295aadd292daed20ef` (GitHub main and observed production baseline). This is a **source-code inventory**, supplemented only by the directly verified two-card Owner UAT and release state. A code path's existence does not establish invocation frequency or customer-facing production acceptance.

**Authoritative decisions:** [ADR-013](../decisions/ADR-013-Separate-Communications-and-Approval-Services.md), [ADR-012](../decisions/ADR-012-Canonical-Teams-Communication-Service.md), [J-102](J-102-Governed-Approval-Architecture.md). **Source-readable catalog:** `config/communications/teams-workflow-migration-v1.json`.

## Common core already present

- `infrastructure/jason-teams-gateway/index.mjs`: existing AOT Teams Bot/Agents SDK and one `/internal/proactive/send`; signed, replay-protected ingress.
- `implementation/runtime_service/src/jason_runtime/teams_message_send.py`: already shared `post_existing_teams_gateway` and governed `communication.teams.message.send`.
- `implementation/runtime_service/src/jason_runtime/teams_communication_service.py`: `JasonTeamsCommunicationService`, `ExistingTeamsGatewayTransport`, recipient binding and audience checks, canonical approval-card material.
- `implementation/runtime_service/src/jason_runtime/universal_interaction/{contracts.py,service.py,teams.py}`: `Interaction`, `VisualIntent`, channel-neutral dispatch, journal and `ExistingTeamsInteractionAdapter`.
- `implementation/connectors/src/jason_connectors/approval_requests.py`: independent provider-neutral approval request, decision and atomic repositories; business policies are caller-owned.
- `implementation/runtime_service/src/jason_runtime/procurement_teams_flow.py`: existing `ApprovalInteractionDispatcher` is one callback router; `relapproval-`, `procapproval-`, `planapproval-`, bounded registered extensions.
- `implementation/communication/audience/engine.py`: existing audience/content controls, which do not turn a message into a grant.

**Important:** there is a shared transport today, but not every caller uses the shared presentation contract. Some functions still have their own Adaptive Card JSON and even direct gateway HTTP. These are the **adoption seams**, not a reason to replace the gateway.

## Existing producer-to-target mapping

| Producer / workflow | Current observed code path | Current adaptation state | Proposed migration (existing service only) | Wave |
| --- | --- | --- | --- | --- |
| Signed Teams conversations and ordinary replies | `orchestrator/teams_conversation_flow.py`, `jason-teams-gateway` | Already signed common ingress; output path has its own response renderer | Keep all inbound routing; standardize outward status layout without breaking multi-step conversation or attachment boundaries | 0 |
| General governed internal messages | `runtime_service/.../teams_message_send.py` | Canonical existing gateway HTTP client with separate governed send capability and execution-plan fingerprint | Wrap approved message intent into `Interaction` notice/progress; preserve plan/fingerprint and recipient authorization | 1 |
| Owner two-button **TEST ONLY** UAT | `runtime_service/.../universal_interaction/owner_uat.py` | Already uses `UniversalInteractionService`, existing sender, signed callback, immutable approval ledger | Treat as no-execution regression fixture, not broad release approval acceptance | 0 |
| Playbook autonomy approval cards | `runtime_service/.../playbook_autonomy_review.py` | Reuses shared gateway adapter; still builds a special card | Preserve persisted request/review/promotion rules, replace display with canonical approval template | 2 |
| Release Manager Owner approval | `runtime_service/.../mobile_release_approval.py` and playbook sender | Shared sender; special small-screen exact-SHA/CCC card and separate root release policy | Standardize presentation **after** separate high-risk policy/provenance acceptance; never change release authority | 4 |
| Teams procurement forms | `runtime_service/.../procurement_teams_flow.py` | Own multi-part Adaptive Cards and form/confirmation shapes | Register these existing forms as versioned canonical questionnaire renderers; retain all invoice/PO/part validation and attachment handling | 3 |
| Procurement approval workflow | `runtime_service/.../procurement_teams_flow.py` and reused playbook sender | Separate durable finance request and signed approval route | Shared approval presentation, no change to expense limits, Autotask UDF thresholds, PO execution, or provider workflow | 3 |
| ChatGPT/MCP invoice Teams review | `mcp_service/src/jason_mcp/server.py::_send_procurement_review_to_teams` | **Direct gateway HTTP**, with separate card creation and receipt | Replace raw HTTP with existing sender and registered form template, preserve MCP authentication and exact business payload | 3 |
| Hardware billing audit/disposition | `runtime_service/.../procurement_billing_audit_maintenance.py` + `procurement_inventory_billing.py` | Shared transport; technician/Lori routing and domain-specific disposition card | First migrate text/status notices; subsequently registered technician forms without changing billing evidence/authority | 1/2 |
| Autonomous completion/ticket and engineering status | `runtime_service/.../autonomous_completion_notification.py` | **Direct gateway HTTP**, own event cards; presently bound to governed execution plans | Route event semantics into canonical notices **without losing execution-plan fingerprint, dedup or current recipient** | 2 |
| Bounded universal plan approvals | `runtime_service/.../universal_teams_approval.py` | Source present, separate plan ledger/authority; broad mode **off** pending governance | Adapt display and callback only after high-impact plan approval acceptance; preserve one approval per immutable bounded plan | 4 |
| Legacy Graph approval channel | `connectors/microsoft_graph/teams_approval_delivery.py` | Separate provider adapter in source; live consumer unknown | Inventory actual callers, preserve until no consumer and exact parity tests; no blind deletion | 4 |
| Legacy OpenClaw approval transport | `connectors/microsoft_graph/openclaw_teams_approval_transport.py` | Alternate adapter in source; live consumer unknown | Same: audit, overlay adapter and retire only with proved zero consumers | 4 |

**Additional demand already tracked but not declared deployed:** release/ticket blocked-owner notifications and hourly ticket TLDR (#1116), ordinary invoice/document intake (#759), technician/employee idea submissions (#1519, #877), future AOT mobile/voice (#1475). They become new **consumers of these same existing interfaces**, not their own Teams implementations. Do not claim a missing producer is in production merely because the TODO exists.

## Roll-in checklist for each workflow

1. **Find the producer and active consumers:** actual module, event name, signed ingress/Teams bot, webhook or gateway call; verify live invocation/recipient evidence. Keep customer/organization scope and ticket/CI links.
2. **Freeze current behavior:** payload/card screenshots on mobile and desktop, current callback route, role & spending limits, acceptance/rejection, delivery receipt, unknown-send behavior and exact execution authority. Capture at least one normal, one denied and one failure-path test.
3. **Translate, do not rewrite:** an adapter produces existing `Interaction` v1, or for an approval persists/uses the existing `ApprovalRequest` and its verified route. No provider access, approval policy or Autotask action moves into the Teams renderer.
4. **Select one active sender:** switchable per-workflow `legacy` / `shadow_same_payload_no_send` / `canonical_single_sender`. Shadow must not post a second message. Roll back by config/release to legacy only on **known** send-state.
5. **Canonical UX:** renderer alone applies common style tokens/templates and supplied facts. Distinguish notice from actionable approval. Link evidence; never include credential/secret. Content audience checks and exact recipient binding remain authoritative.
6. **Verify lifecycle:** claim -> gateway accepted (possibly synthetic provider ID) -> actual Teams message insertion only if independently verified -> signed reply/decision receipt -> separately governed execution result. Unknown delivery is not "delivered"; do not blindly retry.
7. **Cut over/retire:** compare old/new message meaning, recipient, authority and errors. Require no duplicate active senders and verified live acceptance before retiring any legacy adapter. Persist rationale, exceptions and rollback evidence.

## Card/UI design system: one place

Use the established `VisualIntent` and Teams Adaptive Card semantic colors from the config catalog (Accent/Warning/Attention/Good). Workflow callers specify event/facts, never a hex color or arbitrary heading text. Standard template types:

| Template | Information emphasized | Buttons / authority |
| --- | --- | --- |
| `notice` | Subject, summary, evidence/source | None |
| `progress` | What began, current step, verified status, next milestone | None |
| `incident` | Urgency, impacted client/device, evidence, corrective owner | Only registered and governed actions |
| `human_action_required` | Exact human dependency and smallest safe step | May link to separate approval request, but never fake approval |
| `approval` | Exact immutable target, approver, scope, risk, expires, effects | Approve/Deny from already persisted request and signed registered route |
| `questionnaire` | Structured fields, validations, submit/cancel behavior | Workflow-registered callback only |
| `acknowledgement` | What was decided, what will happen next, precise receipt state | No new execution grant |

Release cards should remain easy to read on narrow phones; do not sacrifice exact commit SHA or critical rollback facts just to look consistent. Finance cards need pricing and line-item clarity. Semantic layout consistency does **not** justify removing legally/materially relevant information.

## Priority and workload management

This is **P1 architecture adoption** coordinated with #1535, while existing P0 #1440 (broader Universal Approver), #759 (invoice intake), #1078/#1196 (release/TODO worker reliability) retain priority. Wave 0 (inventory/tests/contract) is source-only and does not consume production-change slots. Concrete workflow migrations must be separately admitted and have targeted acceptance; prioritize observed call counts over static source counts as telemetry becomes available.

## Acceptance checklist

- Every actively sending Teams workflow appears in a verified producer/consumer catalog, plus unknown consumers explicitly tagged for investigation.
- A first low-risk notice migrates to the existing `Interaction` facade, using the same Bot/identity, without double-sends or loss of event/ticket/correlation links.
- A first scoped approval migrates in presentation only, maintaining original `ApprovalRequestService`, signed callback, expiry, tenant/client and JKD/CCC/execution rules.
- Shared templates render consistently on real Teams mobile and desktop; no raw provider message ID is fabricated into proof of delivery.
- Every approved action still comes through a fresh, exact-scope authority context and separate execution verification; no second approvals database or Teams app.
- Each workflow has a bounded feature flag, regression tests, rollback/readmission procedure and documented retirement decision.
