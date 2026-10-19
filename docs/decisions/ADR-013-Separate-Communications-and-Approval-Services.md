# ADR-013 — Separate Communications and Approval Services, One Consistent Teams Experience

**Decision:** Owner-endorsed target architecture (2026-10-18); implementation migration staged and subject to review.
**Status:** Architecture accepted in principle; no new runtime authorization or production cutover.
**References:** J-002; [ADR-012](ADR-012-Canonical-Teams-Communication-Service.md); [ADR-009](ADR-009-Direct-Microsoft-Teams-Ingress.md); [J-102](../architecture/J-102-Governed-Approval-Architecture.md); P0 #1440 / #1545; usage-led shared-service #1535.

## Why this decision exists

The AOT Owner wants a **single, predictable Jason Teams experience**: consistent layout, templates, colors, language, identity, delivery and replies regardless of the requesting workflow. **Approvals are a distinct cross-cutting business/authority capability**, not a second Teams communications stack. This is deliberately two shared responsibilities, not one monolithic "Teams Approver".

A source audit of the current production-baseline commit `ad11c311251254d38da2c1295aadd292daed20ef` found reusable implementations already present (`JasonTeamsCommunicationService`, `UniversalInteractionService`, signed `jason-teams-gateway`, audience checks, `ApprovalRequestService`, `ApprovalInteractionDispatcher`) **alongside** bespoke Adaptive Card renderers and remaining direct outbound HTTP senders. Building another Teams bot, ledger, channel or approval runtime would violate integration-before-innovation and increase inconsistency.

## Constitutional architecture

```text
  BackupIQ | Autotask/tickets | RMM/EDR | Procurement | Billing
  Release Manager | Playbooks | Reports | Conversation/Intake
                    |                            |
          normal notification/form         action needs a decision?
                    |                            |
                    |                 Provider-neutral Approval Service
                    |                 (policy, approver, amount, expiry,
                    |                 immutable request, signed receipt,
                    |                 separate executor reauthorization)
                    |                            |
                    +----------+-----------------+
                               |
                   Universal Interaction Service
                   (existing Interaction v1; audience,
                    route, event correlation and one-send claim)
                               |
                    Teams Communications Service
                    (canonical templates, identity, delivery,
                     receipts, conversation updates, callbacks)
                               |
                     Existing Jason Teams Gateway
                    (Agents SDK, signed ingress, AOT tenant,
                     one proactive send transport)
                               |
                         Microsoft Teams
                               |
                signed reply -> canonical dispatcher
                     -> Approval Service (if approval)
                     -> guarded Central Orchestrator
                      only on a separately valid grant
```

The diagram is logical: **do not duplicate physical gateways, databases or execution engines**. There may be multiple in-process adapters, but only one canonical **contract** for each responsibility.

## Precise ownership boundaries

| Owner | Responsible for | Must never do |
| --- | --- | --- |
| **Workflow** | Decide what event occurred, canonical facts/evidence, business-specific validation, audience intent, correlation/ticket/CI link and subsequent work | Choose Teams colors/layout/provider endpoint; grant itself approval; read Teams token |
| **Approval Service** | Read active configurable authority/role/UDF/amount policy, create immutable request, route authorized approvers, expiry/delegation/denial, signed decision/audit, re-evaluate scope before governed continuation | Send its own Teams HTTP, trust button fields as authority, let an Approve alone execute a mutation |
| **Universal Interaction** | Accept existing `Interaction` v1 for notice/progress/questionnaire/approval; choose permitted channel, enforce durable one-attempt claim, route records | Authorize provider writes or create a new approval ledger |
| **Teams Communications** | Single presentation system, registered form/card renderers, active Microsoft recipient/tenant binding, disclosure/audience guard, send, delivery states, updates, inbound routing via signed gateway | Own financial limits or release CCC, autonomously retry ambiguous non-idempotent sends |
| **Teams Gateway** | Retain existing SDK Bot Framework ingress/proactive send and signed verified callback; return precise transport receipt | Invent a success for human delivery, invent identity or approval authority |
| **Central Orchestrator / JKD / CCC** | Re-check exact approved action, identity, organization/client, dependency, fingerprint, disruption rules and execution plan before a provider write | Treat Teams transport/provider acceptance as an execution grant |

Existing `ApprovalRequestService` can remain backed by workflow-specific repositories during migration; do **not** consolidate raw approval databases as a prerequisite. A **logical universal Approval Service facade/registry** may route to these established policy-specific implementations, preserving exact `relapproval-`, `procapproval-`, `planapproval-`, `owneruatapproval-` and legacy prefixes through the existing `ApprovalInteractionDispatcher`. Do not loosen current reserved-prefix rules or invent an unreviewed generic fallback.

## Single source of appearance

Reuse the existing `InteractionKind`, `VisualIntent`, `Fact`, `Field`, and `Action` types. The Teams renderer owns the look; workflow callers send **semantic facts**, not arbitrary card JSON.

**Proposed versioned AOT templates:** `notice`, `progress`, `incident`, `human_action_required`, `approval`, `questionnaire`, `acknowledgement`. Each uses:

- Header: **Jason · AOT** and a short meaningful subject; optional ticket/release/CI context from the owning workflow.
- Consistent labels: **What happened**, **Affected**, **Evidence**, **Current state**, **Next action**, **Expires**; show only facts actually known.
- Consistent semantic colors: information=Accent; action required/caution=Warning; critical=Attention; success=Good. Use Teams-supported Adaptive Card semantic colors rather than hard-coded individual RGB choices.
- Standard responsive layouts and button words: `Approve`, `Deny`, `Request changes`, `Submit`, `Acknowledge`, **only when the interaction contract and signed handler explicitly support them**. Notification is never dressed as an approval.
- The visible template version and event ID are recorded with the delivery claim. Displayed status never substitutes for a verified outcome.

The existing renderer supports version 1.5, while some legacy cards target 1.4. Until a separately tested client rendering/migration exists, keep existing source templates in place and retain backwards-compatible fallbacks; this decision does not force a global on-the-fly Adaptive Card upgrade.

All generated text to clients must come from an approved client communication policy/template. AI may populate bounded approved facts, but cannot improvise client-facing commitments or expose internal secrets. Internal technician/owner content still goes through the existing audience/classification controls.

## Stable workflow integration, not rewrites

A legacy producer migrates by supplying existing `Interaction` v1 fields (`workflow`, stable `interaction_id`, `correlation_id`, org/client, requestor, kind, title/summary, `VisualIntent`, `Fact` values) to `UniversalInteractionService` using a registered, tested **adapter**. Existing domain validation and provider work remain unchanged.

- **Notification/status:** adapter maps existing event -> `InteractionKind.NOTICE` or `PROGRESS`, standard template -> `ExistingTeamsInteractionAdapter` -> existing transport. No approval created.
- **Questionnaire/PO/invoice:** workflow retains fields, vendor/part/Autotask and UDF business validations; registers its existing questionnaire renderer and signed callback with the same interaction router. No business rules moved into card HTML.
- **Approval:** workflow persists an existing scoped `ApprovalRequest` with authorized recipients, expiry, immutable canonical intent/plan, then issues a semantic `APPROVAL` interaction. Universal Interaction verifies the persisted request and uses the canonical approved renderer. Teams signed callback enters the **existing** dispatcher and approval policy. The Central Orchestrator separately reauthorizes and verifies the exact execution plan.
- **Conversation:** existing signed ADR-009 Teams text/attachment ingress and follow-up flow remain; standard reply formatting routes outward via Teams Communications; conversation-to-approval escalation is a new Approval Service request, not a new bot conversation.
- **Failure/retries:** stable correlation + request ID, durable claim before irreversible send. Provider accepted != Microsoft chat inserted != user saw != signed vote != approved action != completed execution. Unknown outcome is indeterminate; no blind resend. A retry requires reconciliation/new idempotent versioned event.

**Cutover per producer:** `legacy` -> `shadow_same_payload_no_send` -> `canonical_single_sender` -> verified rollback/consumer drainage -> `legacy_retired`. A workflow feature flag/config selects which **one** path may send. Shadow comparison must not send two cards. The new workflow is not automatically activated by the inventory registry.

Existing source paths are captured in [Teams workflow migration inventory](../architecture/Teams-Communications-Approval-Migration-20261018.md) and `config/communications/teams-workflow-migration-v1.json`.

## Required safeguards and acceptance

1. No second Teams app, credential, provider transport, webhook, approval service repository, or outbound worker.
2. Before each migration, verify observed live consumers, original source module, exact message fields, recipient/tenant binding, policy/UDFs, signed callback route, idempotency, replay/expiry and no unauthorized provider write.
3. Existing owner permissions are unchanged. Technicians and employees can send authorized internal messages and submit ideas/read-only diagnostics without owner approval; *executing a disruptive/sensitive action* remains controlled by existing explicit authorization. A request for approval is never a grant.
4. Native-platform-first and organization/client boundaries survive across all adapters.
5. High-risk financial, playbook and production-release approvals migrate last; production `JASON_UNIVERSAL_APPROVAL_MODE` cannot turn on because a catalog/config or documentation file changed.
6. Every migration PR includes direct/legacy parity tests, a 1-source/1-destination/1-receipt constraint, canary verification, rollback proof and evidence of no duplicate Teams sends.
7. AOT's standard messaging design must remain provider-neutral enough for future portal/mobile/Alexa; adding a channel does not replace the Approval Service.

## Implementation plan and priority

- **Wave 0:** Inventory only, define versioned presentation and workflow registry, add source anti-duplication tests. Source-only / zero production change.
- **Wave 1:** Migrate simplest existing transport-aligned internal notices (e.g. billing audit status, existing governed internal Teams sends) to semantic Interaction notices. Keep current recipient and authority behavior. Verify parity before enabling.
- **Wave 2:** Adapt playbook review and autonomous-completion notifications; preserve approval fingerprint and existing governed send-plan contract.
- **Wave 3:** Migrate invoice/PO/procurement forms, MCP procurement review direct gateway send and billing action cards, *after separate P0 procurement acceptance*. Preserve employee requester, amounts, UDF thresholds, data extraction and callback.
- **Wave 4:** Consolidate all high-impact approval presentation/routing, including production releases and bounded plans; **do not** change execution authority or resolve disputed historical callback evidence by inference. Future channels can reuse these contracts.

Migration prioritization follows #1535 usage-led process and must not displace an open P0. Record real workflow invocation counts from authoritative telemetry when available; source presence alone is not proof of active production traffic.

**Decision criterion:** one Teams voice and design, one logical approval authority process, **no new provider** and **no interruption of existing production workflows**.
