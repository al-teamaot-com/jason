# Project Jason — Current Resume Point

**Updated:** 2026-08-14  
**Status:** Teams → OpenClaw → Jason governed interaction is operationally proven with visible processing acknowledgement, governed Datto RMM read execution, provider-derived evidence, and source-attributed responses. The latest live-proven implementation checkpoint is durable in GitHub at `e98e4bd` (`Add Teams processing acknowledgement for governed turns`).  
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
10. `docs/decisions/ADR-007-Teams-Proactive-Messaging.md` before changing Teams/OpenClaw messaging behavior
11. current GitHub state and System Registry/host evidence before asserting live production state

Conversation memory is context only. It is not authority and must not be used to reconstruct fundamentals that already have durable owners.

## Last durable success

The 2026-08-14 Teams processing-feedback work established and live-proved a reusable best-effort acknowledgement for governed Teams turns.

The problem was not Teams configuration. OpenClaw native Teams typing is owned by its normal reply lifecycle, while Jason-bound conversations use the `jason-bridge` compatibility pre-agent path and return a handled governed response before the normal model/reply lifecycle begins. Enabling native typing therefore did not produce a visible indicator for Jason-bound turns.

The correction stayed inside the existing OpenClaw/Jason transport boundary. `infrastructure/openclaw-jason-bridge/index.mjs` now uses OpenClaw's supported channel outbound adapter to send the static receipt:

`Received - working on that now...`

The acknowledgement is emitted after required inbound transport identity/conversation fields are validated and before the synchronous governed Jason runtime call begins. It is transport feedback only: it does not imply authorization success, does not expose reasoning or chain-of-thought, does not contain provider data, and is not authoritative for task outcome. If acknowledgement delivery fails or is unavailable, the governed Jason request continues normally and the final governed response/error remains authoritative.

Validation and proof:

- Node syntax validation passed using the OpenClaw container runtime.
- OpenClaw bridge tests passed: `10 passed`.
- Live repository/host/container bridge source parity passed.
- `jason-bridge` and `msteams` both loaded successfully.
- Live Teams proof showed the acknowledgement immediately followed by the normal governed Jason response.
- Durable implementation commit: `e98e4bd19e3881025f5167c5be57529961e73ebe`.
- Proof record: `docs/sessions/Teams-Processing-Feedback-Proof-2026-08-14.md`.

No Jason runtime service, provider capability, authorization rule, model, or System Registry entity was added by this change.

## Current workstream

Teams processing feedback is complete and live-proven.

The next implementation workstream is **in-flight duplicate-request protection** for governed Teams turns. The design must preserve Jason's central-governance boundary:

- exact duplicate transport activities should be idempotent using stable authenticated transport identity such as Teams message/activity identifiers;
- duplicate suppression belongs centrally after authenticated ingress rather than being trusted to volatile bridge memory;
- a repeated new Teams message with the same text is not automatically the same request and must not be suppressed merely by text similarity;
- consequential actions will require governed idempotency/precondition semantics rather than heuristic text deduplication;
- duplicate handling must be auditable and must not bypass the Central Orchestrator.

After duplicate protection, return to the bounded semantic fact-resolution defect demonstrated by:

`What IP is AOT-50282 using internally?`

The current production path preserves the endpoint selector but can reduce `using internally` to generic `ip address`, producing an evidence-unavailable response even though governed LAN IP evidence exists. Repair must occur in the reusable canonical-fact interpretation layer, not through a question-specific Datto mapping or script.

## Unresolved controls / risks

1. **Semantic qualifier resolution:** internal/private/local-network language still needs bounded canonical resolution to `LAN IP address`; public/external/internet-facing language should similarly resolve to `WAN IP address`; bare ambiguous IP wording should not silently choose one.
2. **Rollback verification:** the Teams acknowledgement deployment exposed a weakness in an ad hoc rollback harness that verified container restart but did not verify restored file content afterward. Future rollback procedures must verify restored hashes/state, not merely process restart. Known baseline backups from the live test retained the original bridge hash and were not committed to Git.
3. **System Registry Datto read-surface gap:** prior governance review found active Datto read operations that are not yet fully represented/verified as production capabilities in the System Registry. Do not silently hand-edit production registry state. Close this through the governed System Registry mutation/approval path when that path is available.
4. **OpenClaw plugin-registry metadata warning:** OpenClaw has reported stale persisted plugin-registry metadata while successfully deriving/loading the current registry. This is separate from Teams processing feedback and should be handled as its own controlled maintenance item.
5. **Pre-existing test debt:** approval continuation/recovery tests have known missing test helpers unrelated to the Teams acknowledgement/resource-routing work. Do not attribute those failures to the current changes without new evidence.

## Production/runtime boundary

The Teams acknowledgement change modified the existing OpenClaw Jason Bridge only. It did not rebuild or change `jason-runtime`.

During live validation the authoritative bridge path was:

`/opt/jason/services/openclaw/data/config/extensions/jason-bridge/index.mjs`

inside the OpenClaw container it was visible at:

`/home/node/.openclaw/extensions/jason-bridge/index.mjs`

Do not treat these narrative paths as a substitute for fresh deployment evidence. Re-derive live mounts/source parity before future production mutation.

For Jason runtime rebuild/deployment, continue to use `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md` and derive Compose inputs from current live state rather than assumption.

## Continuity rules now in force

Natural-language resource inquiry handling remains a reusable governed platform pattern, not a family of workflow-specific scripts. Future work must preserve:

- provider-neutral resource interpretation;
- selector/fact separation;
- canonical fact vocabulary derived from governed capability metadata;
- minimal requested facts;
- Central Orchestrator authority and routing;
- bounded structural evidence indexes;
- AI selection only among Jason-supplied bounded evidence/canonical choices;
- deterministic provider-derived fact values and pointer dereference;
- source attribution;
- no direct agent-to-agent or agent-to-provider bypass; and
- failure closed when evidence or semantic support is insufficient.

Teams/OpenClaw remain interface/transport providers only. Transport feedback may improve user experience, but it must never become an authority, policy, provider, or reasoning bypass.

If a representable question fails, repair the reusable layer that failed rather than creating a bespoke query script.

## Next safe actions

1. Validate the documentation control plane after the 2026-08-14 closeout changes.
2. Confirm the documentation commits are durable on `feature/jason-runtime-service` and synchronize the Jason host before new local work.
3. Inspect the current authenticated ingress/replay-store implementation and existing tests before designing duplicate protection.
4. Implement exact transport-message idempotency centrally, with audit evidence and deterministic tests, before considering bounded in-flight same-request handling.
5. Live-test duplicate protection through Teams without weakening the existing acknowledgement or governed runtime path.
6. Update documentation again before closing the duplicate-protection workstream.
7. Then implement the bounded canonical-fact semantic resolver for qualifier-rich human language.
8. Separately plan governed closure of the System Registry Datto read-surface gap and rollback-verification hardening.

## Success condition

A future competent human or AI can resume from the repository and determine, without this chat, that Teams processing feedback is operational, why OpenClaw native typing did not cover the Jason compatibility path, how the acknowledgement is bounded and non-authoritative, what was live-proven and committed, what risks remain, and that the next safe implementation target is centrally governed duplicate protection followed by canonical semantic qualifier resolution.
