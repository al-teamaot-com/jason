# Capability Specification - Teams User Bootstrap and Messaging

**Draft status:** Ready for implementation based on successful 2026-08-10 proof-of-concept.

## Capability 1 - `ensure_teams_conversation`

### Purpose

Ensure Jason can proactively communicate with an authorized Microsoft Entra user through Microsoft Teams.

### Request

```json
{
  "capability": "ensure_teams_conversation",
  "target_user_id": "<entra-object-id>",
  "tenant_id": "<tenant-id>",
  "workflow_id": "<jason-workflow-id>",
  "purpose": "<business-purpose>"
}
```

### Orchestrator responsibilities

- Authenticate and authorize the requesting workflow.
- Resolve tenant boundary and target identity.
- Enforce policy gates before side effects.
- Issue the capability call.
- Record audit events and evidence references.
- Handle retry, timeout, and escalation.

### Capability behavior

1. Validate target user belongs to the expected tenant.
2. Check central conversation/bootstrap registry for a known Teams conversation.
3. If known, return `ready` without changing anything.
4. If unknown, obtain an ephemeral Microsoft Graph app-only token via certificate/secret reference.
5. Query `users/{id}/teamwork/installedApps` for the Jason Teams catalog app.
6. If not installed, install the app.
7. Poll/wait for Teams/OpenClaw conversation availability with bounded retries.
8. Store non-secret conversation metadata centrally.
9. Return structured status.

### Example result

```json
{
  "status": "ready",
  "target_user_id": "<entra-object-id>",
  "app_installation": "existing-or-created",
  "conversation_available": true,
  "evidence_ref": "<central-evidence-reference>"
}
```

## Capability 2 - `send_teams_message`

### Purpose

Send a governed Teams message after ensuring the target conversation exists.

### Request

```json
{
  "capability": "send_teams_message",
  "target_user_id": "<entra-object-id>",
  "message": "<content-or-message-reference>",
  "workflow_id": "<jason-workflow-id>",
  "purpose": "<business-purpose>",
  "requires_response": false
}
```

### Required sequence

1. Orchestrator invokes `ensure_teams_conversation`.
2. If `ready`, orchestrator authorizes outbound send.
3. Teams capability invokes OpenClaw messaging provider.
4. Delivery receipt is captured.
5. Audit event records message purpose, target identity, result, message ID, and conversation reference by reference.

## Idempotency

- App installation must be treated as idempotent.
- A repeated bootstrap request must not create duplicate application installs or duplicate workflow state.
- Message idempotency keys should be used where a workflow could retry after an ambiguous timeout.

## Failure states

Suggested normalized statuses:

- `identity_not_found`
- `identity_not_authorized`
- `app_not_published`
- `graph_auth_failed`
- `graph_permission_denied`
- `app_install_failed`
- `conversation_pending`
- `conversation_unavailable`
- `openclaw_unavailable`
- `delivery_failed`
- `delivered`

Raw vendor errors should be retained as evidence but not become Jason's external contract.

## Security rules

- No agent receives Graph access tokens or private-key material.
- Tokens are generated and used within the capability boundary only.
- Tokens are ephemeral and never written to long-lived logs or shared memory.
- User IDs are validated against tenant context.
- Broad Graph permissions are reviewed periodically for possible reduction.
- The capability must be invoked through the orchestrator; agents never call Graph or OpenClaw directly.

## Audit events

At minimum:

- `teams.bootstrap.requested`
- `teams.app_install.checked`
- `teams.app_install.created`
- `teams.conversation.ready`
- `teams.message.requested`
- `teams.message.sent`
- `teams.message.failed`

Each event should include workflow ID, target identity reference, capability version, policy decision/evidence reference, timestamp, result, and vendor correlation/request IDs where available.

## Technology Steward review

Review at least when any of the following changes:

- OpenClaw Teams provider behavior
- Microsoft Graph Teams app installation APIs
- Required Graph permissions
- Teams app manifest schema
- Microsoft Bot Framework authentication model
- Certificate/federated identity mechanisms

Retire custom bootstrap logic if native OpenClaw/Teams support provides an equivalent governed proactive-conversation capability.
