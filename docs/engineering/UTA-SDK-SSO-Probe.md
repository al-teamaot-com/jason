# Universal Teams Approval — SDK user SSO readiness probe

Status: **development only; disabled by default.** Parent P0 #1545 and #1440.

## Purpose
Verify that an authorized AOT Teams user can obtain a **user-scoped**
Microsoft token from the existing Microsoft 365 Agents SDK 1.6.1 and an
independently approved Azure Bot OAuth connection, without making any approval
or provider write. This probe is **not** UTA activation or proof that a card
can be safely approved.

## Configuration prerequisites (not yet provisioned by this change)
1. Review an AOT-only Microsoft Entra app registration with least-privilege
   delegated scope(s), a resource URI/audience and supported token version.
   Do not reuse bot app-only credentials as user identity evidence.
2. Configure the corresponding Azure Bot OAuth connection, including an
   allowed tenant, the expected app/resource URI and approved consent.
3. Ensure the Teams app manifest's `webApplicationInfo` points to the exact
   Entra app ID and resource URI, and consent/Teams installation is tested.
4. Retain existing Conditional Access/MFA, authorized staff and role
   restrictions. Secrets belong in Jason's approved secret store, not Git.
5. Independently review and authorize the exact governed production release
   before setting any of the following variables.

## Opt-in probe configuration
- `JASON_UTA_SSO_PROBE_ENABLED=true`
- `JASON_UTA_SSO_CONNECTION_NAME=<approved-connection-name>`

Absent activation flag means **no new AgentApplication authorization handler
exists** and current Teams traffic is unchanged. An enabled probe with a
missing/malformed connection name fails startup closed; it does not fall back
to anonymous or app-only approval.

On an actual authenticated Teams conversation, the AOT tester sends the
exact text `/uta-sso-check`. The SDK route applies only to that command,
uses `AzureBotUserAuthorization` with `enableSso=true`, and attempts
`agent.authorization.getToken(context, 'uta-human')` only in that
same turn. It reports success/failure **without logging, persisting,
responding with, or forwarding the token**. It never creates a pending
approval or advances a release. SDK sign-in state currently uses memory and
must not be treated as restart-resilient UTA evidence.

## Distinct next step
Connect this ephemeral SDK user token to the independently reviewed,
JWKS-backed Python verification boundary in PR #1546 using a **secure,
single-turn identity/receipt-binding protocol**. Never copy raw bearer tokens
into Jason's signed conversation envelope or durable approval database.
Validate exact tenant, user, OAuth client, JWT audience/issuer/expiry,
delegated scopes and MFA. Then complete fresh harmless Teams Approve/Deny
and negative/replay tests, protected security review and explicit exact-SHA
production activation. All universal plan flags remain OFF until acceptance.

Microsoft documentation:
- https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agent-oauth-configuration-dotnet
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-register-aad
- https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-manifest
