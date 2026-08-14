# ADR-007 — Microsoft Teams as a Governed Jason Interaction Channel

**Status:** Accepted / proven in production-like testing and live governed runtime use  
**Date:** 2026-08-10  
**Updated:** 2026-08-14  
**Identifier correction:** Originally created as `ADR-004` on 2026-08-10. Renumbered to `ADR-007` during documentation-governance consolidation because the earlier accepted Datto RMM Managed-Device Authority record already occupied ADR-004. This correction changes only the document identifier; the architectural decision is unchanged.

## Decision

Jason will use Microsoft Teams as a supported human interaction and approval channel through OpenClaw's Microsoft Teams provider. Jason will support both normal conversational replies and proactive messaging to users who have never previously contacted the bot.

Proactive messaging will be bootstrapped through Microsoft Graph by ensuring that the Jason Teams app is installed for the target Microsoft Entra user before OpenClaw attempts delivery.

For governed inbound Teams turns that may take noticeable time, Jason's OpenClaw bridge may emit a bounded best-effort processing acknowledgement through OpenClaw's supported outbound channel adapter after required inbound transport identity/conversation fields are validated and before the governed runtime request begins. This acknowledgement is transport feedback only and does not constitute authorization, evidence, reasoning output, provider result, or task completion.

For exact retries of an authenticated inbound Teams activity, Jason will enforce durable exact-message idempotency at the governed ingress/runtime boundary before the request enters the Teams conversation flow or Central Orchestrator. This control is keyed from authenticated transport identity, not message text, and remains independent of ordinary request-ID replay protection.

## Context

OpenClaw can reply to a Teams user after a conversation reference exists. It can also proactively send to that user once the reference is known. However, a brand-new user who has never interacted with the bot has no stored conversation reference, causing outbound delivery to fail with:

`No conversation reference found for user:<aad-object-id>. The bot must receive a message from this conversation before it can send proactively.`

Requiring every employee to manually message Jason first is not acceptable for onboarding, approvals, incident notification, or other workflows that Jason must initiate.

For inbound Jason-bound conversations, OpenClaw's normal typing lifecycle is not always sufficient because the governed `jason-bridge` compatibility pre-agent route can return a handled result before the normal agent/reply lifecycle begins. A visible processing signal therefore needs to be implemented without creating a second authority path or modifying Jason's governed execution semantics.

Processing feedback does not solve duplicate execution. OpenClaw may construct a new signed Jason envelope with a new `request_id`, correlation ID, and nonce when the same Teams activity is retried. Request-ID replay protection alone therefore cannot prove that the underlying authenticated Teams activity has not already been accepted.

## Chosen proactive flow

1. Jason resolves the target user to a Microsoft Entra object ID.
2. Jason obtains a Microsoft Graph app-only token using its certificate identity.
3. Jason checks whether the organization Teams app is installed for the user.
4. If absent, Jason installs the app using Microsoft Graph.
5. Teams establishes the bot/user conversation context.
6. OpenClaw uses the resulting conversation reference to send the proactive message.
7. Jason records the install/bootstrap and delivery result in the central audit trail.

## Chosen inbound processing-feedback flow

1. The OpenClaw/Jason bridge receives the inbound Teams turn.
2. Required transport identity and conversation correlation fields are validated.
3. The bridge uses OpenClaw's supported channel outbound adapter to emit a static best-effort acknowledgement such as:

   `Received - working on that now...`

4. The bridge continues through the existing signed Jason conversation envelope and governed runtime path.
5. If acknowledgement delivery is unavailable or fails, the governed Jason request continues normally.
6. The final governed Jason response or error is the authoritative task outcome.

The acknowledgement must not contain chain-of-thought, hidden reasoning, provider evidence, secret material, authorization conclusions, or a statement that the requested work has completed.

## Chosen exact-message idempotency flow

1. Jason authenticates the signed OpenClaw transport envelope and resolves the trusted machine identity.
2. Jason validates the conversation contract and request freshness.
3. Existing request-ID replay protection claims the envelope `request_id` as before.
4. Jason derives a stable exact-message identity from authenticated transport fields:
   - Microsoft tenant ID;
   - Microsoft object ID;
   - Teams conversation ID; and
   - Teams message ID.
5. Jason joins those values with an unambiguous separator, SHA-256 hashes the compound identity, and claims it in the existing persistent `SQLiteReplayStore` using the namespace `teams-message-v1:`.
6. If the exact-message claim is new, the request continues through normal authenticated audit, identity binding, intent resolution, governance, and Central Orchestrator execution.
7. If the exact-message claim already exists, Jason records `openclaw.teams_conversation_duplicate_suppressed` and returns HTTP `200` with `status=duplicate` and `error_code=duplicate_message`.
8. A suppressed duplicate does not enter `TeamsConversationFlow.handle()` and does not create a second Central Orchestrator execution.
9. A different authenticated Teams message ID remains a new request even when its text is identical to an earlier message.

This is transport-activity idempotency only. Consequential capabilities may still require capability/action-level idempotency keys, preconditions, or provider-specific safe-retry semantics.

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
- Identity must be resolved and authorized before bootstrap or send where the communication itself is an orchestrated action.
- The inbound processing acknowledgement is limited to transport feedback after required inbound transport identity/conversation validation; it does not grant authority or replace downstream authorization.
- Proactive app installation is an auditable side effect.
- Message initiation must be attributable to a workflow, operator, or policy decision.
- Approval workflows must preserve the approval artifact and response evidence.
- Tokens and private keys must never be included in logs or agent context.
- Communication capabilities must be idempotent and safe to retry where side effects are possible.
- Duplicate inbound activities must not create parallel consequential work; exact-message idempotency belongs in the governed ingress/runtime boundary rather than being trusted solely to volatile interface memory.
- Exact-message identity must use stable authenticated transport identity/correlation fields, not request-text similarity.
- Request-ID replay protection and exact-message idempotency are separate controls and must both remain enforced.
- A distinct authenticated message ID must not be silently suppressed merely because the user repeated the same words.
- Duplicate suppression must be auditable and occur before governed conversation flow/orchestration execution.
- User-facing processing feedback must never expose chain-of-thought or imply task completion before the governed result exists.
- Future multi-worker/replica scale-out must preserve an atomic shared idempotency state layer before changing concurrency topology.

## Evidence

### Processing acknowledgement

The 2026-08-14 inbound processing-feedback implementation was validated with:

- static Node syntax validation;
- ten passing bridge tests;
- live host/container source parity;
- loaded `jason-bridge` and `msteams` plugins; and
- live Teams proof showing the acknowledgement immediately before the governed Jason response.

Durable implementation checkpoint:

`e98e4bd19e3881025f5167c5be57529961e73ebe` — `Add Teams processing acknowledgement for governed turns`

Durable proof record:

`docs/sessions/Teams-Processing-Feedback-Proof-2026-08-14.md`

### Exact-message idempotency

The 2026-08-14 exact-message idempotency implementation was validated with:

- focused duplicate-message regression tests;
- a deterministic in-flight concurrency test proving the second exact-message retry is suppressed while the first ingress flow is still active;
- passing full OpenClaw connector tests;
- passing full runtime-service tests;
- successful governed runtime rebuild and deployment;
- deployed image/source parity and runtime-hardening verification;
- trusted signing-key resolution by matching private-key-derived public fingerprints to the registered active public-key fingerprint rather than guessing among multiple PEM candidates;
- a live signed ingress proof in which the first governed Datto read completed successfully and a second independently signed envelope with a different request ID/correlation ID/nonce but the same Teams message ID returned `duplicate_message`;
- security audit proof showing authentication/completion for the first request and only `openclaw.teams_conversation_duplicate_suppressed` for the second; and
- persistent replay evidence showing two request-ID claims and exactly one exact-message claim.

Durable implementation checkpoint:

`aacc1cb7527e640331aa43cbc316c6c22c56ca77` — `Add exact Teams message idempotency`

Durable proof record:

`docs/sessions/Teams-Exact-Message-Idempotency-Proof-2026-08-14.md`

## Consequences

### Positive

- Jason can initiate onboarding and approval conversations with new employees.
- Users do not need to discover or manually contact Jason first.
- Teams remains the human-facing system of engagement while Jason orchestrates behind it.
- Microsoft-native identity and app installation mechanisms are reused rather than duplicated.
- Long-running governed inbound requests provide immediate visible receipt without weakening the Central Orchestrator boundary.
- Transport-feedback failure does not unnecessarily fail an otherwise valid governed request.
- Exact retries of the same authenticated Teams activity no longer create duplicate governed execution merely because OpenClaw generated a new request ID.
- Duplicate suppression is persistent and auditable across the existing runtime replay database rather than relying on volatile bridge memory.
- Repeated text in a genuinely new Teams message remains allowed, avoiding heuristic suppression of intentional user requests.

### Risks / costs

- Graph app installation is privileged and must be governed.
- The broader `TeamsAppInstallation.ReadWriteForUser.All` permission increases blast radius and requires ongoing least-privilege review.
- Conversation/bootstrap state must be tracked and retried safely.
- Certificate and token lifecycle management must be hardened beyond the original proof-of-concept.
- The bridge must continue to use supported OpenClaw interfaces rather than private Teams internals where possible.
- Exact-message ingress idempotency does not replace deeper action/provider idempotency for consequential side effects.
- The current runtime HTTP server is intentionally single-worker. Future scale-out requires an explicitly concurrency-safe shared state layer; the exact-message claim semantics must not be weakened when that topology changes.

## Retirement criteria

Replace or simplify proactive bootstrap if Microsoft Teams/OpenClaw gains a native proactive-conversation bootstrap API that removes the need for custom Graph app-install orchestration while preserving equivalent governance and auditability.

Replace or simplify the custom inbound processing acknowledgement if OpenClaw exposes a supported processing/typing lifecycle that reliably covers Jason's governed compatibility path while preserving the same identity, transport, audit, and failure boundaries.

Replace or simplify the current exact-message replay-store implementation if Jason adopts a shared distributed idempotency state service for multi-worker/replica operation, but only when the replacement preserves authenticated message identity scope, atomic claim semantics, auditability, request-ID replay protection, failure behavior, and Central Orchestrator boundaries.
