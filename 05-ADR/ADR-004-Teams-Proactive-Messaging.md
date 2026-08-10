# ADR-004 - Microsoft Teams as a Governed Jason Interaction Channel

**Status:** Accepted / proven in production-like testing  
**Date:** 2026-08-10

## Decision

Jason will use Microsoft Teams as a supported human interaction and approval channel through OpenClaw's Microsoft Teams provider. Jason will support both normal conversational replies and proactive messaging to users who have never previously contacted the bot.

Proactive messaging will be bootstrapped through Microsoft Graph by ensuring that the Jason Teams app is installed for the target Microsoft Entra user before OpenClaw attempts delivery.

## Context

OpenClaw can reply to a Teams user after a conversation reference exists. It can also proactively send to that user once the reference is known. However, a brand-new user who has never interacted with the bot has no stored conversation reference, causing outbound delivery to fail with:

`No conversation reference found for user:<aad-object-id>. The bot must receive a message from this conversation before it can send proactively.`

Requiring every employee to manually message Jason first is not acceptable for onboarding, approvals, incident notification, or other workflows that Jason must initiate.

## Chosen flow

1. Jason resolves the target user to a Microsoft Entra object ID.
2. Jason obtains a Microsoft Graph app-only token using its certificate identity.
3. Jason checks whether the organization Teams app is installed for the user.
4. If absent, Jason installs the app using Microsoft Graph.
5. Teams establishes the bot/user conversation context.
6. OpenClaw uses the resulting conversation reference to send the proactive message.
7. Jason records the install/bootstrap and delivery result in the central audit trail.

## Required Microsoft identity linkage

The Teams app manifest contains:

```json
"webApplicationInfo": {
  "id": "c94301b7-7194-46ab-aab7-94f9366f51a9",
  "resource": "api://teams-jason.teamaot.com/c94301b7-7194-46ab-aab7-94f9366f51a9"
}
```

The Entra application has the same Identifier URI:

`api://teams-jason.teamaot.com/c94301b7-7194-46ab-aab7-94f9366f51a9`

The organization Teams catalog entry is linked to the same Entra client application ID.

## Microsoft Graph permissions

The proof-of-concept established that the token contained both:

- `TeamsAppInstallation.ReadWriteSelfForUser.All`
- `TeamsAppInstallation.ReadWriteForUser.All`

In this tenant and implementation, the self-only permission still returned HTTP 403 for proactive installation. Adding `TeamsAppInstallation.ReadWriteForUser.All`, refreshing the app-only token, and retrying resulted in HTTP 201 Created.

This behavior is an implementation finding and should be periodically re-evaluated by the Technology Steward. If Microsoft later makes the narrower self permission sufficient in this environment, Jason should retire the broader permission.

## Governance requirements

- Agents may not directly call Teams or Graph. They request a named capability from the orchestrator.
- Identity must be resolved and authorized before bootstrap or send.
- Proactive app installation is an auditable side effect.
- Message initiation must be attributable to a workflow, operator, or policy decision.
- Approval workflows must preserve the approval artifact and response evidence.
- Tokens and private keys must never be included in logs or agent context.
- The capability must be idempotent and safe to retry.

## Consequences

### Positive

- Jason can initiate onboarding and approval conversations with new employees.
- Users do not need to discover or manually contact Jason first.
- Teams remains the human-facing system of engagement while Jason orchestrates behind it.
- Microsoft-native identity and app installation mechanisms are reused rather than duplicated.

### Risks / costs

- Graph app installation is privileged and must be governed.
- The broader `TeamsAppInstallation.ReadWriteForUser.All` permission increases blast radius and requires ongoing least-privilege review.
- Conversation/bootstrap state must be tracked and retried safely.
- Certificate and token lifecycle management must be hardened beyond the proof-of-concept.

## Retirement criteria

Replace or simplify this capability if Microsoft Teams/OpenClaw gains a native proactive-conversation bootstrap API that removes the need for custom Graph app-install orchestration while preserving equivalent governance and auditability.
