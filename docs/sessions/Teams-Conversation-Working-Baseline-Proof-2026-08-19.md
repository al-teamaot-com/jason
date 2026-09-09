# Teams Conversation Working Baseline Proof — 2026-08-19

**Date:** 2026-08-19  
**Status:** Proven working baseline  
**Workstream:** Teams conversational read path  
**Branch:** `feature/jason-runtime-service`

## Purpose

Preserve the first confirmed working Teams conversational baseline after the 2026-08-19 debugging cycle so future operators and AI sessions do not rediscover the same state or repeat failed experiments.

This proof is subordinate to the Jason Constitution, reference architecture, ADRs, System Registry, and current observed production evidence. It records the known-good conversation baseline and the exact evidence that established it.

## Baseline configuration

The successful baseline used the existing non-dynamic conversation path:

`JASON_DYNAMIC_CONVERSATION_ENABLED=false`

The configuration-only transition was performed with:

`bash infrastructure/jason-runtime/jason-ops.sh baseline-deploy`

Observed result:

- `BASELINE_IMAGE=jason-runtime:local`
- `BASELINE_BUILD=SKIPPED`
- `COMPOSE_VALIDATION=PASS`
- rollback image created as `jason-runtime:rollback-20260819-153336`
- runtime reached `healthy`
- `BASELINE_MODE=PASS`
- `JASON_DYNAMIC_CONVERSATION_ENABLED=false`
- `READY_FOR_LIVE_TEST=1`

This establishes configuration state only. It does not prove that unbuilt working-tree source changes are present in the running image. Source-code claims still require the provenance-verified refresh path documented in the baseline attempt log.

## Production ingress topology verified

Immediately before the successful live proof, observed production state was:

- `jason-runtime` — healthy, internal `8080/tcp`
- `jason-teams-gateway` — running, `0.0.0.0:3978->3979/tcp`
- `openclaw-openclaw-gateway-1` — healthy, published only on `18789-18790`

The runtime mode was verified as:

`JASON_DYNAMIC_CONVERSATION_ENABLED=false`

The direct Teams gateway runtime target was verified as:

`JASON_RUNTIME_URL=http://jason-runtime:8080/v1/openclaw/teams/conversation`

The gateway and runtime shared the `jason-core` Docker network.

## Ingress repair performed

The live Teams turn was not initially visible in gateway evidence. To restore the documented direct ingress path without changing planner, Datto, semantic, or runtime application code, only `jason-teams-gateway` was recreated from the already-installed production image:

`jason-teams-gateway:production`

The recreation preserved the documented production contract:

- same Microsoft Teams credential file at `/opt/jason/services/jason-teams-gateway/msteams.env`
- same governed ingress signing key at `/opt/jason/services/jason-teams-gateway/secrets/ingress.pem`
- same runtime URL `http://jason-runtime:8080/v1/openclaw/teams/conversation`
- same ingress key ID `openclaw-gateway-2`
- same `jason-core` Docker network
- same host mapping `3978 -> 3979`
- no runtime rebuild
- no planner change
- no Datto change
- no semantic mapping change
- no OpenClaw routing change

The recreated gateway container ID began:

`0ea86f0f6d8f...`

## Connectivity proof

After gateway recreation:

- Docker DNS resolved `jason-runtime` to `172.19.0.2`
- TCP connection from `jason-teams-gateway` to `jason-runtime:8080` passed
- `jason-teams-gateway` owned host port `3978`
- `jason-runtime` remained healthy
- `openclaw-openclaw-gateway-1` remained healthy and did not own host port `3978`

## Live Teams proof

The regression question was sent in Microsoft Teams:

`When was AOT-50107 last seen?`

The direct gateway then emitted:

```text
{"event":"jason_teams_gateway_started","port":3979,"tenantId":"f7054323-d52b-4863-8c2f-1898f0b6077c","clientId":"c94301b7-7194-46ab-aab7-94f9366f51a9"}
{"event":"jason_teams_turn_completed","status":"completed","httpStatus":200,"conversationId":"a:1OHDLSOI1q1Q__cbeAT5B1JDBmxw298L53JZshpQVGJvBhGbIWIyjri1H3zkJu2GiBBi4aP90SVBcDb5GIqkr4dD9GS23cMQ91Kcmz0LgDQbKBfa9PlVqQaf6baLpR3Ah","messageId":"1787168773572"}
```

This proves the live turn traversed the direct Teams gateway and completed successfully through the configured Jason Runtime conversation boundary with HTTP 200.

## What this proves

This proof establishes a working conversation baseline for:

`Microsoft Teams -> direct jason-teams-gateway -> signed Jason conversation envelope -> jason-runtime -> governed conversation path -> response -> Teams`

It also confirms that the non-dynamic baseline remains operational after the recent dynamic-planner experiments were removed from the active runtime path.

This proof does **not** by itself establish that the dynamic conversation architecture is correct, nor does it validate unbuilt working-tree changes.

## Dynamic-planner result that must not be rediscovered

Before returning to the non-dynamic baseline, the dynamic planner was constrained experimentally to one requirement and tested five times against the real offered capability catalog for:

`When was AOT-50107 last seen?`

All five runs selected:

`endpoint.alert.history.search`

The single-capability safety bound itself worked mechanically, but it did not correct semantic capability selection. The experimental `_MAX_REQUIREMENTS = 1` change was therefore restored to `_MAX_REQUIREMENTS = 12` and must not be reintroduced as though it solved routing.

The documented lesson remains:

- single-capability execution is a baseline architectural stage;
- merely limiting the dynamic planner to one capability does not make its semantic selection correct;
- do not add phrase-specific `last seen` routing or bespoke question mappings;
- do not treat token-budget or model-size tuning as the primary architecture strategy;
- reintroduce dynamic capability discovery only after preserving this known-good baseline and changing one major behavior at a time.

## Gateway observability defect discovered

A tooling mismatch was discovered during this proof.

The direct gateway source emits failed-closed turns as:

`jason_teams_turn_failed_closed`

The current `jason-ops.sh capture` gateway grep does not include that event name. Therefore an empty gateway section in `jason-ops.sh capture` cannot currently be interpreted as proof that no failed-closed gateway turn occurred.

Future maintenance should align the capture helper with the gateway's actual event vocabulary.

A separate shell quoting defect also occurred in an ad-hoc Node health command because Bash history expansion interpreted `!r.ok`. That command failure did not affect the gateway process or live Teams proof. Do not reuse that exact double-quoted Node expression interactively.

## Known-good baseline rule

Until a later constitutional improvement is independently proven, preserve this state as the conversational working reference:

1. direct `jason-teams-gateway` owns ordinary inbound Teams transport;
2. `jason-runtime` remains the governed conversation/orchestration boundary;
3. `JASON_DYNAMIC_CONVERSATION_ENABLED=false` for the working baseline;
4. Central Orchestrator, identity, provider governance, evidence, and return transport remain in place;
5. dynamic capability discovery must be reintroduced as one bounded architectural step, not together with dynamic binding, evidence sufficiency, and multi-capability fulfillment;
6. every later improvement must re-run the live baseline before being retained.

## Next safe architectural step

Do not resume random debugging of the regression sentence.

The next architectural work should start from the sequence already defined in `docs/operations/Teams-Conversation-Working-Baseline-2026-08-18.md`:

1. preserve/freeze this known-good non-dynamic baseline;
2. add automated regression coverage around the observed working contract;
3. then introduce runtime capability discovery while retaining single-capability execution;
4. verify the general discovery contract independently from the `AOT-50107` wording;
5. only after that passes, proceed to dynamic grounding and later constitutional stages one at a time.

The regression question is evidence and a fixture, not the specification for Jason.
