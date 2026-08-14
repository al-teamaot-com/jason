# Project Jason — Current Resume Point

**Updated:** 2026-08-14  
**Status:** Teams -> OpenClaw -> Jason governed interaction is operationally proven with processing acknowledgement, exact authenticated Teams-message idempotency, governed Datto RMM reads, provider-derived evidence, and deterministic canonical-fact qualifier resolution. The latest live-proven implementation checkpoint is durable in GitHub at `2e5db00db970a5cec4e153e54abbd3600819c313` (`Resolve qualified canonical endpoint facts`).
**Canonical purpose:** Human-readable resume point for current work. Production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

A future session resuming Project Jason should read, in order:

1. `docs/index.md`
2. `docs/control/JASON-FUNDAMENTALS.md`
3. this file
4. `docs/control/EXTENSION-CONSTRUCTION-MAP.md`
5. `docs/control/DOCUMENTATION-REGISTER.md`
6. `docs/control/HOW-TO-DOCUMENT-JASON.md`
7. `docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md` for natural-language resource inquiries
8. `docs/engineering/capabilities/Provider-Adaptation-and-Resource-Outcome-Contract.md` for collection/provider adaptation
9. `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md` before rebuilding/redeploying `jason-runtime`
10. `docs/decisions/ADR-007-Teams-Proactive-Messaging.md` before changing Teams/OpenClaw messaging or inbound idempotency behavior
11. `docs/sessions/Teams-Exact-Message-Idempotency-Proof-2026-08-14.md` for the latest live duplicate-protection proof
12. current GitHub state and System Registry/host evidence before asserting live production state

Conversation memory is context only. It is not authority and must not be used to reconstruct fundamentals that already have durable owners.

## Last durable success

The 2026-08-14 canonical-fact qualifier work closed the semantic-collapse defect for qualifier-rich endpoint facts.

The motivating production request was:

`What IP is AOT-50282 using internally?`

Jason already had governed `LAN IP address` and `WAN IP address` canonical facts and provider evidence. The defect was interpretation: generic language reasoning could reduce qualifier-rich wording to `ip address`, erasing the LAN/WAN distinction before capability planning.

Two bounded Qwen experiments were evaluated and rejected as the production solution:

- one incorrectly classified `internet-facing IP` as LAN;
- another handled qualified cases correctly but guessed LAN for the ambiguous `What IP does AOT-50282 have?`.

Jason therefore does not use a model to choose this canonical-fact contrast.

The durable implementation provides deterministic tri-state qualifier analysis:

- `not_applicable` — the competing-fact contrast is not activated;
- `resolved` — a shared semantic anchor exists and exactly one candidate has discriminating language;
- `ambiguous` — the shared anchor exists but no unique candidate can be established, including contradictory qualifiers.

For LAN/WAN addressing:

- internal/private/local language resolves to `LAN IP address`;
- public/external/internet-facing language resolves to `WAN IP address`;
- bare IP wording is ambiguous;
- contradictory internal/public wording is ambiguous.

Qualifier analysis executes before ordinary explicit-alias matching. This prevents a phrase such as `internal public IP` from being captured incorrectly by the longer alias `public IP`.

Ambiguity raises `ConversationIntentUnresolvedError` before generic resource-language reasoning, action reasoning, capability planning, or orchestration.

Live signed production ingress proved:

- internal IP -> LAN;
- internet-facing IP -> WAN;
- bare IP -> HTTP 400 / `conversation_unresolved`;
- qualified requests completed with authenticated and completed audit events;
- the ambiguous request produced authenticated and rejected audit events without a completion event;
- runtime source parity and health passed;
- provider configuration was unchanged;
- no provider write occurred;
- OpenClaw was not restarted.

Durable implementation commit:

`2e5db00db970a5cec4e153e54abbd3600819c313`

Durable proof:

`docs/sessions/Teams-Canonical-Fact-Qualifier-Proof-2026-08-14.md`

## Current workstream

Canonical-fact qualifier resolution is complete, live-proven, and durable.

The next conversational workstream is **governed ambiguity clarification**.

Jason now safely refuses to guess when a request such as:

`What IP does AOT-50282 have?`

does not distinguish LAN from WAN.

The current result is the generic governed `conversation_unresolved` rejection.

The next improvement should preserve that fail-closed behavior while returning a bounded clarification such as asking whether the human means the LAN/private address or the WAN/public address.

The clarification path must not execute a provider request, enter Central Orchestrator execution, or permit a model to guess before the human resolves the ambiguity.

## Unresolved controls / risks

1. **Ambiguity clarification UX:** deterministic canonical-fact ambiguity now fails closed correctly, but the current `conversation_unresolved` response is generic. A future bounded clarification path should ask the human to disambiguate without starting orchestration or allowing a model to guess.
2. **Current runtime concurrency topology:** the production HTTP server is intentionally single-worker. In-flight exact-message suppression is concurrency-proven at the ingress/replay-store layer by deterministic test. Future multi-worker/replica scale-out must preserve an atomic shared idempotency state layer before concurrency topology changes.
3. **Consequential-action idempotency:** exact inbound Teams-message idempotency prevents one transport activity from initiating duplicate governed work, but consequential actions may require capability/action-level idempotency keys and preconditions for safe retry.
4. **System Registry Datto read-surface gap:** prior governance review found active Datto read operations that are not yet fully represented/verified as production capabilities in the System Registry. Do not silently hand-edit production registry state. Close this through the governed System Registry mutation/approval path when available.
5. **OpenClaw plugin-registry metadata warning:** OpenClaw has reported stale persisted plugin-registry metadata while successfully deriving/loading the current registry. This remains a separate controlled-maintenance issue.
6. **Pre-existing approval test debt:** known approval continuation/recovery test helpers remain unrelated to the Teams idempotency/resource-routing work. Do not attribute those failures to this work without new evidence.

## Production/runtime boundary

The canonical-fact qualifier change modified the existing provider-neutral conversational interpretation/runtime only. It did not add a component, provider, capability, permission, governance gate, credential, connector operation, or OpenClaw bridge behavior.

At live proof time:

- container: `jason-runtime`;
- deployed image: `sha256:efb0ea07fb255a77e338319a09187bc69b1b72ee84fd4682a35bf508600625f8`;
- runtime health: healthy;
- source parity: passed for ingress, replay-store runtime, and HTTP-layer implementation;
- hardening: user `1000:1000`, read-only root filesystem, non-privileged, all capabilities dropped, `no-new-privileges:true`;
- OpenClaw restart: not required; and
- provider configuration change: none.

These are point-in-time proof facts, not perpetual topology authority. Re-derive live state before future production mutation.

No System Registry mutation was required for this work because no new production entity or capability was introduced. This does not resolve any separately identified pre-existing registry coverage gap.

## Continuity rules now in force

Natural-language resource inquiry handling remains a reusable governed platform pattern, not a family of workflow-specific scripts. Future work must preserve:

- provider-neutral resource interpretation;
- selector/fact separation;
- canonical fact vocabulary derived from governed capability metadata;
- minimal requested facts;
- Central Orchestrator authority and routing;
- bounded structural evidence indexes;
- bounded AI selection only among Jason-supplied choices where explicitly allowed;
- deterministic provider-derived fact values and pointer dereference;
- source attribution;
- no direct agent-to-agent or agent-to-provider bypass; and
- failure closed when evidence or semantic support is insufficient;
- deterministic tri-state qualifier analysis before generic semantic fallback when governed canonical facts share an ambiguous human anchor;
- ambiguous or conflicting canonical-fact qualifiers stop before generic resource-language or action-model reasoning; and
- models must not be used merely to force a choice between equally eligible governed canonical facts.

Inbound transport idempotency now additionally requires:

- exact authenticated transport activities to be keyed from stable authenticated transport identity rather than request text;
- duplicate claims to be durable and centrally enforced before governed execution;
- duplicate suppression to be auditable;
- request-ID replay protection to remain independent and preserved; and
- same-text messages with distinct authenticated message IDs to remain distinct requests unless a deeper governed capability explicitly defines other idempotency semantics.

Teams/OpenClaw remain interface/transport providers only. Transport feedback and duplicate suppression must never become authority, policy, provider, or reasoning bypasses.

## Next safe actions

1. Inspect the current `ConversationIntentUnresolvedError` through governed ingress and OpenClaw/Teams response path.
2. Define a structured provider-neutral clarification result carrying only bounded competing canonical facts and safe user-facing clarification text.
3. Ensure ambiguous requests do not invoke the Central Orchestrator, provider, connector, or action model before disambiguation.
4. Add deterministic tests for bare-IP and conflicting-qualifier clarification while preserving qualified LAN/WAN routing.
5. Prove clarification through signed authenticated ingress and Teams/OpenClaw presentation.
6. Close documentation for the clarification pattern.
7. Separately close the System Registry Datto read-surface gap and future consequential-action idempotency requirements through their governed workstreams.

## Success condition

A future competent human or AI can determine from durable repository records that exact Teams-message idempotency and deterministic canonical-fact qualifier resolution are operational; that internal/private/local IP language resolves to LAN while public/external/internet-facing language resolves to WAN; that bare or conflicting qualifiers fail closed before model reasoning or orchestration; that operational values remain provider-derived; and that the next safe conversational target is governed ambiguity clarification.
