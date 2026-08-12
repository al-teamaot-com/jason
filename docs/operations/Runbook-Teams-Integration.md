# Runbook - Jason Microsoft Teams Integration

**Last validated:** 2026-08-10

This runbook documents the working Microsoft Teams integration, including inbound chat, outbound replies, and proactive messaging to users who have never contacted Jason.

## 1. Known working architecture

### Public ingress

- DNS: `teams-jason.teamaot.com`
- Public Elastic IP: `18.235.19.103`
- AWS relay instance: `i-0b0bb56884acb565c`
- Relay private IP at creation: `172.31.72.2`
- Security group: `sg-0c3decf82edd65ab6`
- Allowed inbound: TCP 80 and TCP 443
- IAM role/profile: `Jason-Teams-Relay-SSM`
- Caddy version validated: `v2.11.4`

### ZeroTier

- Network ID: `743993800f93d22f`
- Network name: `Jason`
- Jason/OpenClaw host ZeroTier IP: `10.87.246.157/24`
- AWS relay ZeroTier IP: `10.87.246.16/24`
- AWS relay successfully reached `http://10.87.246.157:3978/api/messages` and received HTTP 401, proving network reachability and OpenClaw authentication enforcement.

### OpenClaw

- Container: `openclaw-openclaw-gateway-1`
- Teams/Bot listener: TCP 3978
- OpenClaw version observed: `2026.7.1`
- Main model: `openai/gpt-5.6-sol`
- Tool profile: `coding`
- Additional tools: `tools.alsoAllow = ["group:messaging"]`

### Teams / Entra identifiers

- Tenant ID: `f7054323-d52b-4863-8c2f-1898f0b6077c`
- Entra app / bot App ID: `c94301b7-7194-46ab-aab7-94f9366f51a9`
- Teams organization catalog app ID: `1b24025a-201f-439d-a4ef-e308c7f3d853`
- Published Teams app version validated: `1.0.2`
- App distribution method: `organization`
- Public bot endpoint: `https://teams-jason.teamaot.com/api/messages`
- Certificate thumbprint: `736F21058BB767E7B9BC31A65A36175C0361AAFA`

### Known test users

- Primary operator Entra object ID: `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`
- Lindsey Collins Entra object ID used for proactive test: `9f590a57-a07e-434b-84e9-5b698161b86a`

Object IDs are identifiers, not authentication secrets, but production workflows should resolve them from authoritative identity data instead of hard-coding them.

## 2. OpenClaw Teams configuration

Validated shape:

```json
{
  "appId": "c94301b7-7194-46ab-aab7-94f9366f51a9",
  "tenantId": "f7054323-d52b-4863-8c2f-1898f0b6077c",
  "authType": "federated",
  "certificatePath": "/run/jason-secrets/microsoft-teams/jason-approval-bot-combined.pem",
  "certificateThumbprint": "736F21058BB767E7B9BC31A65A36175C0361AAFA",
  "enabled": true,
  "allowFrom": [
    "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
  ],
  "dmPolicy": "pairing",
  "groupPolicy": "allowlist"
}
```

Host secret mount:

`/opt/jason/bootstrap/secrets/microsoft-teams -> /run/jason-secrets/microsoft-teams`

The combined PEM was constructed from:

- `jason-approval-bot.crt` - PEM certificate
- `jason-approval-bot.pem` - PEM private key
- `jason-approval-bot-combined.pem` - certificate followed by private key

OpenClaw outbound Teams authentication failed when `certificatePath` pointed only to the private key. The combined PEM resolved the failure.

## 3. Caddy behavior

Caddy terminates public TLS for `teams-jason.teamaot.com` and proxies the Teams bot endpoint to Jason over ZeroTier.

Validated public behavior:

- TLS certificate obtained automatically from Let's Encrypt.
- Microsoft Bot Framework POST requests reached Caddy from Microsoft addresses.
- Caddy proxied requests to OpenClaw.
- A direct unauthenticated GET/HTTP request to `/api/messages` returned HTTP 401 from Express/OpenClaw after the proxy path was corrected. This is expected and proves the request reached the protected application.

Operational check:

```bash
curl -i https://teams-jason.teamaot.com/api/messages
```

Expected diagnostic result for an unauthenticated request: HTTP 401. Do not treat that 401 as an outage.

## 4. OpenClaw conversational messaging fixes

### Direct-message allowlist

Inbound Teams messages initially produced pairing/drop behavior because the sender was not allowlisted. The stable Entra user ID was added:

```bash
openclaw config set channels.msteams.allowFrom '["bee80bdc-ffb0-4c50-b453-c09d4d411f5f"]'
```

### Messaging tool availability

`openclaw doctor` reported:

`Agent "main" is routed from channel "msteams", but the message tool is unavailable for that agent.`

The existing global tool profile was `coding`. Messaging was added without replacing that profile:

```bash
openclaw config set tools.alsoAllow '["group:messaging"]'
```

### Model validation

The model/agent path was proven independently with:

```bash
openclaw agent --agent main --message "Reply with exactly: JASON TEST OK"
```

Expected output: `JASON TEST OK`.

This check is useful when Teams receives a turn but no reply payload is queued.

## 5. Outbound Teams test

Once certificate handling was corrected, a direct proactive message to a user with an existing conversation reference succeeded:

```bash
openclaw message send \
  --channel msteams \
  --target "user:<ENTRA_OBJECT_ID>" \
  --message "Jason outbound Teams test" \
  --json
```

Success indicators:

- `deliveryStatus: sent`
- A Teams `messageId`
- A Teams `conversationId`

## 6. Teams organization app publication

The Teams Developer CLI downloaded the package:

```powershell
teams app package download c94301b7-7194-46ab-aab7-94f9366f51a9
```

The package was published to the AOT organization app catalog with Microsoft Graph. The resulting catalog app ID is:

`1b24025a-201f-439d-a4ef-e308c7f3d853`

The updated package version `1.0.2` includes `webApplicationInfo`:

```json
"webApplicationInfo": {
  "id": "c94301b7-7194-46ab-aab7-94f9366f51a9",
  "resource": "api://teams-jason.teamaot.com/c94301b7-7194-46ab-aab7-94f9366f51a9"
}
```

The Entra application's Identifier URI was set to the same resource value.

## 7. Microsoft Graph permissions

### Application permissions on Jason Approval Bot

Validated token roles:

- `TeamsAppInstallation.ReadWriteSelfForUser.All`
  - AppRoleId: `908de74d-f8b2-4d6b-a9ed-2a17b3b78179`
- `TeamsAppInstallation.ReadWriteForUser.All`
  - AppRoleId: `74ef0291-ca83-4d02-8c7e-d2391e6a444f`

Important implementation finding: the self-only permission was present in the app-only token but proactive installation still returned HTTP 403. After `TeamsAppInstallation.ReadWriteForUser.All` was added and a fresh token was issued, the same install request returned HTTP 201 Created.

### Administrative publication permission

Updating the organization Teams app catalog from an interactive admin Graph PowerShell session required `AppCatalog.ReadWrite.All` (or another supported app-catalog write scope). This is an operator/publishing requirement and should not automatically be granted to Jason's runtime identity.

## 8. App-only Microsoft Graph authentication

The proof-of-concept used the existing certificate and private key on Jason to generate a signed client assertion and request a client-credentials token from Microsoft Entra.

Inputs:

- Tenant ID: `f7054323-d52b-4863-8c2f-1898f0b6077c`
- Client ID: `c94301b7-7194-46ab-aab7-94f9366f51a9`
- Certificate: `/opt/jason/bootstrap/secrets/microsoft-teams/jason-approval-bot.crt`
- Private key: `/opt/jason/bootstrap/secrets/microsoft-teams/jason-approval-bot.pem`
- Scope: `https://graph.microsoft.com/.default`

The access token was temporarily written to `/tmp/jason_graph_token` for testing.

Production requirement: token creation must become an internal capability and the token must remain ephemeral. Do not print, persist long-term, or place Graph tokens in prompts, logs, tickets, or documentation.

## 9. Proactive install / new employee bootstrap

### Why it is needed

Before app installation, OpenClaw returned:

`No conversation reference found for user:<id>. The bot must receive a message from this conversation before it can send proactively.`

### Working Graph request

With a valid app-only token:

```http
POST https://graph.microsoft.com/v1.0/users/<USER_ID>/teamwork/installedApps
Authorization: Bearer <APP_ONLY_TOKEN>
Content-Type: application/json

{
  "teamsApp@odata.bind": "https://graph.microsoft.com/v1.0/appCatalogs/teamsApps/1b24025a-201f-439d-a4ef-e308c7f3d853"
}
```

Validated successful response: `HTTP/1.1 201 Created`.

After installation, OpenClaw successfully sent directly to the previously uncontacted user with `openclaw message send --channel msteams --target "user:<id>" ...` and returned `deliveryStatus: sent` plus a new conversation ID.

## 10. Proposed production capability

Implement a governed orchestrator capability:

`ensure_teams_conversation(user_id)`

Suggested behavior:

1. Validate caller/workflow authority.
2. Resolve and validate the target Entra identity.
3. Check central state for a known valid Teams conversation reference.
4. If unknown, query Graph to see whether Jason is installed for the user.
5. If absent, install the organization app.
6. Wait/poll for conversation/bootstrap state with bounded retries.
7. Confirm OpenClaw can resolve the user's proactive target.
8. Return a structured result containing only non-secret identifiers and status.
9. Emit audit events for each state transition.

Then implement a separate capability:

`send_teams_message(user_id, message_ref_or_content, purpose, workflow_id)`

The orchestrator calls `ensure_teams_conversation` first, then performs delivery. Agents do not call Graph or OpenClaw directly.

## 11. Security cleanup required

The proof-of-concept temporarily changed `jason-approval-bot-combined.pem` to mode `0644` so the OpenClaw container user could read it. Because the file contains a private key, **do not leave it world-readable as the production state**.

Recommended remediation:

- Determine the OpenClaw container runtime UID/GID.
- Set the host file owner/group so only root and the required container identity can read it.
- Use mode `0640` or tighter where the bind-mount model permits.
- Prefer Docker secrets or the existing Jason/OpenBao secret-delivery architecture so plaintext private-key material is not broadly readable on the host.
- Verify with an explicit least-privilege read test from the container.

Additional OpenClaw doctor findings to clean up:

- Configure `commands.ownerAllowFrom` for the authorized human operator.
- Explicitly set `plugins.allow` for trusted non-bundled plugins such as `codex` and `msteams` after validation.
- Migrate `gateway.auth.token` and other secret-bearing configuration to SecretRefs.
- Run `openclaw secrets audit --check`.
- Run `openclaw security audit --deep`.

## 12. Troubleshooting matrix

| Symptom | Observed cause | Resolution |
|---|---|---|
| SSM instance never appears online | IAM instance profile was newly associated after boot; agent initially lacked usable instance credentials | Reboot after profile association; SSM came online |
| Caddy unavailable through Amazon Linux package/COPR | Caddy COPR did not publish an Amazon Linux 2023 repo | Installed official Caddy binary directly |
| Public endpoint returned 404 | Reverse proxy route was not yet correct | Corrected Caddyfile; endpoint then reached OpenClaw |
| Public endpoint returns 401 | Unauthenticated request reached protected OpenClaw endpoint | Expected diagnostic result, not failure |
| Teams POST reaches OpenClaw but DM is dropped | Sender not on `channels.msteams.allowFrom` while `dmPolicy=pairing` | Add stable Entra object ID to `allowFrom` |
| Turn dispatched but no reply payload | `coding` tool profile did not expose the messaging tool | Add `tools.alsoAllow = ["group:messaging"]` |
| Agent suspected broken | Unknown whether model could answer | `openclaw agent ...` returned `JASON TEST OK`; model path healthy |
| Outbound Teams send fails: PEM does not contain certificate | `certificatePath` pointed to private-key-only PEM | Create combined PEM containing certificate + private key and point OpenClaw to it |
| Proactive send fails: no conversation reference | User has never established a bot conversation | Publish app to org catalog and install it for target user through Graph |
| Graph proactive install returns 403 with self permission | Tenant/API behavior required broader app installation permission in this implementation | Add `TeamsAppInstallation.ReadWriteForUser.All`, refresh token, retry; HTTP 201 |
| App catalog update returns 409 version exists | Teams manifest version unchanged | Bump manifest version, rebuild ZIP, publish new app definition |

## 13. Validation milestones from 2026-08-10

- Microsoft Bot Framework POST observed at Caddy with HTTP 200 downstream handling.
- OpenClaw automatic conversational reply observed in Teams.
- Manual OpenClaw outbound Teams send returned `deliveryStatus: sent`.
- Organization Teams app version `1.0.2` published.
- Jason app-only Graph token contained required installation roles.
- Proactive Graph install for Lindsey returned HTTP 201 Created.
- OpenClaw then proactively sent the test message to Lindsey and returned `deliveryStatus: sent` with a new conversation ID.

These milestones prove that Jason can both converse with existing users and bootstrap/initiate a Teams conversation with a new user.
