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
