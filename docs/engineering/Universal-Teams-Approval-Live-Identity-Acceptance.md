# Universal Teams approval: live actor-authentication acceptance

Status: **blocked pending a genuine platform-backed human identity proof and live approval receipt**. This document describes an integration requirement; passing unit tests alone does not activate universal plan approvals.

## Existing live ingress

`infrastructure/jason-teams-gateway/index.mjs` handles Teams `message` activities and card submissions. It reads `activity.from.aadObjectId`, tenant and message IDs, uses a duplicate-decision claim, and emits a machine-authenticated governed conversation envelope. The OpenClaw ingress verifies envelope authenticity, freshness, and replay and forwards `approval.submit` to the approval dispatcher. The production dispatcher currently has no universal handler, so `planapproval-*` fails closed.

## Missing human proof

The signed gateway envelope authenticates **the gateway**, and includes Teams activity identity *assertions*. It does not carry a delegated Microsoft **user token** suitable for `MicrosoftTokenVerifier.verify()`. Never populate `verified_token_source` using the bot application's client-credentials token, tenant ID, AAD object ID alone, a forwarded card field, or a token cached for a different action. The universal dispatcher requires an exact approval, tenant, actor, response receipt binding and independently verified Microsoft token.

The implementation needs a trusted Teams platform activity-authentication design and a documented Microsoft user-authentication mechanism (for example, supported Teams SSO/OAuth user flow), with audience, issuer, tenant, token lifetime, and sender/receipt correlation validated. Ensure tokens are not logged, persisted in plain text, or echoed in card responses. If platform authentication is relied upon without a delegated user JWT, design an explicit separate verifier contract and independent security review rather than silently weakening the existing JWT contract.

**2026-10-17 fail-closed gateway hardening:** Before claiming a one-time approval decision or signing an approval envelope, the SDK-authenticated gateway now requires `channelId=msteams`, explicit `channelData.tenant.id` equal to the configured tenant, a UUID `from.aadObjectId`, and nonempty conversation and activity IDs. Missing tenant is never replaced by the ordinary text-message fallback for an approval. The helper has dedicated positive and negative unit tests. This closes channel/tenant omission routes but **does not** establish an independently verified human OAuth identity or activate universal plan approval.

**Identity-proof completion path:** Use a Microsoft 365 Agents SDK user-authorization handler with an Azure Bot OAuth / Teams SSO connection (or an explicitly reviewed equivalent platform attestation). The human-scoped proof must be tied to the exact activity/callback, Microsoft tenant, AAD object ID, OAuth audience/issuer/expiry, and the immutable pending approval. Treat app-only client-credentials tokens, Teams card data, and a synthetic delivery ID as insufficient. The official SDK describes route-scoped `authorization.getToken(...)`; Teams Adaptive Card SSO requires user token exchange/consent. Relevant vendor references: https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agent-oauth-configuration-dotnet and https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/universal-actions-for-adaptive-cards/enable-sso-for-your-adaptive-cards-universal-action .

## Acceptance (controlled AOT internal test)

1. Persist a server-owned test plan and original governed request. Confirm a single bounded scope and configured approver role. No customer mutation or production release action.
2. Deliver a Teams approval card to an allowed test user and record the actual Teams provider message identifier; synthetic `accepted:` IDs are not delivery proof.
3. Capture a **real** Approve action with authenticated human identity and unique response receipt. Verify tenant/actor and exact plan/receipt binding; audit Microsoft/Teams/JKD decision and issuance of exactly one scoped grant, with no automatic provider mutation.
4. Capture a separate **real** Deny on a fresh proposal. Verify audit persisted, no grant, no execution continuation.
5. Reject missing/untrusted proof, different tenant, different actor, mismatched receipt, expired plan, duplicate response, and replay. Verify on desktop and mobile where supported.
6. Retain draft and no production activation until protected CI, independent security and governance reviews, and live provider receipt readback pass.

## 2026-10-17 verified human-token binding groundwork (development only)

`jason_runtime.teams_human_token_binding.VerifiedTeamsHumanTokenBinding` now supplies
an isolated, **off-by-default** proof boundary. It composes Jason's existing
registered-gateway Ed25519 verifier and Microsoft JWKS-backed token verifier
without introducing a second approval engine or changing live authority.

The only accepted proof pairs the exact signed `planapproval-*` callback
(including the signed message/response receipt) with a **delegated Microsoft
human token**, independently checked for issuer, audience, approved tenant,
expiration, `oid`, `sub`, delegated `scp`, allowed OAuth client `azp`/`appid`,
and MFA evidence. The signed Teams tenant/actor must equal the token's verified
tenant/actor. App-only tokens and cross-user/cross-tenant mismatches fail closed.
The result contains a non-bearer SHA-256 commitment, never the user token.

This change **does not** retrieve the user token, configure Azure Bot OAuth,
activate `JASON_UNIVERSAL_APPROVAL_MODE`, create a test approval, or authorize
a provider execution. The Microsoft 365 Agents SDK user-authorization route
must supply the ephemeral token **from the same actual Teams callback**, and
a reviewed integration must preserve the proof through the existing
one-time approval/JKD execution path. No production rollout or owner approval
may be inferred from unit tests; complete the live desktop/mobile acceptance
steps below first.


## Integrated production fail-closed gate (2026-10-17)

Before `JASON_UNIVERSAL_APPROVAL_MODE=enforced` can compose an approval
runtime, the factory now requires an independent human-proof port with a
`verify_callback` contract. The current production composition intentionally
does not provide such a port: attempting to enable universal mode without
completing the reviewed SDK user-token bridge **fails startup closed**, rather
than treating the registered Teams gateway's signed identity assertions as
independent human authentication. Owner-only mobile release approvals and
existing playbook approval mechanisms are unchanged.

When a genuine human proof source is subsequently installed, each universal
approval callback must provide a token verified through Microsoft JWKS and
the exact signed Teams actor/receipt. The independent non-bearer human proof
digest is retained in a separate protected SQLite table bound to the original
signed transport hash; neither OAuth bearer tokens nor delegated credentials
are retained. Resume/restart workers require the independent proof record
in addition to the authenticated gateway signature, decision audit,
immutable scope, JKD grants, plan ledger and per-step reauthorization. A
missing or changed independent proof blocks execution.

This integration currently uses a **clearly synthetic, test-only** human
proof fixture in its isolated unit tests. That fixture is never instantiated
by production composition. Passing unit tests and CI is **not** live Entra
proof, real Teams acceptance, an OAuth app registration, or permission to
deploy or change approval authority.
