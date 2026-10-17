# ADR-012 — Canonical Jason Teams Communication Service

**Status:** Proposed for constitutional and security review, 2026-10-17
**Parent:** #1440, #1545. Previous alternative PR #1548 must not merge as a substitute for this canonical implementation.

## Architectural decision

**Every Jason workflow requesting Teams communication uses one approved, replaceable
communications capability.** Teams is a provider and user interface, not an
authority source. Do not provision another Teams bot, OAuth registration,
notification queue, or parallel approval ledger merely to add a workflow.

This enforces J-002 **Article V (Integration Before Innovation)**, IV (Capability
Abstraction), VI (Separation of Responsibilities), VIII/IX (Explanation and Audit),
XIII (Simplicity), XV (Continuity) and XVI (Modularity and Reversibility).
ADR-009 remains authoritative for authenticated Teams inbound ingress, while
ADR-005/007 govern approved outbound transport until retired by a reviewed
replacement. This ADR does not alter those existing production boundaries.

## Reused components — authoritative reuse ledger

| Required function | Reused component | Authority boundary |
| --- | --- | --- |
| Inbound Teams message/button | Existing `jason-teams-gateway`, Agents SDK, signed conversation envelope and ingress replay store | Verified gateway/tenant/actor as **evidence**, never a grant |
| Human/role identity | Existing Microsoft-to-Jason binding, IdentityAuthorityService and JKD roles | Live organization/capability/scope check |
| Outbound text, card and status | Existing `/internal/proactive/send` gateway and `communication.teams.message.send` capability | Workflow-specific send permission and receipt |
| Communication suitability | Existing `communication.audience.AudiencePolicyEngine` | Recipient, org/client, channel, content, sensitive disclosures |
| Actionable approval display | Existing `render_approval_card(ApprovalRequest)` / `TeamsGatewayPlaybookApprovalSender._adaptive_card` | Card cannot invent approval scope or modify server material |
| Approval decisions | Existing `ApprovalRequestService`, atomic approval repository, existing `ApprovalInteractionDispatcher` | One-time approve/deny, live approver authority and expiry |
| Provider execution | Central Orchestrator plus per-step governance/CCC/JKD | Only after the workflow verifies the receipt and execution authority |
| Multi-step bounded plans | Existing `UniversalTeamsApprovalInteractionFlow` and immutable plan ledger | Kept disabled until live benign acceptance and review |

The newly introduced `ExistingTeamsGatewayTransport` is an **adapter around the
existing live provider**, not a replacement provider or new communication
transport. Existing playbook review and hardware-billing notification senders
are refactored to reuse this adapter; invoice/PO form cards and other workflows
must use the same shared transport, not duplicate low-level HTTP calls.

`JasonTeamsCommunicationService` requires an explicitly authorized workflow
caller, active recipient identity and Microsoft binding, audience/content
review, and for approvals a **pending persisted ApprovalRequest** with the
recipient in its original immutable approver list. The display text and
Adaptive Card are re-rendered from that stored request; caller-supplied
approval facts cannot override them.

`ExistingTeamsApprovalReceiptHandler` adapts the existing decision service
for workflows like manager expense approvals. `ApprovalInteractionDispatcher`
remains the **single callback router** with prefixed, non-overlapping,
explicitly registered workflow handlers. It keeps existing owner
procurement `procapproval-`, mobile release `relapproval-`, bounded plan
`planapproval-`, and playbook approval routing unchanged. Adding a workflow
is a policy/handler registration, not a second gateway or approval engine.

## Supported use cases and exact scope

- **Internal message/status:** operational updates, release progress,
  automated diagnostic completion, technician follow-up and escalations;
  bounded templates and relevant evidence links, no unilateral customer-facing
  commitments.
- **Supervisor expense approval:** employee submits expense -> existing durable
  request with amount, purpose, attachment references, supervisor role, cap and
  expiry -> shared Teams card -> authenticated supervisor vote -> atomic receipt;
  **no expense posting/reimbursement solely because a Teams card was clicked**.
- **Invoice, part, quote and PO cards:** existing procurement form workflow
  retains its approval thresholds, client/ticket links, vendor/part/product
  validation and governed writes. Existing UI and approved workflow remain
  authoritative; a shared transport refactor cannot loosen its rules.
- **Future workflows:** register a canonical operation, identity/authority
  policy, recipient/audience specification and (if actionable) exact persisted
  approval record; do not create workflow-specific Teams credentials.

## Risk and rollouts

1. **Transport acceptance is not user delivery or approval.** Gateway response
   `message_id` proves provider accepted only. Sender must distinguish
   submitted/accepted/delivered/decision received/authorized/executed.
2. **Notification sending is not an execution grant.** Routine, approved internal
   messages do not need an additional human sign-in or new OAuth registration.
   Sensitive/disruptive/high-value financial operations still require separate
   policy, role and scoped decision approval.
3. **Existing SDK-authenticated Teams activity and Jason identity binding are
   retained.** No user claim in an editable card supplies authority. A higher
   independent assurance factor may be required for a specifically identified
   high-risk workflow by separately reviewed policy. Do not impose unrelated
   OAuth on delivery or claim it replaces role/JKD/CCC evidence.
4. **No production deployment just from passing unit tests.** Protected CI,
   independent constitutional/security review, exact GitHub SHA and owner
   authorized CCC release, rollback plan and live safe acceptance required.
5. **Live acceptance:** message to owner, invoice/PO card and bounded expense
   manager card to two authorized AOT staff, native Teams approve and deny
   responses with distinct receipts and actor/tenant/replay/expiry tests,
   execution state separately verified. No customer/provider mutation in
   harmless pilot.
6. **Source-of-truth preservation:** existing status/finance/reporting flows
   unaffected; no direct agent-to-agent communication or provider writes.

## What this does not assert

- **Not proof that production UTA is currently fully enabled.** Production
  `JASON_UNIVERSAL_APPROVAL_MODE=off` until a separately approved rollout.
- **Not proof that invoice/PO *actions* completed.** Sending the card alone
  is not an accepted decision or successful Autotask change.
- **Not an expense accounting engine.** Expense business validation and
  posting remain in the owning workflow; shared Teams carries messages and
  governed approval decisions only.

## Anti-duplication validation (future work)

The pipeline must check, before introducing any provider, bot, sender,
approval ledger or client, whether a canonical capability already exists and
require an ADR explaining why reuse is insufficient. A delivery/approval PR
must cite this ledger and include tests of *existing* invoice/PO, playbook,
manager expense and generic notifications, plus security, replay, CCC and
recipient authority. Any direct extra `/internal/proactive/send` implementation
must have an explicit reviewed exception and retirement date.

**Proposed retirement:** this concrete gateway adapter can be replaced by any
future governed Teams provider implementing the same capability without
rewriting financial, ticket, backup or engineering workflow policy.
