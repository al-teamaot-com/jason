# P0 acceptance: owner approvals in Teams without SSH

**Status:** Required before declaring Jason's Universal Interaction Service production-ready. Source development only; does not authorize a new production approval or change to existing owner-only pilot.

## Product requirement

The AOT Owner must be able to approve **production releases** and **other owner-level workflow decisions** using the existing Microsoft Teams conversation on a phone or desktop, with actionable **Approve** and **Deny** controls.

**The owner must not have to SSH into Jason, run a terminal command, inspect a worktree, or separately enter a CCC/Release Manager command in order to grant a routine approval.** A temporary proof-only manual script is not a substitute for the real operational flow.

The calling workflow supplies the immutable action details, reason, risk, affected systems, exact candidate/hash or object reference, rollback or reversibility, and required owner decision. The existing Jason authority service identifies whether the sender/recipient is permitted and routes the card accordingly. The Universal Interaction Service only presents the content consistently and returns evidence to the **original** governed workflow; it cannot turn a Teams message or card into execution permission.

The approved release subsystem, root-owned processes, and provider capability executors perform permitted work after independent checks. **Owner approval in Teams is not a Linux sudo or root credential.** Any host privileges needed by the action must come from independently preprovisioned, auditable governed service authority. Emergency break-glass may use SSH, but routine owner approval cannot depend on it.

## Two required end-to-end acceptance flows

### A. Exact-SHA production release (normal-risk pilot first)

1. Create a genuine but **non-disruptive** protected test release or release-equivalent review in preproduction, with immutable candidate SHA, rollback SHA, changed surfaces, risk and manifest proof. Never use a fictional approval to deploy real customer code.
2. The existing issuer creates one persisted owner-scoped ApprovalRequest and sends the canonical Adaptive Card through the **existing Teams gateway** to the verified owner.
3. Verify the **real owner sees the card in Teams** on their intended device (desktop/mobile), not just a synthetic `accepted:` transport receipt or posted conversation message. Card must visibly distinguish **ACTION REQUIRED** from ordinary status, show exact material, and display Approve and Deny.
4. **Deny first:** the owner personally presses **Deny**. Confirm signed Bot Framework callback, active Entra-to-Jason identity, authorization, exact immutable request, one-use receipt, and a terminal denied state. Confirm no production or CCC authorization and no execution.
5. Create a **different** harmless approval. Owner personally presses **Approve**. Confirm signed callback and one-use accepted receipt at the appropriate original approval service. Host-side release and CCC gates must run independently. No second owner terminal/SSH step can be required to grant approval.
6. Replay the same callback, alter SHA or request, use expired card or wrong owner identity: all must fail closed. Confirm no double execution or alternative approval.
7. Show the owner an explicit message distinguishing **Decision recorded**, **Processing**, **Verified complete**, and **Failed / human action required**. A recorded decision alone is never a claimed production deployment.

### B. Other owner-level prompt (provider-neutral)

1. Create one **harmless, nonexecuting** owner-level example such as a governed maintenance decision, not a release and not a purchase.
2. The same Universal Interaction contract is constructed from an **existing** ApprovalRequest and routed to the active owner through the same Teams sender, with purpose, impact, choices, scope and expiry.
3. Owner can personally **Approve or Deny** in Teams. The original workflow receives only a verified normalized decision from the original signed callback dispatcher/ApprovalRequestService, **never** an untrusted form field or guessed identity.
4. Employee without approval authority is notified and routed to the actual authorized approver. Cross-client, cross-tenant, forged, duplicated or expired answers cannot proceed.
5. No SSH, shell, GitHub issue comment or ChatGPT instruction is required to complete the owner's routine approval step.

## Risk-tier boundaries (do not silently broaden privilege)

The currently deployed `JASON_RELEASE_MOBILE_APPROVAL_MODE=owner_only_pilot` is limited to approved **normal-risk** release requests and an exact 0600 owner-only policy. This does **not** prove that high-risk or other owner-level approvals are currently supported.

Before broader go-live, each workflow must declare its risk and prerequisites. A high-risk owner request may need additional independently governed confirmation or authentication (for example, authenticated second-step approval), but the owner still should not need to SSH as the routine approval interface. Never lower an approval threshold, weaken CCC, assume human presence from signed transport alone, or expand Entra privileges to satisfy this goal.

When Teams is unavailable, expire/pause safely and provide a **separately authorized secure fallback channel** when available; never auto-approve or tell the owner to SSH as the expected path. An emergency break-glass operation remains a different, separately governed exception.

## Security blockers and proof requirements

- **#1553:** the Owner disputes seeing/pressing an earlier release approval, even though a signed account-bound callback exists. Investigate device-visible card/notification and Bot Framework callback provenance before declaring trust.
- **#1554:** release/owner-level high-impact approval containment must be proven fail-closed. Keep normal messaging intact.
- **#1549 / #1555:** the universal approval source and generic owner presentation mapping are development work. Default flags must remain off until exact authorized activation.
- **#1552:** generic Teams conversation-intent routing must not intercept approval responses or owner queries.
- A signed callback and ledger receipt prove authenticated electronic evidence; they **do not by themselves prove the owner personally clicked**. For first acceptance, obtain the Owner's direct confirmation and independently correlate the real Teams client action, incoming Bot Framework activity, one-use receipt and originating workflow outcome.
- The approved acceptance evidence must contain timestamps, actual provider message ID (if available), exact approval ID and source SHA (for release), signed activity reference, identity/tenant validation, audit event and host-side result; never print signature material or credentials.

**Release rule:** Do not declare production or generic owner-level Teams approvals operational until the Owner has successfully completed both real-world workflows **without SSH** and all negative security cases have passed. Any subsequent rollout requires normal source review, protected CI, exact-SHA Owner authorization, CCC, root host reconciliation and rollback.

## Nonexecuting owner acceptance campaign (prepared; NOT active in production)

A safe test-only workflow is prepared in source through the same universal interaction contract and existing Teams sender. There is no second bot, OAuth application, provider capability, approval database, or callback endpoint. The sender uses an existing persisted ApprovalRequest, and the callback uses the existing signed dispatcher, Ed25519 verifier, Microsoft/Jason identity binding, and ApprovalRequestService.

Campaign configuration, all disabled by default:

- JASON_OWNER_UAT_MODE=nonexecuting_test_only
- JASON_OWNER_UAT_WORKER_ENABLED=true (single card issuance through existing runtime maintenance; false keeps callback-only routing)
- JASON_OWNER_UAT_SESSION_ID=unique-bounded-session-identifier (one immutable request per ID; never automatically resend)

Defaults remain mode OFF, worker false, empty session. The UAT request is exactly capability interaction.owner.acceptance.record, mode test:nonexecuting, owner person-al, requester svc-jason-acceptance-test, 10-minute TTL, and immutable test_only=true plus execution_permitted=false. This cannot be a production release, CCC, procurement or ticket authorization.

Live test: (1) After separately owner-approved exact-SHA test deployment, create one session. Owner personally sees TEST ONLY in Teams and clicks Deny. Independently verify signed callback, active owner binding and one durable DENIED receipt, with no provider execution. (2) Use a DIFFERENT session ID and have owner personally click Approve. Verify signed callback and an APPROVED test-only receipt, again no execution. Confirm owner visibility, not merely a provider-accepted transport reference. (3) Reject unsigned/tampered, wrong account, expired, duplicated and replayed responses; no cross-tenant or extra capabilities.

Source and automated security tests cannot establish a real human click. The disputed approval provenance #1553 and governed containment #1554 remain high-impact rollout blockers. A normal-risk release still requires exact SHA, CCC, root host reconciliation and rollback. Owner interaction never requires an owner SSH session.
