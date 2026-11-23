# Shared Teams notifications and approvals — November 23, 2026

Status: isolated engineering candidate. No merge, production activation, provider
writes, real notifications, role changes or PMv4/audit recovery changes authorized
by this record. Today's explicit Owner decisions supersede conflicting older UX,
notification, routing and scheduling requirements; production safety remains.

## Owner-confirmed contract

- One shared communications/approval capability for procurement, technician,
  playbook and release workflows; each retains existing business/authority rules.
- Procurement owns Autotask reads, limits, amounts, PO/invoice validation and
  execution. Teams is the presentation channel, not financial authority.
- An explicit in-limit purchase request needs no second human approval. Check
  total including tax, freight and fees. Missing/ambiguous limits fail closed.
- Above-limit requests follow Supervisor contact relationships until sufficient
  authority is found. Missing/unavailable/invalid routing falls back to Al Davis.
- One decision covers the bounded reviewed purchase and ceiling. Material changes
  require amended scope; ordinary internal steps must not demand repeat consent.
- Remind hourly during 08:00–18:00 America/New_York Monday–Friday. Escalate after
  600 accumulated business minutes. Holidays are configurable; no holiday dates
  were supplied, so the supplied calendar excludes weekends only.
- Approval/action-required, escalation, verified completion and human blockers
  notify both requester and current approver. No routine progress stream.
- Requester copies carry no approval buttons; current approval authority stays
  independently enforced. No self-approval permission is added.
- An authenticated Jason interface, including ChatGPT, may accept decisions under
  the same independently verified identity/scope/audit rules when Teams is down.
  Queue/reconcile Teams notifications; never equate provider acceptance with read.
- Supervisor is an active Contact Text (Single Line) UDF. Use the supervisor's
  email address and resolve one active same-company contact plus trusted binding.
- Cards must be concise, mobile-readable and free of internal jargon. The request
  supplies actual facts; centrally configured templates choose labels and fields.
- Business settings and additional presentation templates use configuration or DB
  entries, with validation, auditable versions and safe reload, without rebuilding.

## Reuse and implementation

Extends existing `TeamsGatewayPlaybookApprovalSender`, canonical signed approval
requests/callbacks, procurement maintenance, submission store and composition.
No new bot, approval ledger, scheduler, credential or provider endpoint.

`JASON_TEAMS_WORKFLOW_POLICY_PATH` is optional; absent means unchanged legacy
behavior. The supplied `config/communications/teams-workflow-policy-v1.json` is
**disabled**. An explicitly supplied invalid file fails closed. Reads reload at
each operation. Apply edits by atomic file replacement, through an authorized
configuration change path. Full config digest supports evidence; the routing
scope digest pins fallback routing independently of presentation and timing.
Changing labels/reminder intervals does not demand new purchase consent. The
existing supervisor policy also reloads its file for decisions and revalidation;
policy changes cannot be hidden by an old in-memory snapshot. Existing granted
authority still bounds the eligible recipient set.

The common renderer chooses an existing capability/mode and reads facts only
from its persisted approval. It copies existing signed action IDs/nonces rather
than letting configuration invent callbacks, grants, amounts or approvers. A
second existing approval type is proven by adding one template in a test.
Purchase item, vendor, requester, quantity and total cannot be omitted.

Supervisor lookup uses existing governed Contact search and trusted Microsoft
bindings. The relationship is routing evidence, never a grant. Candidates must
already be in the approved procurement authority set; insufficient limits are
skipped, loops/cross-company/ambiguous/inactive entries fall back safely. New
supervisor privileges still require the existing authorized role configuration.

Durable notification attempt claims are atomically stored in the **existing**
submission row. They survive process restarts; partial/unknown sends stay claimed
for reconciliation. No blind retry can duplicate the same event. Requester and
approver each receive one initial notice (action card vs non-action copy), rather
than an action card plus duplicate status message to the approver.

Business timing is independent of the short-lived card challenge. Expired
procurement offers are cancelled through canonical compare-and-set and replaced
with a new nonce/request for the same business digest; the business clock is not
reset. A simultaneous valid decision races against that existing atomic terminal
transition, not against an ad hoc approval database write. The old request remains
immutable history. A late click that already marked it EXPIRED does not strand
the business request; only an undecided offer may be renewed. Al receives continued hourly reminders at the final fallback;
there is no self-escalation and silence never approves anything.

## Additional canonical integration

The disabled-by-default `workflow_approval` MCP action reviews an existing
configured purchase and accepts an explicit Approve/Deny with its exact reviewed
scope. The server independently derives tenant/OID/principal and assurance from
validated Entra OAuth; none are tool inputs. It audits a token fingerprint plus
exact decision/scope/response/time evidence through the existing authority audit
before consuming the **same** canonical one-use receipt. Raw bearers are not
logged. Live binding, organization, current Supervisor relationship, spending
policy, material digest, expiry and no-self-approval gates remain. The new channel
`jason_mcp_entra` is accepted only for configured purchases; legacy purchase
receipts retain their Teams-only guard. No global Owner-admin role or release
permission is granted. A provider-execution or notification failure cannot erase
an already durable human decision or demand a duplicate decision.

The existing gateway records real issued-card references in its existing decision
store. A canonical terminal receipt can replace only the original bot messages
bound to that tenant, recipient, conversation and approval. Editable callback data
cannot select another message. Configured terminal cards have no hidden or visible
vote actions. The reactive Teams callback and authenticated MCP fallback both
reuse the existing bot update API. Existing procurement maintenance queues and
reconciles terminal presentation separately from purchase execution. Old replaced
offers show a configured inactive-link state. An update failure retains the
canonical decision and a reconciliation requirement, never a repeat purchase.
Untracked pre-upgrade or synthetic-message references remain unverified.

Configured sends carry stable per-approval/event/recipient communication IDs.
The existing gateway store claims the send before provider message execution,
retains real acceptance receipts and returns an identical saved receipt on a
matching retry. A changed payload is denied. An interrupted provider outcome
without a stored receipt remains blocked; synthetic IDs never prove delivery.
The internal receipt-read route performs no send or approval. Maintenance stores
an exact replacement plan and deterministic approval ID in the existing submission
row before retiring an offer. Canonical CAS and immutable scope checks make
recovery after cancellation, request creation, pointer transition or a partial
fan-out reuse the same request/nonce. Business clocks remain unchanged. Expired
undecided replacements are superseded without invented delivery or consent.
Older claims lacking a persisted recovery plan still require evidence review.

## Acceptance and limits

Latest local verification: **277 Python tests passed** across targeted runtime,
composition, procurement, MCP handoff, canonical approval/security and architecture
suites; **46 Node gateway tests passed**. Engineering standards, documentation
control, syntax/compilation and diff checks PASS. The gateway workflow now runs all
its test files. A packaging regression test found and corrected a missing
`objective-approval-route.mjs` copy; new modules are also explicitly packaged.
The installed SDK's pinned 1.6.1 source confirms `updateActivity` support.

These are source/fixture tests, not provider-backed acceptance. No production
application, credential, authority, service, contact or provider state was changed.
Previously governed read-only Contact/Entra checks succeeded: the internal query
returned 45 contacts (29 active), no Supervisor assignments. Autotask serializes
numeric spending UDFs with four decimal places; exact trailing zeros are accepted
without rounding fractional cents. Al remains the configured fallback.

Fresh November 23 host inspection verified runtime/MCP remain on the original
`d1b8c196dadd4b672ec8ba47075f27bb61c98d63` images and gateway on
`0f423d54a3acce61ff7b944897a074b482488f15`. Exact rollback image IDs:

- runtime: `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`
- MCP: `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`
- gateway: `sha256:0a3529f8052ee85516b3fd73e2f2f4edae7748fd7633ecaf7ae5a318602eb4f5`

Protected freeze SHA256 remains
`bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`.
The protected readback at 15:58:12 UTC (10:58:12 Eastern) reports circuit breaker
**OPEN**, `continuous_production_drift_detected`, one
`required_system_unit_not_active` problem. The audit journal service and its
maintenance timer were inactive on the independent host check. Those are live
release blockers belonging to the active audit recovery, not authorization to
repair its units from this Teams workstream. The projected readback is evidence;
only native Root verification can restore the gate. Remote execution is UID1000;
its configured privilege blocks remain unchanged.

The global Owner-admin probe still rejects `AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED`.
That result is **not** proof of release-Owner rejection: release approval has a
separate exact OAuth identity policy. Do not expand admin roles as a Teams fix.
MCP's published release-approval evidence also remains unavailable/mismatched.

Source tests cover business hours, weekends/holidays/DST, policy reload, stale
routing and scope, exact-cent numeric UDFs, requester non-action copies, a second
configured template, denial/replay/expiry, authenticated alternate-channel
receipts, authority/audit failures, recovery at both cancellation/create
interruption points, unknown provider outcomes, original-message isolation and
terminal card updates without repeat execution.

The following remain operational/integration acceptance:

1. Clear the native production breaker through the **existing audit-recovery
   owner**, then reverify health, freeze, exact live sources and release lane.
2. Reconcile open core-service changes and prepare an exact reviewed protected
   core release. The independent-component controller explicitly protects runtime,
   MCP and Teams gateway; it must not be repurposed to swap them. Do not deploy
   full current Main as a Teams-only update or transplant unrelated Owner/audit
   changes from the feature branch's complete MCP server file.
3. Deploy the coupled gateway/runtime/MCP interfaces under the existing exact
   source/image/rollback release controls. Keep the policy disabled until the
   controlled canary is approved and the app's tool publication is verified.
4. Real active requester/supervisor/Owner roster/authority review; fresh Contact
   spending/Supervisor readbacks and controlled changed-before-consent rejection.
5. Real Teams mobile/desktop Approve/Deny; ChatGPT fallback with independent OAuth;
   expiry, replay, partial send/restart recovery, original-card update/readback,
   requester visibility, exact provider execution/readback, original detector
   recheck and no PMv4/Ticket Core collateral regression.
6. Complete the existing producer migration and final receiving/invoice matching
   plus service paused/restored integration after core canary acceptance. The
   current PO processor ends at `ordered`; it must not emit whole-purchase
   completion before the owning lifecycle verifies its remaining final gates.

## Integration and release boundary

Original baseline: `2e231c0b5462a2d86abd434ba6074005c4d87c80`.
Reconciled main baseline: `4ba98e05e4512d7accb77595b8e8c05086d8b0a6`. Changes touch runtime
composition, existing procurement flow/maintenance and shared approval sender;
these overlap PMv4/identity/procurement consumers. Preserve active source pins.
No automatic merge or promotion. Risk classification: **High-Risk** because
routing and approval continuation are affected. A full-main runtime promotion is
not an isolated Teams deployment merely because this branch is isolated.

Before release, reconcile relevant active PRs and exact current production
component sources, review the complete delta, select immutable tested candidate
and rollback, verify PMv4/audit recovery state and serialize activation through
existing release control. Do not substitute this source branch for an active
root/audit release candidate. No production approval is requested by this draft.

Rollback: withhold activation; for a future activated component, restore its
exact prior reviewed artifact/config. Retain immutable approvals, submission
claims and provider evidence. A runtime disable stops configured pending work
for review; it must not quietly revert a configured approval to legacy authority.

Related existing work: #1440, #1566, #2043, #2165, #1306, #2015, #699, #1979.
Do not duplicate these projects or close them based on this candidate.
