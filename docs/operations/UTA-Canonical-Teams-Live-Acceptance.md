# Universal Teams Approver — Constitutional Live Acceptance

**Status:** Procedure prepared. Live Approve/Deny acceptance has NOT passed.
**Constitution:** J-002 Article V Integration Before Innovation and ADR-009
authenticated Jason Teams ingress. **Source proposal:** PR #1549.

## Existing transport confirmed in production (2026-10-17)

The deployed Jason MCP capability `communication.teams.message.send` performed
one ordinary status-message send and a separate informational Adaptive Card
send to the Owner's **existing active Microsoft Teams identity**. Each
governed call returned `status=succeeded`, one provider attempt and
`provider=microsoft_teams_gateway`.

An independent Microsoft Teams read located the informational card's
message in the existing **Jason Approval Bot** chat at
**2026-10-17 17:00:41Z**:

- Teams message ID: `1792256441608`
- Governed correlation ID: `corr_mcp_action_adacd23291f94e26b174fe9a79812c46`
- Message text: "Jason UTA constitutional test: informational Teams card sent
  through the existing governed message capability. No approval or customer
  action is requested."

The Graph message proves provider delivery into an actual Teams conversation.
It does **not** prove what the Adaptive Card looked like on a particular
client, that a person read it, or that an approval click round-tripped.

## Constitutional execution and source pin

1. Verify GitHub protected main and the canonical PR #1549 exact head, required
   independent code/security review and all expected CI statuses. **Do not
   substitute or merge the older OAuth-first PR #1548**.
2. Confirm the active Teams bot identity and ADR-009 endpoint remain the only
   ordinary inbound gateway; use existing `/internal/proactive/send` and the
   existing governed `communication.teams.message.send` provider for output.
   No new bot, app registration, OAuth grant, Teams credentials, or parallel
   approval engine is authorized by this work.
3. Through the existing exact-SHA owner-governed release manager, verify CCC,
   production drift, host reconciliation, rollback readiness, and the release
   readback. **No deploy on an unreviewed hash**, no shell/API shortcut to
   alter approval/provider records.
4. Keep existing procurement `procapproval-`, release `relapproval-` and
   playbook approvals working. Their business authorizations remain separate
   from transport delivery and UTA plan approvals.

## Real harmless AOT approval pilot (requires approved activation)

Use a reviewed, protected AOT-only policy whose capabilities are read-only or
nonexecuting acceptance operations; set `production_allowed=false`, explicit
`role_members`, `capability_roles`, low `max_risk`, bounded
`max_ttl_seconds`, and distinct real requester/approver identities.
Recheck both against current active Microsoft-to-Jason bindings and JKD-001.
Never let a requester authorize their own plan.

Issue a fresh, *server-owned* `planapproval-` (or bounded test-prefix)
`ApprovalRequest` through Jason's actual issuance path. The proposal must
include the exact capability, organization, scope, requester, approver list,
risk, expiration, evidence references, and immutable plan digest.

- **Send:** same stored request and server-rendered Adaptive Card, exactly
  one provider send; obtain a real Teams message ID and verify the card
  visually on both Teams desktop and mobile.
- **Approve:** an authorized different AOT human clicks Approve on an
  unexpired card. The SDK gateway authenticates the Teams activity, validates
  tenant and Entra object ID, signs one callback, and existing Jason binding,
  `ApprovalRequestService`, per-step JKD, policy and immutable plan checks
  issue exactly one durable response receipt. Any execution remains governed
  and is restricted to a no-customer-write operation.
- **Deny:** create a distinct fresh request. An authorized human clicks
  Deny. It records one durable denied receipt and executes nothing.
- **Negative tests:** wrong tenant/actor, missing identity, unbound principal,
  disallowed role, requester self-approval, changed card material/plan digest,
  duplicate decision, expired message/request, failed send, disconnected
  gateway, replay after restart, and unexpected provider outcome all fail
  closed without provider mutations.
- **Receipt evidence:** separate provider-accepted, actually delivered,
  clicked/decision received, authorized, and execution states; retain
  original IDs and correlated audit references, never treat
  `message_id` as an approval.

## Finance and cross-workflow proof

After the benign acceptance passes, validate the existing **invoice,
part, quote and PO card** workflows, plus a **supervisor expense request**,
against explicitly reviewed AOT internal role/threshold policy. Confirm
client, ticket, vendor and dollar limits. The finance worker must never
post an expense, invoice or PO solely because the gateway accepted a card;
the existing approved workflow must separately authorize and verify any write.
Test with customer/provider writes disabled first.

For routine internal communications, verify the same shared capability with
technician status, ticket follow-up, billing review and engineering alerts.
No extra human OAuth registration is needed to **send** an ordinary Teams
notification. Higher-risk approvals may require extra independently reviewed
identity assurance, but transport and approval policy remain separate.

## Completion criteria

Do **not** say "UTA fully functional" until (a) reviewed code and policy
were deployed through exact-SHA Owner authorization; (b) actual Teams message,
card, Approve and Deny receipts are documented; (c) wrong-user/replay/expiry
cases fail; (d) original procurement and release approvals still pass; and
(e) the release manager records CCC PASS and a closed, verified state.

The original production revision remains authoritative until new owner
release approval and successful governed readback.
