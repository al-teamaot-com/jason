# Owner Teams test-only acceptance session — 2026-10-20

**Status: source-only, not sent to Teams or activated in production.** Related #1440, #1545, #1553, #1554.

The active protected main e658934a7eeffd430f09e44e03fdbf5885424093 holds a release-eligible but **not owner-approved** Teams release. Its immutable owner UAT campaign expired October 19, so the correct source-pinned validator currently outputs off|false|none; merely deploying that candidate would not send the required real-world acceptance cards.

## Minimal source refresh

Refresh **only** the separate, source-pinned config/owner-uat-campaign.json session to OwnerUAT20261020NoSSH01, with expiry **2026-10-22T02:00:00Z**. Preserve the existing aot organization, person-al recipient, svc-jason-acceptance-test requester, strict interaction.owner.acceptance.record capability, execution_permitted=false, the validated Git blob, and 48-hour maximum campaign period. Only the existing JASON_OWNER_UAT_* environment values can be derived through canonical deployment; no broader JASON_UNIVERSAL_APPROVAL_MODE, Teams gateway, or protected release authority is added.

Source tests verify eligibility only within the window, expiry at the exact boundary, fail-closed when a campaign exceeds 48 hours, and enforced off in preproduction. The existing UAT unit tests independently verify the signed owner identity, tenant, one-use persisted receipt, separate Deny then Approve cards, no resends, and **no** ticket, device, financial, CCC, or production execution path.

## Critical rollout boundaries

1. Preserve the existing closed c62da59e production release as root-verified last-known-good and its active auto-promotion hold.
2. Protected CI, exact-source preproduction/rollback and individually scoped owner production/CCC authorization are **mandatory** for any new merge SHA. An earlier exact-SHA release grant cannot be inherited.
3. The universal UAT issuer can dispatch its **first nonexecuting card only AFTER** its exact running revision has a closed independent release record with production CCC PASS and matching root-owned LKG readback. It may then ask the Owner to personally press **DENY** on the first test, and **APPROVE** on the separate follow-up, before each 10-minute card expires. Buttons cannot authorize a real action.
4. The Owner must independently confirm the card appeared in the intended Teams client and they personally pressed each button. A signed gateway callback and provider-accepted receipt are electronic evidence, not physical human presence. The older disputed high-risk callback #1553 remains a separate security investigation.
5. Do not activate high-impact release approval V2 policy, clear a containment hold, lift root release safeguards, or claim Universal Teams Approver live acceptance from a source-only test.
6. If the campaign expires before reviewed deployment, it remains **off**, and a fresh separately reviewed source campaign is needed; never edit a live image, manifest or approval timestamps to extend it.

This limited acceptance exercise does not claim production approval of the release, human Teams acceptance, or the broader one-approval-per-plan product.
