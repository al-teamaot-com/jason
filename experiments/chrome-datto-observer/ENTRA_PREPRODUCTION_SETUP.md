# J-Assist preproduction AOT Entra OAuth acceptance

**Status: NOT configured.** These instructions define a future AOT
administrator change. No Entra application or service permission was
created by this work.

## Exact app registration and runtime contract

1. Retain one **stable Chrome extension ID** for the approved, signed
   J-Assist package. A fresh unpacked Chrome extension directory may
   produce a different ID. Do not register the v0.1.8 local test ID as
   a permanent production audience without validating its stability.
2. Record the output of `chrome.identity.getRedirectURL("jassist")`
   from the exact technician pilot extension. Register **that exact URI**
   in AOT Entra **App registrations → Authentication → SPA redirect URI**.
   Its Chrome form is `https://<32-character-extension-id>.chromiumapp.org/jassist`.
3. Use a dedicated single-tenant J-Assist public SPA client identity.
   **No client secret**, implicit grant, device-code fallback or
   password authentication in the Chrome extension. Use authorization-code
   PKCE S256 and exact state/callback validation.
4. Give this app only the delegated API permission for Jason's
   reviewed, narrowly scoped screenshot-intake API (proposed name
   `JAssist.Send`). The final literal resource URI must be read
   from the approved Jason API registration. Do **not** ask for
   Microsoft Graph broad permissions or Datto API service keys.
5. The Jason HTTPS ingress must independently validate bearer JWT
   signature, Entra tenant/issuer, `aud` equal to Jason's API app,
   `oid` mapped to an ACTIVE AOT Jason technician, delegated scope
   `JAssist.Send`, expiration and caller permission; the Chrome
   extension is never the source of identity authority.
6. Bind the verified AOT subject to an individually authorized Datto
   active security level, exact Datto device and a current session.
   Datto's API user security level is NOT the same as the interactive
   technician's active UI security level. The provider-backed method to
   read that exact active level is still unresolved and must not be
   replaced with URL/DOM claims.
7. Bind a reviewed Jason HTTPS origin to the deployed extension's build.
   The browser extension must never accept API destination URLs or
   bearer tokens from the active Datto web page or arbitrary messages.
8. Revalidate review/redaction, HTTPS origin, Datto scope and session
   on every transmission; issue a nonce/hash-bound server receipt and
   make reviewed evidence available ONLY to the same AOT subject through
   the separately authorized ChatGPT Business MCP connection.
9. Pilot test: sign in with two real AOT technicians with different
   Datto permissions; check correct user/device, revoke one permission,
   switch Datto active level, navigate and close the tab, expire/stop
   sessions, replay, cross-tenant access, invalid image/secret DLP,
   and MCP evidence isolation. A failure must yield NO success receipt.

## Implementation state

`entra_pkce.js` is a testable **preproduction source module**;
`authenticated_transport.js` is the corresponding pinned sender.
Neither is loaded into the v0.1.8 extension service worker, configured
with a live app/client, or permitted to send an image. The separate
`send_once.js` orchestrator also remains unregistered. This protects
technicians from a nonfunctional or misleading Send button.

References:
- https://developer.chrome.com/docs/extensions/reference/api/identity
- https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow

## Verified pilot-ready parameters, 2026-11-06

AOT's current Jason MCP Entra API is already registered:
* Tenant: f7054323-d52b-4863-8c2f-1898f0b6077c
* Existing resource Application (client) ID: 9b9996e9-5c34-48b7-948c-f44f89352f89
* API Identifier URI: https://mcp-jason.teamaot.com/mcp
* Existing ChatGPT delegated scope: Jason.Read (do not change)

The development extension's new manifest PUBLIC RSA key pins Chrome ID:
pihjpgplfhmpenlghbcdbgdkadleflfi

Its exact SPA redirect is:
https://pihjpgplfhmpenlghbcdbgdkadleflfi.chromiumapp.org/jassist

Older installed v0.1.8 has a DIFFERENT path-derived extension ID and
MUST NOT be used for the new Entra pilot redirect. This v0.1.9 development
build does not include production authentication permissions, registered
backend transport, or a working Send button.

The administrator should add an *admin-consent-only delegated scope*
named JAssist.Send to the existing Jason MCP API (without changing
Jason.Read), then create a new, single-tenant public client
"AOT J-Assist Chrome (Pilot)" with the exact SPA redirect and only that
one delegated Jason API permission. No client secret.

See ENTRA_APPROVAL_PACKET.md for the exact administrator actions and the
one new Application (client) ID to return. The existing ChatGPT OAuth
client remains untouched. Production freeze stays in place.

## Current state — November 12, 2026 (supersedes historical v0.1.8 notes)

J-Assist extension **v0.2.2** loads the guarded send coordinator, PKCE
transport and live-readiness worker modules. The fixed pilot app ID in
source is `d1cc801b-13ba-4d44-bea6-e7f08186e4d5`; this is **not proof
that the corresponding SPA registration, redirect or delegated scope
has been granted in Entra**. The exact extension redirect remains
`https://pihjpgplfhmpenlghbcdbgdkadleflfi.chromiumapp.org/jassist`.

Technician eligibility now uses the configurable existing Entra
`AOT-Jason-JAssist-Users` security group
`5273dd8a-1456-4985-b0a3-c00061267e26`. Native Datto
device/site authorization is separate; a technician's Datto
Administrator security level is **not** a fixed enrollment prerequisite.
The verified provider numeric browser device ID -> native UUID lookup
is a separately governed dependency in draft PR #2456.

The current Jason live receiver is **not registered** and its HTTPS
readiness returns HTTP 404; the Chrome send button must remain disabled.
The Owner approved only a controlled AOT nonproduction screenshot
pilot with content screening, encryption, 120-second expiry and no
automatic endpoint commands; no production deployment or relay change
was authorized. The current exact-frame hash allowlist is suitable
only for independently preapproved synthetic/non-sensitive fixtures,
not arbitrary live screenshots. See
`docs/engineering/JAssist-Pilot-Activation-Readiness-20261112.md`
for current consent, group, vault, DLP, release and activation gates.

Historical sections above are retained to preserve provenance; do
not treat their v0.1.8 implementation state as current.
