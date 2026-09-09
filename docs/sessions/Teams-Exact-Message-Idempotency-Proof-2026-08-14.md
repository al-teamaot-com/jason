# Teams Exact-Message Idempotency Proof — 2026-08-14

**Classification:** Evidence / durable session proof  
**Status:** Live-proven and durable implementation  
**Implementation commit:** `aacc1cb7527e640331aa43cbc316c6c22c56ca77` — `Add exact Teams message idempotency`  
**Workstream:** Governed Microsoft Teams/OpenClaw inbound duplicate protection

## Purpose

This record preserves the implementation, validation, deployment, and live proof for exact authenticated Teams-message idempotency at Jason's governed OpenClaw ingress boundary.

The goal was to prevent the same authenticated Microsoft Teams activity from creating duplicate governed work when OpenClaw or the transport retries the activity with a new Jason transport `request_id`.

This work does **not** deduplicate messages merely because their text is identical. A genuinely new Teams message remains a new request.

## Architectural authority

The change preserves the existing Project Jason authority model:

- Microsoft Teams and OpenClaw remain interface/transport providers only.
- The Central Orchestrator remains the sole governed execution/coordinating authority.
- Agents and connectors do not communicate directly.
- Duplicate suppression occurs after authenticated/signed transport validation and before the governed conversation flow reaches orchestration.
- Existing request-ID replay protection remains in force.
- No provider write capability or side effect was introduced by this work.

## Problem demonstrated

Before this change, the OpenClaw bridge generated a new random `request_id` whenever it built a signed Jason conversation envelope. Jason's ingress replay store claimed only that `request_id`.

Therefore, two envelopes representing the same Teams activity could have:

- the same authenticated Microsoft tenant;
- the same authenticated Microsoft user object ID;
- the same Teams conversation ID;
- the same Teams message/activity ID; but
- different Jason `request_id`, correlation ID, and nonce values.

Both envelopes could pass request-ID replay protection and reach governed execution.

## Implemented control

`implementation/connectors/openclaw/src/jason_openclaw/conversation_ingress.py` now creates a second durable claim after request freshness and request-ID replay validation.

The canonical exact-message identity is:

1. Microsoft tenant ID;
2. Microsoft object ID;
3. Teams conversation ID; and
4. Teams message ID.

The four values are joined using a null separator, SHA-256 hashed, and stored using the namespace:

`teams-message-v1:<sha256>`

The raw compound identity is therefore not used as the replay-store primary key.

The existing `SQLiteReplayStore` is reused for the durable atomic claim. No second database or bridge-local in-memory lock was introduced.

If the exact-message claim already exists, ingress records:

`openclaw.teams_conversation_duplicate_suppressed`

and returns:

```json
{
  "status": "duplicate",
  "error_code": "duplicate_message"
}
```

The duplicate response is an HTTP `200` idempotent transport outcome. The duplicate does not enter `TeamsConversationFlow.handle()` and therefore does not start a second governed orchestration execution.

## Deliberate boundary

This control is exact-message idempotency, not semantic deduplication.

A second Teams activity with a different `message_id` is allowed to execute even when its text is identical to a previous request. Jason does not infer that repeated words mean repeated intent.

Consequential capabilities may require deeper governed action-level idempotency keys, preconditions, or provider-specific safe-retry semantics. This ingress control does not replace those protections.

## Deterministic validation

The implementation added regression coverage for:

- the same authenticated Teams message with a new `request_id` being suppressed;
- the duplicate being suppressed while the first ingress execution is still in progress;
- the first execution continuing normally;
- the second execution never starting the conversation flow;
- a new Teams message with identical text remaining allowed; and
- HTTP duplicate classification returning `200` with `status=duplicate` and `error_code=duplicate_message`.

The focused idempotency tests passed.

The full OpenClaw connector test suite passed.

The full runtime-service test suite passed.

Before durable commit, the complete target suites were re-run together and passed.

### Host test environment prerequisite rediscovered

Host-side runtime tests must expose the same source roots the production runtime image exposes:

- `implementation`
- `implementation/cap-007/src`
- `implementation/connectors/openclaw/src`
- `implementation/runtime_service/src`

Omitting the OpenClaw/runtime roots caused initial collection failures for `jason_openclaw` and `jason_runtime`.

Omitting `implementation/cap-007/src` later caused collection failures for `jason_cap_007`.

These were test-environment failures, not implementation failures. The production Dockerfile already carries all four roots in `PYTHONPATH`.

## Governed runtime deployment

The production runtime was rebuilt using the existing `jason-runtime` Compose service after deriving live Compose topology and required interpolation values from the running container.

### Secret bind verification lesson

Several provider-secret source paths are intentionally protected from direct metadata access by the ordinary operator account. A direct host `test -f` therefore failed even though the files were valid and already mounted by Docker.

The safe verification method was changed to a Docker daemon bind probe:

- bind the existing source path read-only into an ephemeral container;
- test only whether the mounted target is a regular file;
- never print or read the secret value.

All six required OpenBao/AppRole bind sources passed this probe.

This method verifies presence through the same Docker privilege boundary that performs the production bind without weakening filesystem permissions.

### Build and deployment evidence

Previous production image:

`sha256:88aeadb5e3838629b0a25e0b646980923cfa080bca715033cceeef8f9f6fb029`

Verified rollback tag created before deployment:

`jason-runtime:pre-message-idempotency-20260814T151057Z`

New deployed production image:

`sha256:060f0b5fe98611fc9bb634bc2d11d87d239b685fb441a4b6fae35103298e8ac6`

The runtime became healthy after recreation.

The deployed image ID exactly matched the newly built image.

Host/container source parity passed for the ingress, replay-store runtime, and HTTP-layer implementation files.

The health endpoint reported the expected Central Orchestrator authority.

Runtime hardening remained:

- user `1000:1000`;
- read-only root filesystem;
- not privileged;
- all Linux capabilities dropped; and
- `no-new-privileges:true`.

OpenClaw was not restarted and provider configuration was not changed.

## Signing-key selection proof

The live signed-ingress proof discovered two private PEM candidates in the OpenClaw Jason ingress key directory.

No key was guessed, deleted, or replaced.

The public key derived from each private candidate was SHA-256 fingerprinted and compared to the active trusted public-key fingerprint registered for `openclaw-gateway-2`.

Exactly one candidate matched: the configured `openclaw-jason-ed25519-v2.pem` key. The older PEM did not match.

Private-key contents were never printed.

This establishes the construction rule that proof tooling must resolve a signing key from trusted public metadata rather than assume a directory contains only one private-key candidate.

## Live signed duplicate-ingress proof

A live proof was executed against the healthy production `jason-runtime` endpoint using the active OpenClaw signing key and recent authenticated Teams transport context already present in Jason's security audit.

The safe governed request was:

`What is the LAN IP address of AOT-50282?`

Two independently signed envelopes were sent with:

- different request IDs;
- different correlation IDs;
- different nonces; and
- the same authenticated Teams message ID.

Proof message ID:

`jason-live-idempotency-20260814T151957Z-1000289`

### First request

The first request returned:

- HTTP `200`;
- `status=completed`;
- `orchestration_status=succeeded`; and
- a non-empty governed reply.

Security audit events for the first request included:

- `openclaw.teams_conversation_authenticated`; and
- `openclaw.teams_conversation_completed`.

### Second request

The second request returned:

- HTTP `200`;
- `status=duplicate`; and
- `error_code=duplicate_message`.

Its security audit contained exactly the duplicate-suppression event:

`openclaw.teams_conversation_duplicate_suppressed`

No completion event existed for the duplicate request.

### Persistent replay-store evidence

The persistent replay database contained:

- two request-ID claims, one for each signed envelope; and
- exactly one exact-message claim for the shared Teams message identity.

This proves the second envelope passed ordinary request-ID uniqueness but was stopped by the new durable exact-message claim.

The runtime remained healthy after the proof.

No provider write occurred.

## In-flight concurrency statement

The ingress implementation has a deterministic concurrency regression test in which the first flow execution is deliberately blocked while a second envelope with the same authenticated Teams message identity is submitted. The second envelope is suppressed before entering the flow while the first is still active.

The current production HTTP server is intentionally single-worker, so the live HTTP proof itself is serialized by the server. The concurrency property is therefore proven at the ingress/replay-store layer by the regression test, while production validates the signed transport, persistent claim, audit, HTTP classification, and governed execution behavior.

Future scale-out must preserve an atomic shared idempotency state layer before introducing multiple runtime workers or replicas.

## Durable implementation checkpoint

Implementation commit:

`aacc1cb7527e640331aa43cbc316c6c22c56ca77`

Commit message:

`Add exact Teams message idempotency`

Changed implementation files:

- `implementation/connectors/openclaw/src/jason_openclaw/conversation_ingress.py`
- `implementation/connectors/openclaw/src/jason_openclaw/runtime.py`
- `implementation/connectors/openclaw/tests/test_conversation_ingress.py`
- `implementation/runtime_service/src/jason_runtime/http.py`
- `implementation/runtime_service/tests/test_http.py`

## Documentation-impact determination

**Documentation impact: material.**

This work introduced a reusable ingress/runtime idempotency pattern and exposed deployment/validation prerequisites that future operators should not rediscover.

Required closeout updates:

- `docs/control/CURRENT.md` — advance the durable resume point and next workstream;
- `docs/control/EXTENSION-CONSTRUCTION-MAP.md` — add exact authenticated transport-message idempotency to the ingress construction pattern;
- `docs/decisions/ADR-007-Teams-Proactive-Messaging.md` — record the accepted exact-message idempotency decision and evidence;
- `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md` — preserve Docker bind-probe, host test source-root, rollback, and deployed-source verification lessons; and
- this proof record.

### System Registry impact

**No System Registry mutation is required for this work.**

The change did not add a new production component, provider, capability, credential, identity binding, governance gate, or deployment service. It changed behavior inside the already existing governed OpenClaw ingress/runtime component.

This determination does not close or alter any separately identified pre-existing System Registry coverage gaps.

### Documentation navigation impact

No new documentation category was introduced. `docs/sessions/` is already the governed class for durable proof records. This proof is linked from `CURRENT.md`, ADR-007, and the Extension Construction Map, so no additional top-level documentation index entry is required.

## Next safe work

Exact Teams-message idempotency is complete, deployed, live-proven, auditable, documented, and durable.

The next primary implementation workstream is the bounded canonical-fact semantic resolver for qualifier-rich natural language, beginning with the known case:

`What IP is AOT-50282 using internally?`

That work must resolve only among governed canonical facts/capabilities and must not create question-specific Datto scripts or mappings.
