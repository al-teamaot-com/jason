# Project Jason — Current Resume Point

**Updated:** 2026-08-19  
**Status:** Ordinary Microsoft Teams ingress is production-proven through the dedicated `jason-teams-gateway`. A working non-dynamic Teams conversational baseline is now re-proven live with `JASON_DYNAMIC_CONVERSATION_ENABLED=false`; the direct gateway completed a real Teams turn with HTTP 200 after being recreated from the already-installed production gateway image.  
**Canonical purpose:** Human-readable resume point for current work. Current production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

Future sessions should read, in order:

1. `docs/index.md`
2. `docs/control/JASON-FUNDAMENTALS.md`
3. this file
4. `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
5. `docs/control/DOCUMENTATION-REGISTER.md`
6. `docs/control/HOW-TO-DOCUMENT-JASON.md`
7. `docs/operations/Teams-Conversation-Working-Baseline-2026-08-18.md`
8. `docs/operations/Teams-Conversation-Baseline-Attempt-Log-2026-08-19.md`
9. `docs/sessions/Teams-Conversation-Working-Baseline-Proof-2026-08-19.md`
10. `docs/decisions/ADR-009-Direct-Microsoft-Teams-Ingress.md`
11. `docs/decisions/ADR-006-Governed-Conversational-Interface-Routing.md`
12. `docs/operations/Runbook-Teams-Integration.md`
13. `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`
14. current Git and System Registry/host evidence before asserting live production state

Conversation memory is context only. It is not authority.

## Current working Teams conversational baseline — 2026-08-19

The currently proven working conversational baseline is:

`Microsoft Teams -> teams-jason.teamaot.com/api/messages -> relay/ZeroTier -> Jason host :3978 -> jason-teams-gateway:3979 -> signed Jason ingress -> jason-runtime -> governed non-dynamic conversation path -> Central Orchestrator -> governed provider -> response -> Teams`

The runtime configuration for this known-good baseline is:

`JASON_DYNAMIC_CONVERSATION_ENABLED=false`

The configuration-only baseline transition completed with:

- `BASELINE_IMAGE=jason-runtime:local`
- `BASELINE_BUILD=SKIPPED`
- `COMPOSE_VALIDATION=PASS`
- `BASELINE_MODE=PASS`
- `JASON_DYNAMIC_CONVERSATION_ENABLED=false`
- `READY_FOR_LIVE_TEST=1`

Observed service state before the final live proof:

- `jason-runtime` healthy on internal `8080/tcp`;
- `jason-teams-gateway` on `0.0.0.0:3978->3979/tcp`;
- `openclaw-openclaw-gateway-1` healthy on host `18789-18790` only.

The direct gateway was recreated from the already-installed `jason-teams-gateway:production` image without changing runtime application code, planner code, Datto code, semantic mappings, or OpenClaw routing. The recreated gateway:

- joined Docker network `jason-core`;
- resolved `jason-runtime` successfully;
- connected to `jason-runtime:8080` successfully;
- retained the governed ingress signing key and dedicated Teams credential file;
- retained the documented runtime target `http://jason-runtime:8080/v1/openclaw/teams/conversation`;
- owned host port `3978`.

The live regression request was:

`When was AOT-50107 last seen?`

The direct gateway emitted:

```text
{"event":"jason_teams_gateway_started","port":3979,"tenantId":"f7054323-d52b-4863-8c2f-1898f0b6077c","clientId":"c94301b7-7194-46ab-aab7-94f9366f51a9"}
{"event":"jason_teams_turn_completed","status":"completed","httpStatus":200,"conversationId":"a:1OHDLSOI1q1Q__cbeAT5B1JDBmxw298L53JZshpQVGJvBhGbIWIyjri1H3zkJu2GiBBi4aP90SVBcDb5GIqkr4dD9GS23cMQ91Kcmz0LgDQbKBfa9PlVqQaf6baLpR3Ah","messageId":"1787168773572"}
```

Durable proof:

`docs/sessions/Teams-Conversation-Working-Baseline-Proof-2026-08-19.md`

### Do not rediscover these conclusions

1. The working baseline is the non-dynamic path with `JASON_DYNAMIC_CONVERSATION_ENABLED=false`.
2. The direct `jason-teams-gateway` is the ordinary inbound Teams transport owner. Do not route ordinary inbound Teams back through OpenClaw.
3. The Central Orchestrator, identity boundary, Datto execution path, provider governance, evidence path, and Teams return transport are retained baseline components, not redesign targets without new evidence.
4. A dynamic-planner experiment constrained the plan to one capability and mechanically enforced the bound, but the real catalog still selected `endpoint.alert.history.search` five out of five times for `When was AOT-50107 last seen?`. The temporary `_MAX_REQUIREMENTS = 1` change was restored to `12`; do not reintroduce it as though it solved routing.
5. Do not add phrase-specific `last seen` routing, question-to-field mappings, or bespoke workflow logic to make this regression sentence pass.
6. Do not treat model-size or token-budget tuning as the primary architecture strategy for the dynamic path.
7. Reintroduce constitutional behavior one major step at a time from the working baseline: runtime capability discovery with single-capability execution first, then dynamic grounding, then later continuity/evidence/multi-capability stages.
8. `jason-ops.sh capture` currently misses gateway event `jason_teams_turn_failed_closed`; an empty gateway capture section is therefore not proof that no failed-closed gateway turn occurred. Align the helper with the actual gateway event vocabulary before relying on that inference.
9. An ad-hoc Node health command using a double-quoted `!r.ok` expression failed because Bash history expansion consumed `!`; that shell error did not affect the gateway or the successful live proof. Do not reuse that exact command form.
10. Configuration-only `baseline-deploy` proves runtime configuration, not newly pulled source. Any claim about changed source requires the provenance-verified source refresh path documented in the attempt log.

## Previous durable ingress success — 2026-08-15

On 2026-08-15, ordinary Teams ingress was cut over from OpenClaw to a dedicated non-intelligent Jason Teams Gateway.

The production regression request was:

`Hey Jason, can you tell me who was last on AOT-50282 and if anything is wrong with it right now?`

The Teams response returned:

- last logged-in user `AzureAD\AlDavis`;
- one moderate `Unhealthy` alert;
- added local users `CodexSandboxOffline` and `CodexSandboxOnline`;
- evidence source `datto_rmm`.

Direct gateway logs recorded completed HTTP `200` turns. The same evidence window contained no OpenClaw `dispatching to agent` event for those ordinary Teams turns.

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

The active conversational workstream is now **working-baseline preservation followed by constitutional evolution one major behavior at a time**.

### Repository candidate — durable hosted-model usage correlation

The feature branch now contains a repository-only candidate for durable model-usage
accounting. This is not yet a production-state claim. The candidate:

- provides a mode-`0600` SQLite implementation of the existing append-only usage
  ledger contract;
- binds accounting context at the authenticated Teams turn boundary after Jason
  identity and organization scope are known;
- correlates hosted OpenAI attempts with the Teams conversation/message, Jason
  principal, organization/client scope, and turn correlation identifier;
- records provider-reported input, cached-input, output, reasoning, and total token
  fields when supplied;
- records duration, provider request identity, outcome, model, retry/fallback attempt
  identity, and unknown usage for failed calls without persisting prompts or raw
  provider responses; and
- keeps accounting context non-authoritative: it cannot select scope, capability,
  provider execution, credentials, or policy.

The committed persistence and accounting smoke tests pass in the development
workspace. Full repository acceptance and live deployment/proof remain required
before this candidate may be described as operational.

The immediate sequence is:

1. preserve/freeze the 2026-08-19 working non-dynamic baseline with regression coverage and durable evidence;
2. correct the gateway capture helper so its event vocabulary matches the gateway implementation;
3. reintroduce runtime capability discovery while retaining single-capability execution;
4. prove that discovery generally, independently of the `AOT-50107` wording;
5. only after that is stable, proceed to dynamic selector grounding;
6. continue later stages only after re-proving the baseline after each change.

The direct-gateway hardening/lifecycle items remain valid but are separate from the conversational baseline sequence:

- keep the System Registry/current generated operational view aligned with the direct gateway topology;
- review whether OpenClaw's dormant inbound `msteams` listener/provider can be disabled without breaking approved outbound/proactive Teams messaging;
- migrate the direct gateway's dedicated Microsoft client credential from the temporary mode-0600 host environment file into Jason's preferred governed secret-delivery/federated identity architecture;
- revoke/retire obsolete Microsoft application credentials when migration is complete.

## Production/runtime boundary

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

The cutover backup observed during the original 2026-08-15 proof was:

`/opt/jason/services/openclaw/docker-compose.yml.pre-jason-teams-20260815T173328Z`

These are point-in-time proof values. Verify current state before future mutation.

## Unresolved controls / risks

1. **Teams gateway secret delivery:** the dedicated client credential is protected but still host-file based. Preferred long-term state is governed OpenBao/secret delivery or certificate/federated identity.
2. **Dormant OpenClaw inbound Teams configuration:** OpenClaw no longer owns host `3978`, but its internal Teams provider remains configured. Disable inbound behavior only after confirming outbound/proactive dependencies.
3. **Clarification continuation state:** stateless ambiguity clarification remains operational; short replies such as `LAN` still require separately governed continuation state before they may inherit earlier context.
4. **Runtime concurrency topology:** the production runtime remains intentionally single-worker; future replicas require atomic shared idempotency state.
5. **Consequential-action idempotency:** transport message idempotency does not replace capability/action/provider side-effect idempotency.
6. **System Registry Datto read-surface completeness:** active Datto read capabilities should continue to be reconciled with current verified registry lifecycle rather than inferred from successful conversation alone.
7. **Gateway capture helper event mismatch:** `jason-ops.sh capture` does not currently include `jason_teams_turn_failed_closed`, so gateway failure evidence can be omitted from standard capture output.
8. **Dynamic capability selection:** the current dynamic planner is not yet a reliable replacement for the known-good non-dynamic baseline; real-catalog testing still selected alert history for the endpoint `last seen` request.
9. **OpenClaw plugin-registry metadata warning and pre-existing approval-test debt:** remain separate controlled maintenance items.

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
- rollback and verification before declaring transport topology changes complete;
- a known-good live baseline after each major conversational architecture change.

## Next safe actions

1. Treat `docs/sessions/Teams-Conversation-Working-Baseline-Proof-2026-08-19.md` as the current live conversational checkpoint.
2. Add/freeze automated regression coverage around the known-good non-dynamic conversation contract.
3. Correct `jason-ops.sh capture` to include the gateway's actual failed-closed event.
4. Reintroduce runtime capability discovery while retaining single-capability execution and without adding question-specific mappings.
5. Re-run the live Teams baseline immediately after that one major change; revert or isolate if it breaks.
6. Continue constitutional evolution only one major behavior at a time.
7. Independently continue System Registry alignment and gateway credential hardening as governed infrastructure workstreams.

## Documentation-complete condition for this workstream

The Teams conversational baseline workstream is documentation-complete when a future operator/AI can determine without chat history:

- which component owns ordinary Teams ingress;
- which runtime mode is the known-good conversational baseline;
- how that baseline was proven live;
- which dynamic-planner experiments failed and must not be rediscovered;
- how configuration-only transitions differ from source-code refreshes;
- which capture/tooling defect can hide gateway failed-closed events;
- the next single constitutional improvement to introduce;
- how to verify, revert, and preserve a working baseline after each major change; and
- which separate gateway hardening items remain outstanding.
