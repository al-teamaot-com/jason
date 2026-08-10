# Implementation Record - 2026-08-10 - Microsoft Teams Channel and Proactive Messaging

## Objective

Make Microsoft Teams a functioning Jason interaction channel and prove that Jason can initiate a conversation with a user who has never previously contacted the bot.

## Final result

Successful.

By the end of the session:

1. Teams messages reached Jason/OpenClaw through the public AWS relay.
2. Jason produced automatic conversational replies in Teams.
3. OpenClaw successfully sent direct outbound Teams messages.
4. Jason Approval Bot was published to the AOT organization Teams app catalog.
5. Jason authenticated to Microsoft Graph using app-only certificate authentication.
6. Jason installed its Teams app for a user who had never contacted the bot.
7. Immediately afterward, OpenClaw successfully initiated a Teams message to that user.

## Infrastructure created or validated

### AWS Teams relay

- EC2 instance: `i-0b0bb56884acb565c`
- AMI used at creation: `ami-0bdc7d025135d7b49`
  - `al2023-ami-2023.12.20260803.3-kernel-6.18-x86_64`
- Instance type: `t3.micro`
- Subnet: `subnet-1b9ee57e`
- VPC: `vpc-726cc017`
- Security group: `sg-0c3decf82edd65ab6`
- Inbound rules: TCP 80 and TCP 443 from `0.0.0.0/0`
- Elastic IP allocation used: `eipalloc-05d20d0a5dc28542d`
- Elastic IP: `18.235.19.103`
- IAM role/profile: `Jason-Teams-Relay-SSM`

### DNS / TLS

- Route53 hosted zone: `Z02444982FY651WQ3RXFU`
- Record: `teams-jason.teamaot.com -> 18.235.19.103`
- Caddy obtained a valid Let's Encrypt certificate using ACME TLS-ALPN validation.
- Caddy was installed as a standalone binary because the official COPR repo did not support Amazon Linux 2023.

### ZeroTier

- Network: `743993800f93d22f` / `Jason`
- Jason host: `10.87.246.157/24`
- AWS relay: `10.87.246.16/24`
- Relay-to-Jason connectivity test reached OpenClaw on port 3978.

## OpenClaw findings and changes

### Teams inbound path

Caddy access logging proved a Microsoft Bot Framework request reached:

`POST /api/messages`

with Microsoft Bot Framework headers and was handled with HTTP 200.

### Pairing/allowlist

OpenClaw logs showed the primary Teams user was being dropped because `dmPolicy=pairing` and the user was not allowlisted.

The primary operator Entra object ID was added to `channels.msteams.allowFrom`.

### Missing message tool

`openclaw doctor` explicitly warned that the `main` agent was routed from `msteams` but the `message` tool was unavailable.

Current global profile:

`tools.profile = coding`

Added:

`tools.alsoAllow = ["group:messaging"]`

### Agent/model isolation test

Executed an agent test requesting exactly `JASON TEST OK`.

Result: `JASON TEST OK`.

Conclusion: model and main agent were healthy; the failure was in Teams channel delivery/tooling rather than the LLM.

### Certificate failure

Outbound test initially failed with:

`The file at the specified path does not contain a PEM-encoded certificate.`

Inspection showed:

- `jason-approval-bot.pem` started with `-----BEGIN PRIVATE KEY-----`
- `jason-approval-bot.crt` started with `-----BEGIN CERTIFICATE-----`

OpenClaw's `certificatePath` had been pointing to the private-key-only file.

A combined PEM was created with certificate first and private key second:

`jason-approval-bot-combined.pem`

OpenClaw `certificatePath` was updated to:

`/run/jason-secrets/microsoft-teams/jason-approval-bot-combined.pem`

After gateway restart, direct outbound Teams delivery succeeded.

## Microsoft Teams app publication

Initial Graph lookup returned no organization catalog app because the developer package had not been published to the tenant catalog.

The package was downloaded as `Jason-Approval-Bot.zip` and published to the organization catalog.

Catalog app ID:

`1b24025a-201f-439d-a4ef-e308c7f3d853`

The first published version was `1.0.1`.

## `webApplicationInfo` and Entra resource URI

The original manifest did not contain `webApplicationInfo`.

The Entra application also had no Identifier URI.

Added Entra Identifier URI:

`api://teams-jason.teamaot.com/c94301b7-7194-46ab-aab7-94f9366f51a9`

Added Teams manifest:

```json
"webApplicationInfo": {
  "id": "c94301b7-7194-46ab-aab7-94f9366f51a9",
  "resource": "api://teams-jason.teamaot.com/c94301b7-7194-46ab-aab7-94f9366f51a9"
}
```

The updated app had to be version-bumped because Teams rejected a second `1.0.1` definition with HTTP 409.

Updated and published version: `1.0.2`.

Graph then showed the app definition `authorization.clientAppId` correctly linked to:

`c94301b7-7194-46ab-aab7-94f9366f51a9`

## Microsoft Graph app-only authentication

Jason authenticated as its own Entra application using the existing certificate and private key to sign a JWT client assertion.

The token endpoint used:

`https://login.microsoftonline.com/f7054323-d52b-4863-8c2f-1898f0b6077c/oauth2/v2.0/token`

Scope:

`https://graph.microsoft.com/.default`

The proof-of-concept stored the resulting token temporarily in:

`/tmp/jason_graph_token`

No token or private-key content is included in this record.

## Graph permission progression

### First permission

Granted:

`TeamsAppInstallation.ReadWriteSelfForUser.All`

AppRoleId:

`908de74d-f8b2-4d6b-a9ed-2a17b3b78179`

A fresh app-only token showed this role, but proactive app installation still returned:

`HTTP/1.1 403 Forbidden - Caller is not authorized.`

### Second permission

Granted:

`TeamsAppInstallation.ReadWriteForUser.All`

AppRoleId:

`74ef0291-ca83-4d02-8c7e-d2391e6a444f`

A fresh token then showed both roles.

Repeating the same proactive install call returned:

`HTTP/1.1 201 Created`

This is the decisive proof that the broader permission was required by the actual tenant/API behavior observed on 2026-08-10.

## Proactive-user test

Target user: Lindsey Collins  
Entra object ID: `9f590a57-a07e-434b-84e9-5b698161b86a`

Before app installation, OpenClaw returned:

`No conversation reference found for user:9f590a57-a07e-434b-84e9-5b698161b86a.`

Microsoft Graph was used to install Jason Approval Bot for the target user.

Result:

`HTTP/1.1 201 Created`

Immediately after installation, OpenClaw sent:

`Lindsey, This is Jason. Can you help me escape the Matrix?`

OpenClaw result included:

- `deliveryStatus: sent`
- Teams message ID: `1786383273853`
- A newly created/available Teams conversation ID

The specific joke text is incidental; the operational proof is that a user with no previous Jason conversation could be bootstrapped and messaged proactively.

## What this enables

- New employee onboarding initiated by Jason
- Approval requests initiated by Jason
- Security or operational notifications
- Scheduled/conditional outreach
- Human-in-the-loop governance gates
- Follow-up messages where a workflow, not the human, starts the conversation

## Required production follow-up

1. Implement Graph app-only token acquisition as a reusable Jason capability.
2. Implement `ensure_teams_conversation(user_id)`.
3. Move identity resolution to Microsoft Entra/authoritative directory lookup.
4. Add centralized audit events and evidence references.
5. Add bounded retries and timeouts for app installation/conversation availability.
6. Harden certificate permissions and stop using world-readable combined PEM permissions.
7. Delete temporary `/tmp/jason_graph_token` after tests and do not use a persistent plaintext token file in production.
8. Store secret references centrally (prefer OpenBao/SecretRefs).
9. Explicitly configure trusted OpenClaw plugins and command owner.
10. Review whether `TeamsAppInstallation.ReadWriteForUser.All` can later be reduced to the self-only permission.

## Proven acceptance criteria

The Teams capability should not be considered complete unless all of these continue to pass:

- Public endpoint has valid HTTPS.
- Microsoft Bot Framework can POST to the endpoint.
- AWS relay reaches Jason only through the approved private path.
- OpenClaw automatically replies to an authorized Teams DM.
- OpenClaw direct outbound send returns `deliveryStatus: sent`.
- Jason app-only Graph token can be obtained without exposing secrets.
- Organization Teams app can be checked/installed for a target user.
- New-user install returns a successful idempotent state.
- OpenClaw can then proactively message that user.
- Every install/send action can be tied to an auditable Jason workflow identity and purpose.
