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

## Acceptance and limits

Latest local verification: **255 tests passed** across the targeted runtime,
composition, procurement, canonical approval/security and architecture suites.
Engineering standards, documentation control, compilation and diff checks PASS.
No provider/production calls were used in these tests. Separately, governed
read-only Contact and Entra checks succeeded. Autotask numeric spending UDFs
use four decimal places: parser acceptance now allows exact trailing zeros
without rounding fractional cents. The current internal Contact query returned
45 records (29 active), with no Supervisor assignments yet. No contact values,
limits or reporting relationships were modified. The configured fallback is
therefore necessary until verified relationships are entered.

The live exact-Owner authority probe rejected with
`AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED`; MCP reports protected production approval
evidence unavailable or mismatched. No authority/grant/profile change or
authentication bypass was attempted. Live Owner-path acceptance depends on the
existing governed identity/recovery work; this draft cannot authorize itself.

Offline coverage: business hours, weekends, holidays, DST, one-business-day
escalation, expiry/renewal, denial, policy reload, stale routing rejection,
no second consent on presentation-only edits, insufficient supervisor limit,
cycle/cross-company/inactive/ambiguous fallback, requester non-action copy,
second configured approval template, concurrent/restarted send claims and
unknown delivery. Existing procurement, shared sender, playbook and composition
regressions must also pass before publication.

These are source/fixture tests, not Teams/provider-backed acceptance. Do not claim
all workflows migrated or real approvals/notifications operational from these tests.

The current PO processor ends at `ordered`, not invoice/receiving completion.
Do not send a whole-purchase completion notification at that intermediate state.
The lifecycle owner must emit it only after its verified final readbacks.

The following remain release-blocking integration/operational acceptance:

1. Real active AOT requester/supervisor/Owner roster and exact role review; fresh
   Contact UDF/spending readbacks. Source re-reads the relationship and spending
   limit under the actual signed approver identity before accepting consent, and
   rejects changes before recording a decision; prove this on real controlled data.
2. Recovery/reconciliation of an interrupted replacement after canonical cancel
   or an ambiguous partial send. The safe current disposition is blocked, never
   repeating a possibly delivered card or continuing execution on assumed consent.
3. Existing independently authenticated ChatGPT-to-canonical-receipt bridge;
   procurement currently accepts its signed Teams receipt only. Do not relax that
   receipt guard or claim fallback is active until the real bridge is verified.
4. Existing gateway transport sends cards but does not currently edit the original
   card to a terminal state. Signed replay rejection is retained; visible terminal
   card updates and all-producer migration still need their provider-backed seam.
5. Completion integration across receiving/invoice matching and approved service
   paused/restored producers; no false "completed" event at PO submission.
6. Teams desktop/mobile real Approve and Deny, expiry, wrong actor/tenant, replay,
   restart, send/readback failure, requester visibility, exact controlled provider
   execution/readback, original detector recheck and no collateral regressions.

## Integration and release boundary

Baseline: `2e231c0b5462a2d86abd434ba6074005c4d87c80`. Changes touch runtime
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
