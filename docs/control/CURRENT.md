# Project Jason — Current Resume Point

**Updated:** 2026-08-15  
**Status:** Ordinary Microsoft Teams ingress is now production-proven through the dedicated `jason-teams-gateway`, with OpenClaw removed from externally reachable ordinary inbound Teams routing. The live Teams request completed through Jason Runtime/Central Orchestrator and Datto RMM with provider-derived evidence and no matching OpenClaw model dispatch.  
**Canonical purpose:** Human-readable resume point for current work. Current production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

Future sessions should read, in order:

1. `docs/index.md`
2. `docs/control/JASON-FUNDAMENTALS.md`
3. this file
4. `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
5. `docs/control/DOCUMENTATION-REGISTER.md`
6. `docs/control/HOW-TO-DOCUMENT-JASON.md`
7. `docs/decisions/ADR-009-Direct-Microsoft-Teams-Ingress.md`
8. `docs/decisions/ADR-006-Governed-Conversational-Interface-Routing.md`
9. `docs/operations/Runbook-Teams-Integration.md`
10. `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`
11. current Git and System Registry/host evidence before asserting live production state

Conversation memory is context only. It is not authority.

## Last durable success

On 2026-08-15, ordinary Teams ingress was cut over from OpenClaw to a dedicated non-intelligent Jason Teams Gateway.

Current proven inbound path:

`Microsoft Teams -> teams-jason.teamaot.com/api/messages -> relay/ZeroTier -> Jason host :3978 -> jason-teams-gateway:3979 -> signed Jason ingress -> jason-runtime -> Central Orchestrator -> governed provider -> deterministic response -> Teams`

The live production regression request was:

`Hey Jason, can you tell me who was last on AOT-50282 and if anything is wrong with it right now?`

The Teams response returned:

- last logged-in user `AzureAD\AlDavis`;
- one moderate `Unhealthy` alert;
- added local users `CodexSandboxOffline` and `CodexSandboxOnline`;
- evidence source `datto_rmm`.

Direct gateway logs recorded completed HTTP `200` turns. The same evidence window contained no OpenClaw `dispatching to agent` event for those ordinary Teams turns.

Final observed service state:

- `jason-teams-gateway` owned host `3978 -> container 3979`;
- `openclaw-openclaw-gateway-1` remained healthy on host `18789-18790` only;
- `jason-runtime` remained healthy on internal port `8080`.

Durable architecture decision:

`docs/decisions/ADR-009-Direct-Microsoft-Teams-Ingress.md`

Durable production proof:

`docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`

Primary cutover implementation checkpoint:

`1e3003f74845f4af6786a6ab36d8e99b20fbcdce` — `Release Teams port from resolved OpenClaw bindings`

## Why the ingress architecture changed

The prior OpenClaw-based ordinary inbound path could not prove exclusive Jason ownership before OpenClaw's model path.

The following approaches were attempted and abandoned rather than accumulated indefinitely:

- `before_agent_run` hook;
- `before_agent_reply` hook;
- plugin-owned inbound claim;
- direct live OpenClaw Teams bundle patching.

A plugin-bound Teams session was observed still entering the OpenClaw GPT-backed agent path. After repeated failures of the interception approach, Jason changed architecture instead of continuing brittle patching.

The durable rule is now: **ordinary Jason-bound Teams ingress has one transport owner before any model loop.**

## Current workstream

The direct Teams ingress routing workstream is complete and production-proven.

The next work is **hardening and lifecycle cleanup**, not more routing debugging:

1. keep the System Registry/current generated operational view aligned with the direct gateway topology;
2. review whether OpenClaw's dormant inbound `msteams` listener/provider can be disabled without breaking approved outbound/proactive Teams messaging;
3. migrate the direct gateway's dedicated Microsoft client credential from the temporary mode-0600 host environment file into Jason's preferred governed secret-delivery/federated identity architecture;
4. revoke/retire obsolete Microsoft application credentials when migration is complete;
5. then return to the previously planned governed clarification-continuation workstream.

## Current production boundary

### Ordinary inbound Teams

Owned by `jason-teams-gateway` under ADR-009.

The gateway:

- authenticates through the Microsoft Agents SDK;
- validates tenant and authenticated Entra object identity;
- emits only bounded transport acknowledgement text;
- signs the existing trusted Jason conversation envelope;
- calls only the governed Jason Runtime boundary;
- contains no LLM, agent loop, provider-selection authority, business authority, or direct provider invocation.

### Jason Runtime

`jason-runtime` remains the governed conversation/orchestration boundary. Existing identity binding, replay protection, exact-message idempotency, resource inquiry, policy, Central Orchestrator, provider resolution, evidence, and deterministic response controls remain in force.

### OpenClaw

OpenClaw remains a deployed ecosystem/interface component and may still support approved outbound/proactive Teams behavior and other functions.

For ordinary inbound Teams turns it no longer owns the external host port and must not be treated as the active ingress merely because its internal `msteams` provider logs a startup message.

ADR-005 remains applicable to approved outbound/proactive OpenClaw Teams transport. ADR-009 supersedes it for ordinary inbound Teams ingress.

## Credential state

The direct gateway uses the existing Teams/Entra application identity:

- tenant ID `f7054323-d52b-4863-8c2f-1898f0b6077c`;
- application/client ID `c94301b7-7194-46ab-aab7-94f9366f51a9`.

A dedicated second application credential was appended for the direct gateway. The existing OpenClaw credential was not read, replaced, or deleted.

Current migration storage:

`/opt/jason/services/jason-teams-gateway/msteams.env`

Protection at creation: mode `0600`.

No secret value is stored in Git, documentation, or System Registry.

## Rollback state

Production cutover created a persistent rollback state file:

`/opt/jason/services/jason-teams-gateway/cutover-state.env`

The rollback entry point is:

`bash infrastructure/jason-teams-gateway/rollback-production.sh`

The cutover backup observed during proof was:

`/opt/jason/services/openclaw/docker-compose.yml.pre-jason-teams-20260815T173328Z`

These are point-in-time proof values. Verify current state before future mutation.

## Unresolved controls / risks

1. **Teams gateway secret delivery:** the dedicated client credential is protected but still host-file based. Preferred long-term state is governed OpenBao/secret delivery or certificate/federated identity.
2. **Dormant OpenClaw inbound Teams configuration:** OpenClaw no longer owns host `3978`, but its internal Teams provider remains configured. Disable inbound behavior only after confirming outbound/proactive dependencies.
3. **Clarification continuation state:** stateless ambiguity clarification remains operational; short replies such as `LAN` still require separately governed continuation state before they may inherit earlier context.
4. **Runtime concurrency topology:** the production runtime remains intentionally single-worker; future replicas require atomic shared idempotency state.
5. **Consequential-action idempotency:** transport message idempotency does not replace capability/action/provider side-effect idempotency.
6. **System Registry Datto read-surface completeness:** active Datto read capabilities should continue to be reconciled with current verified registry lifecycle rather than inferred from successful conversation alone.
7. **OpenClaw plugin-registry metadata warning and pre-existing approval-test debt:** remain separate controlled maintenance items.

## Continuity rules now in force

Future conversational/interface work must preserve:

- one exclusive ordinary inbound transport owner before any model loop;
- authenticated transport identity as evidence, not execution authority;
- Jason identity/organization binding before execution;
- exact-message idempotency before governed work begins;
- provider-neutral resource/action interpretation;
- Central Orchestrator as sole execution coordinator;
- no direct agent-to-agent/provider/connector bypass;
- deterministic authority/provider/evidence boundaries outside model discretion;
- bounded model use only where explicitly allowed;
- provider-derived evidence before operational assertions;
- source attribution;
- fail-closed behavior on identity, authority, planning, evidence, signature, or provider failure;
- no bespoke one-off script merely because a new human wording appears;
- rollback and verification before declaring transport topology changes complete.

## Next safe actions

1. Validate the repository System Registry and generated operational view contain `component.jason-teams-gateway` and current Teams ingress ownership.
2. Preserve the direct-gateway production proof and ADR-009 as the canonical historical decision/evidence pair.
3. Review outbound/proactive Teams dependence on OpenClaw before disabling its internal `msteams` provider.
4. Design a governed credential migration for the direct gateway without printing or copying the current client credential.
5. After hardening, resume the governed clarification-continuation design using explicit Jason-owned, authenticated, expiring, auditable state.

## Documentation-complete condition for this workstream

The direct Teams ingress workstream is documentation-complete when durable repository records allow a future operator/AI to determine without chat history:

- why OpenClaw ordinary inbound ingress was retired;
- which ADR now governs the transport;
- the exact current service/port ownership model;
- how to deploy, verify, and roll back the direct gateway;
- how the Microsoft identity/credential is handled without storing secret values;
- what live evidence proved the Datto-backed Teams request and OpenClaw model bypass;
- what System Registry entities represent the current topology; and
- which remaining items are hardening/future work rather than unresolved routing defects.
