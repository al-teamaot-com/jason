# ADR-009 — Direct Microsoft Teams Ingress Gateway

**Status:** Accepted and production-proven  
**Decision owner:** Jason Architecture Authority  
**Date:** 2026-08-15  
**Supersedes:** ADR-005 and ADR-007 only for ordinary inbound Microsoft Teams transport into Jason. Their outbound/proactive-messaging decisions remain in force unless separately superseded.

## Context

Jason originally routed ordinary Microsoft Teams conversation turns through OpenClaw. The intended design was sound at the authority level — OpenClaw as transport only, Jason as the governed execution authority — but the deployed OpenClaw lifecycle did not expose a reliable interception point that could guarantee an ordinary Teams turn was exclusively claimed by Jason before OpenClaw's own model/agent path executed.

Production investigation established several important facts:

- a Teams conversation could be correctly bound to the `jason-bridge` plugin and still enter OpenClaw's normal GPT-backed agent path;
- `before_agent_run`, `before_agent_reply`, and plugin-owned inbound-claim approaches did not reliably execute for the live Teams path;
- patching the live OpenClaw Teams bundle proved brittle across packaging/runtime structure and was abandoned after repeated failures;
- allowing OpenClaw's model path and Jason's governed path to compete for the same ordinary Teams turn creates an unacceptable parallel-intelligence and parallel-authority risk.

The correct architectural response is to remove OpenClaw from ordinary inbound Teams ingress rather than continue adding hooks or private bundle patches.

## Decision

Ordinary inbound Microsoft Teams messages for Jason will enter a dedicated, minimal **Jason Teams Gateway** before any model or OpenClaw agent loop.

The production inbound path is:

`Microsoft Teams -> teams-jason.teamaot.com/api/messages -> public relay -> ZeroTier -> Jason host TCP 3978 -> jason-teams-gateway:3979 -> signed Jason conversation envelope -> jason-runtime -> governed conversation flow -> Central Orchestrator -> governed capability/provider -> deterministic response -> Microsoft Teams`

The gateway:

- uses the Microsoft Agents SDK for authenticated Bot Framework/Teams request handling;
- validates the configured Microsoft tenant and the authenticated Entra object ID supplied by the Teams activity;
- accepts text requests only on the governed conversation path;
- emits the bounded acknowledgement `Received - working on that now...` after required transport identity/conversation validation;
- reuses Jason's existing Ed25519 trusted-ingress signing identity and signed conversation-envelope contract;
- posts only to the governed Jason runtime boundary;
- renders only the runtime's deterministic governed result;
- contains no LLM, agent loop, provider credentials, provider-selection logic, business authority, or direct provider invocation.

The current runtime endpoint remains `/v1/openclaw/teams/conversation` for compatibility with the already-proven ingress contract. The path name is a legacy implementation name, not authority granted to OpenClaw.

## Production port ownership

The 2026-08-15 cutover preserves the existing public Microsoft/relay endpoint and changes only the owner of the Jason host's Teams ingress port:

- `jason-teams-gateway` publishes host `0.0.0.0:3978` to container port `3979`;
- `openclaw-openclaw-gateway-1` remains running and healthy on host ports `18789-18790`;
- OpenClaw no longer publishes host port `3978`;
- the OpenClaw `msteams` provider may still initialize internally, but it is not the externally reachable ordinary Teams ingress path while the host port remains owned by `jason-teams-gateway`.

This preserves the public Teams registration and avoids an unnecessary Microsoft-side endpoint migration.

## Microsoft application identity

The gateway uses the existing Jason Teams/Entra application identity:

- tenant ID: `f7054323-d52b-4863-8c2f-1898f0b6077c`;
- application/client ID: `c94301b7-7194-46ab-aab7-94f9366f51a9`.

A second application credential named for the Project Jason Teams Gateway was appended to the existing Entra application during the migration. The existing OpenClaw credential was not read, replaced, or deleted.

The dedicated gateway credential is currently stored on the Jason host in a mode-`0600` environment file at `/opt/jason/services/jason-teams-gateway/msteams.env`. The secret value is never recorded in Git, System Registry, audit evidence, or documentation.

This host-protected file is an accepted migration state, not the preferred long-term secret-delivery architecture. Moving this credential to Jason's governed secret-provider path or a certificate/federated identity is a hardening follow-up.

## Authority and governance boundaries

The direct gateway changes transport topology only. It does not change Jason's authority model.

The following remain mandatory:

- Microsoft authentication is identity evidence, not execution authority.
- Jason re-binds the Microsoft tenant/object identity to a Jason principal and organization.
- Exact authenticated Teams-message idempotency remains enforced in the governed runtime before conversation flow/orchestration execution.
- Resource/capability planning remains provider-neutral.
- Only the Central Orchestrator may select and invoke governed capabilities/providers.
- Agents may not invoke providers, connectors, shells, or other agents directly.
- Provider evidence must be established before Jason presents operational facts.
- Unknown identity, invalid tenant, invalid conversation context, unavailable runtime, signature failure, or governed runtime failure fails closed.
- The acknowledgement is transport feedback only and never constitutes authorization, evidence, task completion, or reasoning output.

## Relationship to OpenClaw

OpenClaw remains a deployed Jason ecosystem component and may continue to provide other approved interface/transport functions, including currently documented proactive/outbound Teams capabilities where those paths remain operational and governed.

For **ordinary inbound Teams conversation turns**, OpenClaw is no longer the transport owner. Future work must not restore OpenClaw to that ingress path through undocumented hooks, model routing, or bundle patching without a new governed architectural decision and equivalent exclusive-ownership proof.

The `infrastructure/openclaw-jason-bridge/` implementation remains historical/compatibility material and may still support other bounded uses, but it is not the production owner of ordinary inbound Teams messages after this cutover.

## Rejected approaches

1. **Continue adding OpenClaw hooks** — rejected because multiple supported/observed hook points failed to execute reliably for the live Teams path.
2. **Treat plugin binding as proof of exclusive ownership** — rejected because a plugin-bound session was observed entering the OpenClaw model path.
3. **Patch the live OpenClaw Teams bundle** — rejected because the package/runtime layout was brittle and the approach failed repeatedly before safe production cutover.
4. **Allow both OpenClaw and Jason to answer the same Teams turn** — rejected because it creates parallel intelligence, conflicting responses, and an authority bypass risk.
5. **Change the Microsoft public endpoint unnecessarily** — rejected because the existing public path already terminates on host port 3978; changing local port ownership is simpler and easier to reverse.

## Deployment and rollback

Production deployment is owned by:

- `infrastructure/jason-teams-gateway/Dockerfile`;
- `infrastructure/jason-teams-gateway/deploy-pilot.sh`;
- `infrastructure/jason-teams-gateway/cutover-production.sh`;
- `infrastructure/jason-teams-gateway/rollback-production.sh`.

The cutover procedure:

1. requires a healthy isolated pilot;
2. inspects actual Docker runtime bindings rather than assuming the raw Compose representation;
3. preserves all OpenClaw published ports except host `3978`;
4. validates the resulting Compose configuration before replacing the live file;
5. backs up the original OpenClaw Compose file;
6. recreates OpenClaw without host `3978`;
7. starts the direct gateway on host `3978`;
8. verifies gateway health and port ownership;
9. records rollback state; and
10. automatically attempts rollback if a post-mutation cutover step fails.

Rollback removes the direct gateway, restores the backed-up OpenClaw Compose file, recreates OpenClaw, and verifies that OpenClaw regains host port `3978`.

## Production proof

The 2026-08-15 live Teams test asked:

`Hey Jason, can you tell me who was last on AOT-50282 and if anything is wrong with it right now?`

The governed response returned Datto RMM evidence:

- last logged-in user: `AzureAD\AlDavis`;
- one moderate `Unhealthy` alert;
- local-user additions: `CodexSandboxOffline` and `CodexSandboxOnline`;
- source: `datto_rmm`.

The direct gateway log recorded completed HTTP `200` turns. The same evidence window contained no OpenClaw `dispatching to agent` or plugin-bound Teams execution for those turns. Service-state evidence showed the direct gateway owning host `3978`, OpenClaw healthy only on `18789-18790`, and `jason-runtime` healthy.

Durable proof record:

`docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`

Primary cutover implementation checkpoint:

`1e3003f74845f4af6786a6ab36d8e99b20fbcdce` — `Release Teams port from resolved OpenClaw bindings`

## Consequences

### Positive

- one ordinary Teams message has one ingress owner;
- OpenClaw's model cannot race Jason for ordinary inbound Teams turns through the external ingress path;
- Jason's existing identity, replay, idempotency, governance, Central Orchestrator, provider, evidence, and rendering controls are preserved;
- the public Teams endpoint remains stable;
- OpenClaw remains available for unrelated approved functions;
- the direct gateway is small, replaceable, auditable, and intentionally non-intelligent.

### Costs / follow-up

- Jason now owns a dedicated Microsoft Teams ingress service and its operational lifecycle;
- the dedicated Microsoft application credential requires governed rotation and migration into the preferred secret architecture;
- the OpenClaw `msteams` provider remains internally configured and should be disabled for inbound use as a hardening cleanup once outbound/proactive dependencies are reviewed;
- System Registry and operational documentation must represent the direct gateway as current Teams ingress and must not imply that the OpenClaw bridge still owns ordinary inbound Teams routing.

## Retirement criteria

Revisit this ADR when one of the following is true:

- Microsoft provides a materially simpler supported ingress mechanism that preserves authenticated identity and Jason's governance boundary;
- Jason adopts another replaceable Teams/interface adapter with equivalent exclusive ownership, auditability, rollback, and Central Orchestrator enforcement;
- OpenClaw later provides a formally supported exclusive handoff mechanism that can be independently proven not to enter an OpenClaw model/agent path before Jason claims the turn.

Any replacement must preserve identity-first authorization, exact-message idempotency, signed/trusted ingress, evidence-before-assertion, fail-closed behavior, and Central Orchestrator ownership.
