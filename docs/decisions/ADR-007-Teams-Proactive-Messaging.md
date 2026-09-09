# ADR-007 — Microsoft Teams as a Governed Jason Interaction Channel

**Status:** Accepted; proactive/outbound messaging remains active, while ordinary inbound Teams transport is superseded by ADR-009  
**Date:** 2026-08-10  
**Updated:** 2026-08-15  
**Identifier correction:** Originally created as `ADR-004` on 2026-08-10 and renumbered to `ADR-007` during documentation consolidation because Datto RMM already occupied ADR-004.

## Decision

Microsoft Teams is a supported governed Jason interaction and approval channel.

The interaction model now has two transport paths:

1. **Ordinary inbound Teams conversation turns** use the direct Jason Teams Gateway governed by ADR-009.
2. **Approved outbound/proactive Teams messaging** may continue to use OpenClaw/Graph bootstrap behavior governed by ADR-005 and this ADR until replaced by a separately approved transport.

This split does not create separate authority domains. Identity binding, exact-message idempotency, policy/approval, Central Orchestrator ownership, provider resolution, evidence, and audit remain Jason responsibilities.

## Proactive messaging decision

Jason will support proactive messaging to users who have never previously contacted the Teams app.

The currently approved bootstrap pattern is:

1. Jason resolves the target user to a Microsoft Entra object ID.
2. Jason obtains a Microsoft Graph app-only token through governed credential handling.
3. Jason checks whether the organization Teams app is installed for the user.
4. If absent and authorized, Jason installs the app through Microsoft Graph.
5. Teams establishes the bot/user conversation context.
6. The approved outbound transport sends the message.
7. Jason records bootstrap and delivery evidence in the central audit trail.

The original proof established that `TeamsAppInstallation.ReadWriteForUser.All` was required in this tenant even when the narrower self-install permission was present. Technology Steward governance must periodically re-evaluate whether the broader permission can be retired.

## Inbound processing feedback requirement

For governed inbound Teams turns that may take noticeable time, the active transport may emit a bounded processing acknowledgement after required transport identity/conversation fields are validated and before the governed runtime request begins.

Current acknowledgement:

`Received - working on that now...`

After ADR-009, this acknowledgement is emitted by the direct Jason Teams Gateway rather than the OpenClaw bridge.

The acknowledgement:

- is transport feedback only;
- does not grant authority;
- does not prove provider evidence;
- does not expose hidden reasoning;
- does not imply task completion; and
- must never replace the final governed result.

If acknowledgement delivery fails, the governed request may continue when the authenticated request itself remains valid.

## Exact-message idempotency requirement

Exact retries of an authenticated inbound Teams activity must be durably suppressed at the governed Jason ingress/runtime boundary before the conversation flow or Central Orchestrator executes the work a second time.

Jason derives stable exact-message identity from authenticated transport fields:

- Microsoft tenant ID;
- Microsoft object ID;
- Teams conversation ID; and
- Teams message ID.

The compound identity is hashed and claimed in persistent replay/idempotency state using the `teams-message-v1:` namespace. This remains separate from ordinary request-ID replay protection.

If the exact-message claim already exists, Jason records duplicate suppression and returns an idempotent duplicate result without entering governed conversation flow/orchestration again.

A distinct authenticated Teams message ID remains a distinct request even when its text matches an earlier message.

This is transport-activity idempotency only. Consequential capabilities may still require deeper capability/action-level idempotency keys, preconditions, or provider-specific safe-retry semantics.

## Microsoft identity linkage

The Teams application uses the Entra client/application ID:

`c94301b7-7194-46ab-aab7-94f9366f51a9`

Current tenant ID:

`f7054323-d52b-4863-8c2f-1898f0b6077c`

The organization Teams catalog application remains linked to the same Entra application identity.

ADR-009 added a dedicated direct-gateway application credential to the same Entra application without reading, replacing, or deleting the existing OpenClaw credential. Secret values are not documentation/evidence data.

## Governance requirements

- Agents may not directly call Teams or Microsoft Graph.
- Identity must be resolved and authorized before a governed outbound/bootstrap action.
- Microsoft authentication is identity evidence, not Jason execution authority.
- Proactive app installation is an auditable side effect.
- Message initiation must be attributable to a workflow, operator, or policy decision.
- Approval workflows must preserve approval artifacts and response evidence.
- Tokens/private keys/client credentials must never be placed in agent context, logs, System Registry values, or documentation.
- Communication actions must have explicit retry/idempotency semantics.
- Exact duplicate inbound Teams activities must not create parallel governed work.
- Request-ID replay protection and exact-message idempotency remain separate controls.
- User-facing processing feedback must never expose chain-of-thought or imply completion before the governed result exists.
- Future multi-worker/replica scale-out must preserve an atomic shared idempotency state layer before concurrency topology changes.

## Evidence

### Proactive/outbound foundation

Historical proof established:

- organization app publication;
- app-only Graph application installation;
- HTTP 201 installation for a previously uncontacted user;
- subsequent successful proactive Teams delivery through OpenClaw.

Operational details remain in `docs/operations/Runbook-Teams-Integration.md` and approval messaging runbooks.

### Processing acknowledgement

The 2026-08-14 acknowledgement was initially implemented through the OpenClaw bridge and proven in live Teams use.

Historical proof:

`docs/sessions/Teams-Processing-Feedback-Proof-2026-08-14.md`

ADR-009 preserves the behavior but moves its transport implementation into the direct Jason Teams Gateway.

### Exact-message idempotency

The 2026-08-14 idempotency implementation remains in Jason Runtime and therefore survived the transport cutover unchanged.

Historical proof:

`docs/sessions/Teams-Exact-Message-Idempotency-Proof-2026-08-14.md`

### Direct inbound production proof

The 2026-08-15 production proof established that the direct gateway receives and completes Teams turns while the OpenClaw model path is not involved in those ordinary inbound requests.

Proof:

`docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`

## Consequences

### Positive

- Teams remains a supported human-facing Jason channel.
- Proactive onboarding/approval conversations remain possible.
- Ordinary inbound Teams now has one exclusive transport owner before any model loop.
- The acknowledgement and exact-message idempotency controls survive the transport change.
- Microsoft identity and app-installation mechanisms are reused rather than duplicated.
- OpenClaw can remain available for approved outbound/proactive behavior while no longer racing Jason for ordinary inbound turns.

### Risks / costs

- outbound/proactive messaging and ordinary inbound messaging currently use different transport implementations;
- the broader Graph app-installation permission requires periodic least-privilege review;
- the direct gateway's temporary host-protected client credential requires migration into the preferred secret/federated architecture;
- OpenClaw's internal Teams provider should not be disabled until outbound/proactive dependencies are reviewed;
- exact-message ingress idempotency does not replace action/provider idempotency for consequential side effects.

## Relationship to other decisions

- ADR-005 remains active for approved OpenClaw outbound/proactive Teams transport.
- ADR-006 governs provider-neutral conversational routing and Central Orchestrator ownership.
- ADR-009 governs ordinary inbound Teams transport and supersedes this ADR's original OpenClaw-specific inbound implementation.

## Retirement criteria

Revisit the proactive/outbound portion when Microsoft/OpenClaw/direct-gateway capabilities allow a simpler approved transport with equal or stronger governance, auditability, identity, retry/idempotency, and rollback characteristics.

Revisit the current direct inbound transport only through ADR-009 or a successor decision.
