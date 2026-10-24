# Universal Teams approval: live actor-authentication acceptance

Status: **blocked pending a genuine platform-backed human identity proof and live approval receipt**. This document describes an integration requirement; passing unit tests alone does not activate universal plan approvals.

## Existing live ingress

`infrastructure/jason-teams-gateway/index.mjs` handles Teams `message` activities and card submissions. It reads `activity.from.aadObjectId`, tenant and message IDs, uses a duplicate-decision claim, and emits a machine-authenticated governed conversation envelope. The OpenClaw ingress verifies envelope authenticity, freshness, and replay and forwards `approval.submit` to the approval dispatcher. The production dispatcher currently has no universal handler, so `planapproval-*` fails closed.

## Missing human proof

The signed gateway envelope authenticates **the gateway**, and includes Teams activity identity *assertions*. It does not carry a delegated Microsoft **user token** suitable for `MicrosoftTokenVerifier.verify()`. Never populate `verified_token_source` using the bot application's client-credentials token, tenant ID, AAD object ID alone, a forwarded card field, or a token cached for a different action. The universal dispatcher requires an exact approval, tenant, actor, response receipt binding and independently verified Microsoft token.

The implementation needs a trusted Teams platform activity-authentication design and a documented Microsoft user-authentication mechanism (for example, supported Teams SSO/OAuth user flow), with audience, issuer, tenant, token lifetime, and sender/receipt correlation validated. Ensure tokens are not logged, persisted in plain text, or echoed in card responses. If platform authentication is relied upon without a delegated user JWT, design an explicit separate verifier contract and independent security review rather than silently weakening the existing JWT contract.

## Acceptance (controlled AOT internal test)

1. Persist a server-owned test plan and original governed request. Confirm a single bounded scope and configured approver role. No customer mutation or production release action.
2. Deliver a Teams approval card to an allowed test user and record the actual Teams provider message identifier; synthetic `accepted:` IDs are not delivery proof.
3. Capture a **real** Approve action with authenticated human identity and unique response receipt. Verify tenant/actor and exact plan/receipt binding; audit Microsoft/Teams/JKD decision and issuance of exactly one scoped grant, with no automatic provider mutation.
4. Capture a separate **real** Deny on a fresh proposal. Verify audit persisted, no grant, no execution continuation.
5. Reject missing/untrusted proof, different tenant, different actor, mismatched receipt, expired plan, duplicate response, and replay. Verify on desktop and mobile where supported.
6. Retain draft and no production activation until protected CI, independent security and governance reviews, and live provider receipt readback pass.


## Phase-bound universal-plan card provenance hardening (P0 #1440)

General `planapproval-*` approvals now require a new 192-bit random
`card_instance_challenge`, stored with its SHA-256 checksum in the immutable
server-issued `ApprovalRequest`. The existing Teams Adaptive Card inserts the
challenge as an `Action.Submit` field; the authenticated gateway must sign
that selected field, and runtime independently verifies the exact issued
challenge and digest **before** an approval can create a plan grant or enqueue
execution. Missing, stale, mismatched, swapped, cross-tenant, malformed or
unreviewed card submissions must fail closed; decision replay is still
governed by the existing atomic ledger.

**Trust boundary:** A card challenge is *not* an OAuth human JWT, proof of
Microsoft Teams message-origin ID, MFA, or proof that the Owner personally
clicked. The unresolved historical provenance case #1553 remains separately
open. This source-only implementation does not enable
`JASON_UNIVERSAL_APPROVAL_MODE=enforced`, provide a production routing policy,
authorize any reboot/PO/client message, or substitute for live negative UAT,
Owner approval, CCC, and governed release controls.
