# Project Jason — Current Resume Point

**Updated:** 2026-08-14  
**Status:** Teams → OpenClaw → Jason governed interaction is operationally proven with visible processing acknowledgement, governed Datto RMM reads, provider-derived evidence, source-attributed responses, and exact authenticated Teams-message idempotency. The latest live-proven implementation checkpoint is durable in GitHub at `aacc1cb7527e640331aa43cbc316c6c22c56ca77` (`Add exact Teams message idempotency`).  
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

The 2026-08-14 exact Teams-message idempotency work closed the known duplicate-execution hole at the governed OpenClaw ingress boundary.

Before this change, OpenClaw could construct a new signed Jason envelope for the same Teams activity using a fresh random `request_id`. Jason's existing replay protection claimed only `request_id`, so the same authenticated Teams message could theoretically reach governed execution more than once.

The durable correction is implemented at authenticated Jason ingress rather than in volatile OpenClaw bridge memory.

After freshness and request-ID replay validation, Jason derives an exact-message identity from:

- Microsoft tenant ID;
- Microsoft object ID;
- Teams conversation ID; and
- Teams message ID.

That compound identity is SHA-256 hashed and claimed in the existing persistent `SQLiteReplayStore` under the namespace `teams-message-v1:`.

If the claim already exists, Jason records `openclaw.teams_conversation_duplicate_suppressed` and returns HTTP `200` with `status=duplicate` and `error_code=duplicate_message`. The duplicate does not enter the Teams conversation flow or start a second Central Orchestrator execution.

The control intentionally does not suppress a genuinely new Teams activity merely because its text matches an earlier request.

Validation and proof:

- focused exact-message idempotency tests passed;
- in-flight concurrency regression test passed at the ingress/replay-store layer;
- full OpenClaw connector tests passed;
- full runtime-service tests passed;
- complete target suites passed again immediately before commit;
- production `jason-runtime` was rebuilt and deployed successfully;
- deployed image/source parity and runtime hardening passed;
- a live signed ingress proof executed one governed Datto read and then submitted a second independently signed envelope with a different request ID/nonce/correlation ID but the same Teams message ID;
- the first request completed with successful orchestration and a governed reply;
- the second returned `duplicate_message` without a completion audit event;
- persistent replay evidence showed two request-ID claims but exactly one message-ID claim; and
- the runtime remained healthy.

Durable implementation commit:

`aacc1cb7527e640331aa43cbc316c6c22c56ca77`

Durable proof record:

`docs/sessions/Teams-Exact-Message-Idempotency-Proof-2026-08-14.md`

The previously completed Teams processing acknowledgement remains operational and is documented at `docs/sessions/Teams-Processing-Feedback-Proof-2026-08-14.md`.

## Current workstream

Exact Teams-message idempotency is complete, live-proven, and durable.

The next primary implementation workstream is the **bounded canonical-fact semantic resolver for qualifier-rich natural language**.

The known production example is:

`What IP is AOT-50282 using internally?`

The current path can preserve the endpoint selector while reducing `using internally` to generic `ip address`, producing evidence unavailable even though governed LAN IP evidence exists.

The next change must repair the reusable semantic/canonical-fact layer rather than add a question-specific Datto script or mapping.

The intended bounded behavior is:

- deterministic endpoint/resource selector resolution remains separate from fact interpretation;
- the eligible fact vocabulary comes only from governed capability/resource contracts;
- a bounded local reasoning step may choose only among the supplied allowlisted canonical facts;
- internal/private/local-network language may resolve to the canonical LAN IP fact;
- public/external/internet-facing language may resolve to the canonical WAN IP fact;
- an ambiguous bare `What IP?` request should not silently choose LAN or WAN; and
- operational fact values remain deterministic and provider-derived.

## Unresolved controls / risks

1. **Semantic qualifier resolution:** qualifier-rich human language still needs bounded canonical-fact resolution without allowing a model to invent provider fields, providers, capabilities, facts, or operational values.
2. **Current runtime concurrency topology:** the production HTTP server is intentionally single-worker. In-flight exact-message suppression is concurrency-proven at the ingress/replay-store layer by deterministic test. Future multi-worker/replica scale-out must preserve an atomic shared idempotency state layer before concurrency topology changes.
3. **Consequential-action idempotency:** exact inbound Teams-message idempotency prevents one transport activity from initiating duplicate governed work, but consequential actions may require capability/action-level idempotency keys and preconditions for safe retry.
4. **System Registry Datto read-surface gap:** prior governance review found active Datto read operations that are not yet fully represented/verified as production capabilities in the System Registry. Do not silently hand-edit production registry state. Close this through the governed System Registry mutation/approval path when available.
5. **OpenClaw plugin-registry metadata warning:** OpenClaw has reported stale persisted plugin-registry metadata while successfully deriving/loading the current registry. This remains a separate controlled-maintenance issue.
6. **Pre-existing approval test debt:** known approval continuation/recovery test helpers remain unrelated to the Teams idempotency/resource-routing work. Do not attribute those failures to this work without new evidence.

## Production/runtime boundary

The exact-message idempotency change modified the existing Jason/OpenClaw governed ingress/runtime only. It did not add a component, provider, capability, permission, governance gate, credential, or OpenClaw bridge behavior.

At live proof time:

- container: `jason-runtime`;
- deployed image: `sha256:060f0b5fe98611fc9bb634bc2d11d87d239b685fb441a4b6fae35103298e8ac6`;
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
- failure closed when evidence or semantic support is insufficient.

Inbound transport idempotency now additionally requires:

- exact authenticated transport activities to be keyed from stable authenticated transport identity rather than request text;
- duplicate claims to be durable and centrally enforced before governed execution;
- duplicate suppression to be auditable;
- request-ID replay protection to remain independent and preserved; and
- same-text messages with distinct authenticated message IDs to remain distinct requests unless a deeper governed capability explicitly defines other idempotency semantics.

Teams/OpenClaw remain interface/transport providers only. Transport feedback and duplicate suppression must never become authority, policy, provider, or reasoning bypasses.

## Next safe actions

1. Validate this documentation closeout using `tools/validate_documentation_control.py` and `git diff --check` after synchronizing the documentation commit to the Jason host.
2. Confirm the documentation commit is durable on `feature/jason-runtime-service` and that the host checkout is clean.
3. Inspect the current deterministic resource interpreter, canonical fact vocabulary, capability contracts, semantic planner boundaries, and existing tests before implementing qualifier resolution.
4. Add a bounded canonical-fact resolver that receives only governed eligible canonical facts and cannot invent provider-specific fields or operational values.
5. Add positive tests for internal/private/local-network → LAN and public/external/internet-facing → WAN language, plus an ambiguity test for bare IP wording.
6. Re-run the broader grounded endpoint routing proofs to ensure existing deterministic questions do not regress.
7. Live-test the semantic qualifier behavior through the governed Teams/OpenClaw path.
8. Close documentation before moving to the next workstream.
9. Separately plan governed closure of the System Registry Datto read-surface gap and any future consequential-action idempotency framework.

## Success condition

A future competent human or AI can resume from the repository and determine, without this chat, that Teams processing feedback and exact authenticated Teams-message idempotency are operational, why duplicate request IDs alone were insufficient, how exact-message identity is scoped and durably claimed, what was live-proven and committed, what the production concurrency boundary is, what risks remain, and that the next safe implementation target is bounded canonical-fact semantic qualifier resolution.
