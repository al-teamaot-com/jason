# AOT Entra administrator approval packet — J-Assist Chrome pilot

State: PREPARED ONLY. No tenant, production Jason MCP, or existing
ChatGPT OAuth app settings have been changed. This packet is the
smallest scoped AOT Entra configuration needed to test real Chrome SSO.

## Verified existing resources (do not modify their current permissions)

AOT tenant: f7054323-d52b-4863-8c2f-1898f0b6077c

Existing resource/API app: Jason MCP API
Application (client) ID: 9b9996e9-5c34-48b7-948c-f44f89352f89
Canonical Identifier URI: https://mcp-jason.teamaot.com/mcp
Existing delegated scope: Jason.Read (MUST remain enabled and unchanged)

Existing ChatGPT OAuth client: Jason - ChatGPT MCP
Application (client) ID: 9bdefd9b-df74-4ac7-801b-8aa610366901
Do not modify its secret, callback, or access to Jason.Read.

## A. One new admin-consent-only scope on the existing API registration

In Microsoft Entra admin center:
Entra ID > App registrations > All applications > Jason MCP API
Confirm Application (client) ID 9b9996e9-5c34-48b7-948c-f44f89352f89.
Choose Expose an API > Add a scope, on existing
https://mcp-jason.teamaot.com/mcp Identifier URI.

Scope name: JAssist.Send
Who can consent: Admins only
Admin consent display name: Send a reviewed Datto screenshot to Jason
Admin consent description: Allow a signed-in AOT technician, subject to
Jason governance and Datto device authorization, to upload one explicitly
requested remote screen image for session-specific assistance.
State: Enabled

Resulting delegated permission identifier:
https://mcp-jason.teamaot.com/mcp/JAssist.Send
JWT scp claim must contain JAssist.Send (not the full URI).

Do NOT remove/change Jason.Read or the existing API Identifier URI.

## B. One new single-tenant public Chrome SPA client application

Entra ID > App registrations > New registration

Name: AOT J-Assist Chrome (Pilot)
Supported account types: Accounts in this organizational directory only
Redirect platform: Single-page application (SPA)
Redirect URI: https://pihjpgplfhmpenlghbcdbgdkadleflfi.chromiumapp.org/jassist

The redirect above comes from the development extension manifest's pinned
PUBLIC RSA key. It deliberately differs from the older v0.1.8 unpacked
extension ID kckeghklalamkjloakolkdceajkbmehj; DO NOT use the old ID.

Under API permissions > Add a permission > My APIs > Jason MCP API:
Type: Delegated permissions
Permission: JAssist.Send ONLY
Grant admin consent for AOT after reviewing this precise scope.
Remove any default Microsoft Graph User.Read permission if auto-added.
Do not add application roles, client secrets, certificates, implicit flow,
personal-Microsoft-account support, broad Graph permissions or Datto keys.

Record the new client application's Application (client) ID after saving.
That ONE GUID is the only identifier missing from the pilot source config.

## C. Installation and access boundaries

Developer build: J-Assist v0.1.9, stable development extension ID:
pihjpgplfhmpenlghbcdbgdkadleflfi

The public manifest key may be distributed in code. Its private development
signing key is in the Jason host's restricted local development identity
storage; it is NOT in GitHub or Windows Downloads. Transfer to an approved
enterprise secret/key-management process before any signed distribution.
Never transmit or paste the private key into chat, a ticket, or Teams.

The new app is delegated USER authorization, not a service principal
permission to operate autonomously. Backend must validate Entra signature,
issuer, tenant, aud=Jason MCP API, client azp=new J-Assist SPA ID, exact
scp=JAssist.Send and ACTIVE Jason subject binding.

No Chrome upload is permissible until native Datto technician permissions,
review/redaction, durable encrypted evidence handling and the governed
HTTPS endpoint pass acceptance. App registration/consent alone MUST NOT
enable upload, create a production release, or lift the production freeze.

## D. Administrator deliverables and no-secrets acceptance

Administrator records:
1. The new pilot Chrome SPA application CLIENT ID (GUID).
2. The fact that Jason MCP API exposes enabled JAssist.Send.
3. J-Assist SPA app has ONLY delegated JAssist.Send grant and the
   exact SPA redirect URI shown above.
4. No changes to the existing ChatGPT/Jason.Read client.

No password, client secret, recovery code, private key, or access token is
required. The engineering team can then finish real pilot OAuth validation
and authorization tests before the one separate governed production release.

Official references:
https://learn.microsoft.com/en-us/entra/identity-platform/scenario-protected-web-api-expose-scopes
https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
https://developer.chrome.com/docs/extensions/reference/api/identity
