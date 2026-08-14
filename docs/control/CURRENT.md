# Project Jason — Current Resume Point

**Updated:** 2026-08-14  
**Status:** Teams -> OpenClaw -> Jason governed interaction is operationally proven with processing acknowledgement, exact authenticated Teams-message idempotency, governed Datto RMM reads, provider-derived evidence, deterministic canonical-fact qualifier resolution, and stateless governed ambiguity clarification. The latest live-proven implementation checkpoint is durable in GitHub at `9d125d8c5144ead948e2c90d9b79f7796bdb3c1c` (`Add governed ambiguity clarification`).
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

The 2026-08-14 governed ambiguity-clarification work converted deterministic canonical-fact ambiguity from a generic failure into a bounded non-execution conversational result.

The motivating production request was:

`What IP does AOT-50282 have?`

The qualifier layer establishes that this request is ambiguous between:

- `LAN IP address`;
- `WAN IP address`.

Jason now returns:

- HTTP `200`;
- `status=clarification_required`;
- `error_code=canonical_fact_ambiguous`;
- candidates exactly `LAN IP address` and `WAN IP address`;
- bounded clarification text; and
- `requires_complete_request=true`.

Clarification occurs before orchestration-request construction, Central Orchestrator execution, provider access, or model guessing.

The signed live proof produced only:

- `openclaw.teams_conversation_authenticated`;
- `openclaw.teams_conversation_clarification_required`.

It produced no completion, rejection, or failure event, no orchestration result, no provider result, and no return-path handoff.

The active OpenClaw bridge rendered the exact clarification text supplied by Jason.

The implementation is intentionally stateless. A short reply such as `LAN` does not yet inherit the previous endpoint selector or become execution authority.

Durable implementation commit:

`9d125d8c5144ead948e2c90d9b79f7796bdb3c1c`

Durable proof target:

`docs/sessions/Teams-Governed-Ambiguity-Clarification-Proof-2026-08-14.md`

## Current workstream

Stateless governed ambiguity clarification is complete, live-proven, and durable.

The next conversational workstream is **governed clarification continuation**.

Today, after Jason asks whether the human means LAN or WAN, a bare reply such as:

`LAN`

does not inherit the previous request context.

That is intentionally safer than hidden conversational memory.

Any future continuation mechanism must be explicit Jason-owned state rather than model or OpenClaw memory. It must be scoped to authenticated tenant, principal, and conversation; tied to the original ambiguity; short-lived; auditable; idempotent; and unable to change the original authority or resource selector.

## Unresolved controls / risks

1. **Clarification continuation state:** stateless clarification is operational, but short replies such as `LAN` do not yet continue the original request. Any continuation state must be bounded, authenticated, conversation-scoped, expiring, auditable, and non-authoritative by itself.
2. **Current runtime concurrency topology:** the production HTTP server is intentionally single-worker. Future multi-worker/replica scale-out must preserve an atomic shared idempotency state layer.
3. **Consequential-action idempotency:** exact inbound Teams-message idempotency prevents one transport activity from initiating duplicate governed work, but consequential actions may require capability/action-level idempotency keys and preconditions.
4. **System Registry Datto read-surface gap:** active Datto read operations are not yet fully represented/verified as production capabilities in the System Registry. Do not silently hand-edit production registry state.
5. **OpenClaw plugin-registry metadata warning:** stale persisted plugin-registry metadata remains a separate controlled-maintenance issue.
6. **Pre-existing approval test debt:** known approval continuation/recovery test helpers remain unrelated to this work.

## Production/runtime boundary

The ambiguity-clarification work changed existing provider-neutral conversational interpretation, governed ingress/HTTP result classification, and OpenClaw presentation behavior.

It did not add a new provider, capability, permission, credential, governance gate, external integration, or provider write surface.

At live proof time:

- runtime container: `jason-runtime`;
- runtime image: `sha256:e4897ecdb45e80cac2403b00279da1205f995c2e442b578985940555e1b41724`;
- OpenClaw container: `openclaw-openclaw-gateway-1`;
- OpenClaw image: `sha256:6fdd46f654a1c4edf3ddc7324ebb5918738a35b3e36809c4a47292b399aa7824`;
- active bridge host path: `/opt/jason/services/openclaw/data/config/extensions/jason-bridge/bridge-core.mjs`;
- active bridge container path: `/home/node/.openclaw/extensions/jason-bridge/bridge-core.mjs`;
- runtime health: healthy;
- OpenClaw health: healthy;
- runtime source parity: passed;
- active bridge repository/host/container parity: passed;
- runtime rollback tag: `jason-runtime:pre-clarification-20260814T161345Z`; and
- provider configuration/write changes: none.

These are point-in-time proof facts, not perpetual topology authority. Re-derive live state before future production mutation.

No System Registry mutation was required because this work introduced no new production entity or capability.

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

1. Inspect existing Jason-owned conversation and replay-state mechanisms before designing clarification continuation.
2. Define the smallest bounded continuation record needed to preserve the original authenticated selector and competing canonical facts.
3. Scope continuation state to authenticated tenant, principal, and conversation with explicit expiration and audit evidence.
4. Permit continuation to select only one candidate from the original ambiguity.
5. Prevent continuation from changing organization, resource selector, provider authority, or capability authority.
6. Preserve exact-message idempotency and fail closed on stale, conflicting, cross-conversation, or cross-principal replies.
7. Prove no provider/orchestration execution occurs until a valid human clarification is supplied.
8. Live-prove and document the continuation path.

## Success condition

A future competent human or AI can determine from durable repository records that exact Teams-message idempotency, deterministic canonical-fact qualification, and stateless governed ambiguity clarification are operational; that ambiguous canonical facts produce bounded human clarification rather than a generic failure; that clarification does not enter request construction, orchestration, provider execution, or model guessing; that OpenClaw only presents the Jason-supplied result; and that the next safe conversational target is governed clarification continuation rather than hidden conversational memory.
