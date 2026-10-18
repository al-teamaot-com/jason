# P0 Teams approval for protected releases: opt-in owner-reviewed channel

**Parent issues:** #1440 (Teams approval), #1545 (live universal acceptance),
#1078 (Production Manager), #1565 (evidence-first status reporting).
**Status:** Source-only candidate, NOT deployed, NOT enabled, NOT yet verified
for a protected-core production release.

## Precise observed boundary

On 2026-10-18 the AOT Owner completed a real, signed Teams TEST ONLY DENY
and APPROVE pair (durable records; neither executable). A separate production
release relapproval owner click for source ad11c311... completed via the
existing Teams owner pilot and independent CCC + Release Manager closeout.
These prove the owner-only Teams ingress can work. They do not establish
Universal Teams Approver activation for all workflows.

The deployed owner-only release pilot uses a private 0600 v1 policy with only
allowed_risk_profiles=normal. Its runtime mode is owner_only_pilot. More
importantly, the official release-manager offer publisher hardcodes
risk_profile==normal. The merged Production Manager changes include root
release-control code, correctly classify as production_control_core, and
cannot acquire an actionable Teams card through the existing pilot. A normal
Teams notification cannot substitute for a signed release approval.

This is a concrete workflow gap and a source of misleading claims that
'Teams approval is operational' for any type of release.

## Narrow source repair (no production activation)

- Retain v1 policy exactly, normal-risk only. No silent behavioral upgrade.
- Introduce an **explicitly reviewed v2** policy mode owner_reviewed. Its
  private versioned policy must name AOT organization, the sole Owner identity,
  exact permitted risk profiles, a 300-900s TTL, and four mandatory safeguards:
  exact SHA, signed Teams identity, independent CCC and unchanged release gates.
- Separate runtime mode owner_reviewed is required for v2. If the running
  container's actual mode does not match the versioned policy, the host
  publisher does not create an approval offer. The runtime issuer and callback
  also reject a mode/version mismatch. Changing a policy file alone is not
  activation.
- The existing server-persisted release metadata and immutable manifest,
  exact source/rollback SHA, policy hashes, existing Microsoft Teams signed
  gateway proof, Owner binding, single-use receipt, hold/replay checks, and
  the independent host release+CCC decision consumer remain in charge. A card
  is not a release permission and an Owner click is not CCC PASS.
- Explicitly mark the release owner-approval runtime/host proof modules as
  protected-core in the policy and risk classifier. Any amendment needs an
  exact-SHA Owner-gated production promotion.
- Emit a specific, honest ineligible channel reason (reviewed policy
  excludes risk, or running mode mismatch) rather than treating activity
  or a generic Teams send as an actionable approval.

## Source and release acceptance

Before enabling v2, independently review the specific AOT Owner decision
to allow protected_core and/or other listed risk classes over the current
signed Teams owner channel. This channel permission is NOT a standing
approval for future releases: each release still needs one exact-SHA human
Approve action. Whether additional live human assurance is necessary for
high-impact classes must be explicitly reviewed; do not claim MFA or
delegated SSO from bot transport signature alone.

**One-time bootstrap limitation:** Current production does NOT have this v2
logic. The first release containing it cannot be authorized by a protected-
core Teams card that the current production code is incapable of issuing.
The bootstrap needs existing independent exact-revision Owner authorization
and normal governed CCC/preproduction/rollback safeguards. Do not
misclassify it as normal risk, fake a Teams click, use a test-only receipt,
or silently change the running 0600 authority policy. After the code is
deployed and reviewed v2 policy plus matching runtime mode are deliberately
activated, all subsequent exact protected-release approvals may use Teams
subject to the verified authority and individual click.

Prove all of the following before marking protected release approval ready:
1. Current v1 normal-risk owner pilot remains usable and high-risk denied.
2. Reviewed v2 and matching live runtime mode are both active; pending
   protected-core candidate on GitHub main has passed isolated preprod,
   rollback, health, protected checks and release eligibility.
3. Real Teams owner sees exact SHA, risk, file/manifest, LKG rollback and CCC
   explanation; real signed Approve yields one exact release owner grant and
   CCC *material review* (not CCC certification).
4. Official Release Manager independently validates the latest protected
   source, runs fresh CCC, deploys, verifies host/runtime/MCP, checks drift and
   function smoke, records closed LKG. A denied request never deploys.
5. Wrong actor/tenant, policy drift, stale SHA, expired nonce, replay and
   version mismatch all fail closed without production/CCC grant.
6. Current Universal Teams Approver plan mode can remain OFF while this
   specific release lane is operational. Broader shared approval workflows
   require their own acceptance and must not be labeled operational early.

## Communication status contract

Use separate labels for (a) source-coded, (b) GitHub CI/merged,
(c) deployed, (d) reviewed v2 policy + live mode enabled,
(e) real owner Teams Approve/Deny proof,
(f) signed approval consumed into CCC and exact release gate, and
(g) full protected release closeout/rollback verified.

Until step (g) **Protected-core approval via Teams: NOT OPERATIONAL.**
Until independently verified universal plan routes pass all workflows,
**Universal Teams Approver: NOT OPERATIONAL**, even if release-only lane passes.
