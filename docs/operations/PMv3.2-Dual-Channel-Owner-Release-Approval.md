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

## Configuration-driven identity and destination policy (no hard-coded people)

Jason's core implementation must **never** contain `person-al`, an AOT
admin username/email, a specific Entra Object ID, or a fixed AOT hostname
as an authorization condition or default. This is not an Al-specific
feature. The same governed process must work for another appropriately
authorized technician/Owner, another tenant and a different registered
approval host, without rebuilding the code.

- Access and capability eligibility come from the **reviewed Entra security
  group IDs**, the canonical Jason authority model and the signed/reviewed
  organizational policy. Do not infer authority from group display names,
  usernames, email suffixes or a Teams message recipient. The future web
  adapter must verify the actual group membership and per-release Owner
  eligibility using authoritative Entra data before issuing the approval.
- The **exact final privileged signer** must be bound to the reviewed
  privileged role and current Entra Object ID, checked again against the
  fresh OIDC login claims. Unlicensed administrator accounts are supported:
  Teams entitlement is required for the *notification* account only.
- The single `ReleaseIdentityRoute` now has **required policy inputs**:
  `tenant_id`, `regular_teams_oid`, `admin_approver_oid`,
  `owner_subject_id`, `registered_redirect_uri`, and `notice_uri`.
  There are **no deployment-specific defaults**. The two HTTPS approval
  URLs must have the same validated origin, fixed application route paths,
  no arbitrary port, credentials, query strings or fragments. The token
  redemption uses that exact policy-bound registered redirect.
- The account names and Object IDs above are a **current incident
  reference**, not an allowlist compiled into Jason. They belong in
  versioned, root-governed organizational bindings. Test fixtures use
  synthetic identities and example domains; a second tenant/Owner/host
  must pass identical tests.
- A generic or self-reported `owner_subject_id`, group ID, or route object
  is **not itself an authority grant**. Until the existing release
  authority, group proof, root policy and native host consumer are
  integrated, all these pure functions remain dormant.

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

## Source-only browser HTTP adapter (2026-11-09)

`jason_mcp.entra_release_browser_http.AdminReleaseBrowserAdapter` now
provides a **non-mounted**, dependency-injected Starlette HTTP implementation
of the existing one-time session and confidential Entra code-exchange
primitives. Its ordinary-request route is the reviewed
`/admin/release-approval`, and its callback is exactly
`/admin/release-approval/callback`. The notice page has no approval action.

The adapter refuses every request until a **trusted independent Conditional
Access/MFA enforcement attestor** returns strict True. It validates exact
HTTPS host/path against the reviewed route, checks form Origin, limits body
size, denies polluted parameters, sets a Secure+HttpOnly+SameSite=Lax
`__Host-` cookie, consumes the exact session before code redemption,
clears the cookie on callback, and never reflects OAuth codes, JWTs,
client secrets or PKCE into its response. Its successful response is
**identity verified / no release approved**; the underlying
`verified_admin_signin` evidence remains `release_authorized=False`.

A new opaque-cookie hash lookup on `OneTimeBrowserLoginStore` resolves the
correct **server-stored** approval ID; a URL parameter or forwarded
Teams notice cannot choose which release is consumed on callback.
The callback re-reads the immutable exact release before atomic consumption.

The HTTP adapter remains intentionally **UNMOUNTED** in `server.py`.
It does not load a production policy, register the Entra confidential
client, attest a live CA authentication context, expose an approval UI,
sign an approval decision, or modify the host Release Manager. This is
security preproduction, not an actionable owner approval.

Tests run with a completely offline, isolated copy of the MCP runtime's
Starlette/AnyIO source dependencies and synthetic identities/hostnames,
without contacting Microsoft or altering running containers. The tests
cover nonactionable notice, unverified CA, CSRF Origin, parameter
pollution, exact registered redirect, secure cookie, one-time callback,
replay, wrong state, and exact release-scope changes during login.

## Explicit administrator consent and independent V5 evidence (2026-11-09)

Source-only security primitives now also distinguish **successful Entra
authentication from an explicit administrative approval**. The new
`OneTimeAdminDecisionStore` creates a private 0600 short-lived consent
session only after the previously verified privileged Entra login. The
browser displays the exact candidate and rollback SHA and requires a separate
same-origin, CSRF-bound `approve` or `deny` POST. The consent cookie is
Secure, HttpOnly, SameSite=Strict and one-use. An unavailable signer or
evidence sink blocks the POST; failed/forged CSRF cannot consume a valid
session. Neither a Teams notification nor a successful OAuth callback
can automatically approve a release.

`entra_release_browser_decision.py` implements a versioned **V5 source-only**
Ed25519 envelope bound to exact pending approval ID, candidate and rollback
SHA, reviewed scope and manifest digests, tenant, privileged OID,
canonical owner subject, fresh login, decision, nonce and expiry. The
independent verifier accepts *only* trusted reviewed public key IDs and a
valid signature over canonical bytes. Its result deliberately contains
`release_authorized=False`. Private signing keys are NOT committed, generated
in production, or provided with this PR. The actual signer and public key
must be enrolled through governed OpenBao/root policy only after explicit
approval, not from an environment-supplied or arbitrary user key.

The explicit decision hand-off now uses a **private SQLite signed-evidence
outbox**: signing precedes one atomic transaction that consumes the
one-use consent and stores the exact signed envelope/digest. A sink failure
does not lose the user's authenticated decision; a separate governed,
idempotent ledger reconciler may re-deliver exactly the SAME signed envelope
and acknowledge its SHA-256, without issuing another approval or duplicating
authority. Concurrent browser sessions for the same immutable approval ID
cannot record contradictory decisions. The browser itself does not run
background recovery: a protected native worker must be wired into the
existing ApprovalRequestService before activation.

The V5 browser decision is still **not accepted by the existing V4
Release Manager consumer**. It must be incorporated into the *existing*
`ApprovalRequestService` signed decision lifecycle, with atomic
nonreplay, signed root policy migration, CCC, freeze transaction,
and independent exact-key verification. **Do not treat this evidence
primitive as a standing release grant.** No live HTTP routes are mounted.

The isolated ASGI and cryptographic source tests cover full login-to-decision
hand-off, authentication-vs-consent separation, unlicensed normal account
impersonation, unavailable signer, forged CSRF, replay, wrong signing key,
expiry, changed SHA/scope/manifest, and revoked CA attestation. SEC-007
now requires all five component regression suites.

## Protected host trust for V5 browser signatures

`kernel.entra_release_root_trust.read_root_browser_release_trust` now
provides a **read-only, fail-closed** parser for a future reviewed 0600
root-owned signing-key trust manifest. There is no default key, no embedded
tenant/owner identity, no private signing key on the host and no code path
that writes this manifest. Independent host tests prove the approved
Ed25519 public key verifies the exact signed browser decision while a
wrong key, unreviewed trust policy hash, alternate tenant/admin OID,
symlink, world-readable file, duplicate key or malformed key fails.

This is an additional **independent trust primitive only**. No V5
root policy is installed and the V4 release consumer continues rejecting
all non-Teams evidence. A decision becomes operational only after separate
governed policy migration and integration with the existing approval
ledger, CCC and one-transaction freeze controls.

## Required tenant evidence before any live V5 approval route

The newly available, delegated administrator Microsoft Graph read confirmed
that AOT_OpenClaw has **no Web redirect URI**, and the tenant currently
returns **zero authentication-context references**. No live CA policy has
been verified to enforce context-specific step-up on this route. The prior
privileged-user authentication method read returned HTTP 403. These are
**real tenant configuration and authorization dependencies**, not reason to
silently assume `c1` is MFA. See the live read-only inventory below.

The separately privileged tenant administrator must verify/create a reviewed
confidential Web app registration with the **exact** registered HTTPS redirect
`https://mcp-jason.teamaot.com/admin/release-approval/callback`
(or a separately reviewed deployment-specific URI; never hard-coded into
reusable source). A server-side confidential credential belongs in the
existing governed OpenBao secret store and must not be pasted into chat, Git,
Teams, or browser URLs. The available source code currently supports the
client-secret OAuth redemption variant; certificate-based client assertions
would require an additional reviewed implementation.

The tenant administrator must also confirm that an authentication-context
reference `c1` through `c99` is actually assigned an enabled Conditional
Access policy requiring suitable MFA for the exact privileged signer and
application, and that the tenant has the necessary Entra ID P1 rights.
A configured context label, `acrs` JWT claim or sign-in method list by
itself **does not prove** enforcement. Only independently verified live
CA policy and login evidence can enable the policy attestor.

Microsoft source references:
- https://learn.microsoft.com/en-us/entra/identity-platform/developer-guide-conditional-access-authentication-context
- https://learn.microsoft.com/en-us/entra/identity-platform/msal-client-application-configuration
- https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow

Before activation the **same existing** ApprovalRequestService and native
root Release Manager must accept an explicitly versioned V5 decision under
its own root policy, protected signer trust, nonreplay, exact release scope,
CCC and one-transaction freeze. The V4 signed-Teams-only policy is intact,
and the new V5 source cannot approve a release on its own. This requires an
independently reviewed Owner policy transition, not an ordinary Teams
notification or a code-only edit.

## Live AOT Entra inventory, read-only (2026-11-09)

A separately authenticated `al_admin@teamaot.com` delegated Microsoft Graph
session was successfully reused through the supported `CurrentUser` MS Graph
cache on the user's Windows PC. Queries were read-only; no tenant policies,
applications, credentials, or production controls were modified.

- The existing **AOT_OpenClaw** single-tenant application has application ID
  `84bd25c4-2f7e-4d55-8db3-14e7c21e3b33`, two active registered client
  credentials expiring in March 2028, and **no configured Web redirect URI**.
  Existing credential usage was *not* established. Do not overwrite, remove,
  rotate, or repurpose it until its workload owners/dependencies are verified.
- The service principal was enabled, with zero assigned app roles and zero
  granted delegated scopes in the queried inventory. This does **not** prove
  that its existing client credentials are unused or safe to share.
- Graph `GET /identity/conditionalAccess/authenticationContextClassReferences`
  returned an empty collection. No tenant authentication-context `cX` is
  available to satisfy V5's mandatory explicit CA step-up claim. No default
  `c1` may be assumed or fabricated.
- Multiple enabled Conditional Access MFA policies target all cloud apps.
  **The privileged admin is explicitly excluded** from several, including
  the policy `M365 - Require MFA + 8h reauth` and `[All cloud apps] GRANT:
  Require MFA for All users`. The enabled `Require multifactor authentication
  for admins` policy contains applicable admin role IDs and has no explicit
  user, role, group, or application exclusions; however, role assignment,
  policy conditions and a live sign-in have not been independently attested.
  Hence **MFA for the exact V5 browser approval is not yet verified**.

**Required next gated actions:** independently confirm existing OpenClaw
credential dependencies; select a dedicated confidential browser sign-in
identity if extending the existing app would risk workload isolation; prepare
and review an exact redirect + client-credential enrollment; configure and
verify a named CA authentication context requiring fresh admin MFA; then
perform an isolated preproduction sign-in and binding test. Any tenant
configuration requiring approval must use the Teams-governed process; a Teams
notification cannot by itself authorize production release. The existing V4
root signed-Teams-only policy, production freeze and engineering Owner pause
remain controlling until separately authorized V5 transition and release.

## Read-only existing host release-consumer attestation (2026-11-09)

`tools/verify_browser_release_evidence.py` now adds a pure, non-activated
verification function usable by the **existing** host Release Manager consumer
once a distinct reviewed V5 root policy exists. It requires exact
`policy_version=5.0`, currently PENDING `ApprovalRequest` from the
native release manager, one governed Owner identity, exact reviewed policy
hash, candidate SHA, rollback SHA, manifest, scope, request TTL, and
`entra_browser_admin` channel metadata. It independently loads only the
root-reviewed mode-0600 Ed25519 trust manifest and verifies the browser
signature and exact administrative Entra OID. The result remains
`release_authorized=False`; no approval ledger mutation, CCC review,
release unlock, or signed Teams impersonation is performed.

20 host negative/positive tests are mandatory in the protected SEC-007
security workflow. This verifier is **NOT** invoked by the live V4
signed-Teams-only consumer, because a genuine, independently reviewed V5
policy migration and browser decision ledger integration are still required.

## Existing approval-ledger bridge acceptance

`jason_runtime.browser_release_approval_bridge.V5BrowserApprovalDecisionBridge`
is now staged **without live mounting**, and delegates signed V5 decisions
only to the same existing `ApprovalRequestService.accept_response`.
It requires a root-reviewed `5.0` policy, exact pending release, independent
root public-key signature proof, original privileged OID, valid request TTL,
and canonical Jason owner authorization. The standalone runtime module
imports **no MCP or host-only packages**: the protected host attestor is
an explicit injected fail-closed port, not a user-substitutable model input.
Standalone runtime tests reject V4 and missing host attestation before any
approval write. Negative tests reject a V4 policy,
normal Teams identity, tampered release SHA/scope, denied Jason authority,
and a duplicate click. Recording a decision does NOT deploy a release;
the existing host Release Manager independently revalidates the signed
receipt, CCC and freeze controls before production.

This bridge must not be enabled before the signed V5 policy migration,
root trust enrollment, and host consumer code review are complete.

## Protected host-consumer SQLite readback acceptance

`release_mobile_approval_consumer.verify_protected_v5_browser_ledger` now
performs a **read-only** bounded lookup of the native approval ledger's
accepted decision, exact request, and retained signed browser evidence.
`v5_browser_release_host_consumer.verify_v5_browser_release_receipt`
revalidates the original versioned V5 policy, root-trusted signing key,
admin Entra OID, timestamp, exact release/rollback/manifest/scope and
cross-matches the signed evidence digest against the *native*
`ApprovalResponse`. Any V4 Teams card, wrong actor, absent ledger,
changed hash, fabricated receipt or expired scope fails closed.

The V5 host readback returns `release_authorized=False`,
`ccc_attested=False`, and `production_changed=False`.
It cannot populate an `owner_approval` field, fabricate CCC, remove
the freeze, deploy or restart services. A separately approved V5 policy
and final host promotion authorization are required to wire the verified
result into the existing release-authority transaction. This intentionally
does **not** modify V4 signed Teams receipt processing.

The runtime/MCP bridge and protected SQLite/signature integration tests are required by
SEC-007. No production routing or privileged account license changes occur.

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
