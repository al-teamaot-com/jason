# PMv3.2 — Single governed owner approval using Teams notice + Entra admin sign-in

**Classification:** HIGH RISK — Owner authentication, delegated authority,
release/rollback and protected production freeze. **Status:** isolated
source-only security groundwork. **Tracking:** #2376, #2377 and
`release-65e2f18b051e3dda`.

## Owner requirement

The Owner explicitly confirmed on 2026-11-08 that
`al_admin@teamaot.com` is **intentionally unlicensed and cannot use Teams**.
Never treat licensing this account as a repair prerequisite, nor purchase or
move Microsoft 365 seats to make Jason approval work.

The correct single process is:

1. Jason's **existing** Teams gateway sends an *informational, non-approving*
   release-approval notice to the already licensed regular account
   `al@teamaot.com` (Entra OID
   `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`). A Teams notification is
   never release authority; the notice must contain no actionable approve/deny
   `Action.Submit`, no approval bearer credential, and no unverified
   cross-account fallback.
2. A verified HTTPS link opens the **existing** Jason auth-host boundary,
   which starts a fresh Microsoft Entra authorization-code + PKCE + OIDC
   transaction. Owner authenticates as *the separate enabled but unlicensed*
   `al_admin@teamaot.com` (OID
   `c848022d-e13b-4457-84b0-e2f5c00dcaf6`), same exact tenant
   `f7054323-d52b-4863-8c2f-1898f0b6077c`.
3. The server verifies state, nonce, code_verifier, short session TTL,
   token cryptographic signature from Microsoft JWKS, exact `iss`, `aud`,
   `tid`, `oid`, token `exp`, `nbf`, `iat`, `auth_time`, and an
   explicitly requested Microsoft Entra Conditional Access authentication
   context (MFA/step-up) through the ID-token `claims` parameter.
   **The presence of an `acrs` value alone does not prove MFA.** Microsoft
   may issue the claim when there is no tenant Conditional Access policy
   protecting that context. Before any live activation, an independently
   verified tenant policy must prove this exact context actually enforces
   appropriate MFA/step-up for the admin application. Missing context or
   missing independent policy proof denies.
4. Show the exact approved release SHA, scope digest, rollback SHA, release
   manifest digest, expiration, and pending ID. Owner explicitly chooses
   approve or deny while *admin-authenticated*. The link and regular Teams
   identity alone **cannot** approve anything.
5. Bind that decision to the existing shared
   `ApprovalRequestService` and its immutable exact release subject. The
   existing root-trusted evidence consumer independently verifies a new,
   versioned **`microsoft_entra_browser_stepup`** signed evidence type
   against the same Owner policy. Preserve one-use and expiration rules,
   CCC, release lock, production freeze, native rollback and postflight.
   There must be only ONE Owner decision per exact release, not a second
   approval service or standing release permission.

## Source established by this change

`implementation/mcp_service/src/jason_mcp/entra_release_stepup.py` provides
**non-activated pure proof-building primitives**, including:
- immutable and strictly separated Entra account roles;
- exact release tuple validation and SHA256 fingerprint binding across a
  browser sign-in, so changing scope while awaiting the callback fails;
- random short-lived `state`, `nonce`, PKCE S256 verifier, tenant-scoped
  `prompt=login` OIDC URL and exact reviewed HTTPS redirect;
- safe regular-account Teams notification descriptor **with no approval
  actions**;
- independent RS256 JWKS ID-token verification of exact admin OID/tenant,
  nonce, fresh `auth_time`, bounded source TTL and explicit CA/MFA context;
- the result is **identity evidence only**, marked
  `release_authorized=False`. It does NOT create a decision or authorize a
  production transaction.
- `jason_mcp.entra_release_browser_sessions.OneTimeBrowserLoginStore`
  implements a private 0600 server-side SQLite login session ledger. The
  browser cookie is random and stored only by SHA256, the PKCE verifier/
  nonce/state never leave the server, exact release fingerprint is locked,
  one-time use is enforced in a transactional consume, and invalid state,
  wrong cookie, scope tampering, stale/expired or replayed sessions fail
  closed. The adapter must set `Secure; HttpOnly; SameSite=Lax`; this
  library **does not** establish an HTTPS web route or actually set a cookie.
- `jason_mcp.entra_release_code_exchange.redeem_admin_browser_code`
  performs the exact tenant-specific confidential-client **authorization-code
  + PKCE redemption** after the one-time browser session is consumed.
  The requested scope is only `openid profile`; the redirect is pinned to
  the separately reviewed callback. It validates Microsoft's signed ID
  token through the exact admin verifier and never returns the authorization
  code, secret, access/refresh token or raw ID token. A provider error or
  token exchange failure is generic and cannot become an approval.

The old #2377 admin Teams-license preflight is only a defense against a
misleading message-ID receipt. It is not the end-to-end remedy for this
unlicensed privileged account. No production should be deployed solely to
reproduce an unlicensed admin delivery failure.

## Unimplemented integration — release gates

**Do not treat these source helpers as a working approval flow yet.**

- Verify or register an appropriate *confidential-client* Entra application
  redirect for
  `https://mcp-jason.teamaot.com/admin/release-approval/callback`.
  The code rejects any arbitrary redirect URI. Do not assume a redirect is
  registered merely because Jason's MCP OAuth is functional.
- Implement the server-side, secure `HttpOnly; Secure; SameSite=Lax`
  HTTP cookie/session adapter on top of the existing protected one-time
  store, connection to the separately registered confidential OAuth client,
  CSRF and callback replay checks, Entra signing keys and token storage
  restrictions. The tested code-exchange helper does not perform web routing. Use a mature auth library as appropriate; no access
  or refresh tokens in Teams URLs, cookies or durable approval evidence.
- Verify the configured tenant Conditional Access authentication context
  forces suitable step-up/MFA for the privileged account; context absent or
  unverified must block.
- Update the existing approval interaction dispatcher and independent
  protected host consumer to accept the **new explicitly versioned and
  cryptographically authenticated channel**. Current V4 `policy_mode
  admin_approver_separated` root policy and host consumer allow **signed
  Teams only**, so do NOT inject web evidence into them or relabel it
  `microsoft_teams`.
- Obtain the normal exact source SHA, protected CI, isolated preproduction,
  signed Owner authorization under a *valid existing channel*, and guarded
  one-transaction production release. If the V4-to-next-version bootstrap has
  no currently valid authorization channel, escalate for an explicit
  reviewed, human-authenticated transition—never self-unfreeze, edit SQLite,
  change the root policy or forge a Teams card.

## Negative acceptance before production

- Regular Teams account cannot approve, even with the URL or a forwarded link.
- Malicious redirect, forged or stale nonce/state, wrong app audience,
  different tenant, wrong admin, wrong JWT signature, non-RS256 algorithm,
  missing MFA context, stale `auth_time`, expired release and changed
  candidate/scope/rollback/manifest are rejected.
- Approval ID is not a bearer token; a non-authenticated caller cannot issue
  a decision. Replayed browser callback or browser form submission is denied.
- Signed approval evidence must be original, exact, bounded and independently
  host-verifiable, with no regular-account substitution.
- Root freeze, auto-promotion hold and engineering Owner pause remain intact
  until each separately authorized release transaction.
- Live acceptance must use a valid admin browser sign-in and independently
  observed Teams notice to the licensed regular account; no claim of live
  completion from synthetic unit tests.

## Current operational state

As of this source groundwork, the previously prepared
`release-65e2f18b051e3dda` has **no signed Owner decision**. The production
candidate remains undeployed; PMv3.2 integration remains release-locked,
and Company `1158` has no live `enable_jason_outbound_comm` UDF value.
Source-only code does **not** fix this without registered auth callback,
reviewed root approval-policy migration and live acceptance.
