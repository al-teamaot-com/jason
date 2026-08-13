# Project Jason — Current Resume Point

**Updated:** 2026-08-13
**Status:** Teams → OpenClaw → Jason → Datto RMM governed resource inquiry is operationally proven for varied human language, deterministic resource recognition, canonical collection outcomes, provider adaptation, complete managed-site enumeration, and source-attributed evidence. The latest live-proven source checkpoint is durable in GitHub at `5b2c6c6`.
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
8. `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md` before rebuilding/redeploying `jason-runtime`
9. the governing architecture/ADR/component/standard/runbook records for the workstream
10. current GitHub state and System Registry/host evidence before asserting live production state

Conversation memory is context only. It is not authority and must not be used to reconstruct fundamentals that already have durable owners.

## Last durable success

The 2026-08-12 resource inquiry work established and deployed a generic semantic/evidence correction through the production Teams → OpenClaw → Jason → Datto RMM path.

Provider truth for `AOT-50282` was established directly from Datto RMM:

`/lastLoggedInUser = AzureAD\AlDavis`

The production-shaped Jason result exposed the value at `/provider_data/lastLoggedInUser`. The bounded evidence index included that pointer first, and live Ollama evidence selection chose that exact pointer when the requested fact was `last logged in user`.

The root defect was upstream natural-language interpretation: selector/inventory vocabulary was being emitted as requested facts. Production composition now derives resource types, selector keys, and fact hints from governed provider-neutral read-only capability metadata and supplies those fact hints to the resource inquiry reasoner. Endpoint fact hints are canonicalized as discrete facts, and the reasoner is constrained to return the smallest requested fact set.

Focused automated tests passed (`20 passed`), static validation passed, the authoritative runtime deployment completed successfully, and the runtime health check passed.

Final Teams proof:

`AOT-50282 — last logged in user: AzureAD\AlDavis. Source: datto_rmm.`

Proof: `docs/sessions/Teams-Datto-Resource-Semantic-Proof-2026-08-12.md`

Reusable pattern: `docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md`

Deployment procedure: `docs/operations/Jason-Runtime-Rebuild-and-Deploy.md`

## Continuity rule now in force

Natural-language resource inquiry handling is a reusable governed platform pattern, not a family of workflow-specific scripts. Future work must preserve:

- provider-neutral resource interpretation;
- selector/fact separation;
- capability-derived language vocabulary;
- minimal requested facts;
- Central Orchestrator authority and routing;
- bounded structural evidence indexes;
- model selection only among Jason-supplied evidence pointers;
- deterministic pointer dereference and source attribution; and
- no direct agent-to-agent or agent-to-provider bypass.

If a representable question fails, repair the reusable layer that failed rather than creating a bespoke query script.

## Current workstream

The semantic resource inquiry defect for `Who last used AOT-50282?` is operationally resolved.

The next source-control task is to review and, only with explicit authorization, commit/push the runtime implementation changes that were deployed from the uncommitted working tree. At deployment time the last verified HEAD was `25bc07a` and modified files included:

- `implementation/connectors/openclaw/src/jason_openclaw/conversation_ingress.py`
- `implementation/orchestrator/ollama_reasoning.py`
- `implementation/orchestrator/resource_capability_catalog.py`
- `implementation/orchestrator/tests/test_ollama_reasoning.py`
- `implementation/runtime_service/src/jason_runtime/composition.py`
- `implementation/runtime_service/tests/test_composition.py`

Do not assume those local modifications are durable in GitHub until verified from Git.

## Production/runtime boundary

The production runtime was rebuilt and restarted successfully on 2026-08-12 using the authoritative Compose project discovered from the running container:

- Compose directory: `/home/al/projects/jason/infrastructure/jason-runtime`
- Compose file: `/home/al/projects/jason/infrastructure/jason-runtime/compose.yaml`
- Project/service: `jason-runtime`
- Image: `jason-runtime:local`

Deployment inputs were derived from the running service environment and bind mounts. Protected Microsoft Graph secret paths required privileged metadata verification because the ordinary account could not traverse the parent directory. Secret contents were not printed.

Do not guess Compose paths, deployment variables, or secret host paths in future sessions. Re-derive them from authoritative live state when needed.

## Next safe actions

1. Fetch current Git state before making any source-control claim.
2. Confirm whether the six deployed runtime modifications remain uncommitted locally.
3. If authorized, run the full relevant validation suite and commit/push those implementation changes as a coherent governed change.
4. Continue broad resource-inquiry validation with other endpoint facts/resources using the generic capability/resource path, not bespoke scripts.
5. Update construction guidance whenever a reusable pattern changes or a prerequisite has to be rediscovered.

## Success condition

A future session can reproduce why the AOT-50282 answer was wrong, locate the provider truth, understand the generic semantic/evidence correction, rebuild the runtime from the authoritative deployment topology, and distinguish operational deployment from Git durability without relying on this conversation.

<!-- BEGIN 2026-08-12 DATTO READ WORKSTREAM -->
## Last durable success — 2026-08-12 Adaptive Governed Datto Read Foundation

Production Jason now supports broad governed Datto RMM read inquiries through reusable provider-neutral capabilities.

Durable success includes:

- organization-wide AOT Datto provider-read observe authority;
- device alerts, audit, software, account alerts, and managed-site reads;
- deterministic-first resource interpretation with Ollama semantic fallback;
- structurally authoritative direct collection evidence;
- bounded human-oriented collection rendering;
- generic Provider Adaptation for contradictory provider evidence;
- complete collection aggregation when the resource inquiry requires completeness;
- `result_intent` and `completeness_requirement` as governed inquiry properties;
- production proof of adaptive Datto site recovery and complete 46-site aggregation.

Architecture:
`docs/engineering/capabilities/Provider-Adaptation-and-Resource-Outcome-Contract.md`

Session proof:
`docs/sessions/Datto-Governed-Read-Adaptation-Proof-2026-08-12.md`

Existing resource evidence pattern:
`docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md`

Runtime deployment runbook:
`docs/operations/Jason-Runtime-Rebuild-and-Deploy.md`

Current branch:
`feature/jason-runtime-service`

Next priority:

- add visible Microsoft Teams processing feedback using OpenClaw's supported native typing/processing lifecycle;
- continue generalized provider/resource behavior rather than question-specific scripts;
- govern Datto write capabilities separately from the established read-only surface.
<!-- END 2026-08-12 DATTO READ WORKSTREAM -->

## Latest durable success — varied-language complete collection interpretation

The production Teams request `List every site in Datto RMM` exposed and then verified correction of a generic language-contract defect. Jason now separates resource-recognition `inquiry_hints` from broader returnable `fact_hints`, normalizes exhaustive collection language to the capability's canonical `collection_fact`, and propagates `result_intent` plus `completeness_requirement` through planning.

For managed sites, exhaustive wording resolves to canonical `sites` evidence with `enumerate + complete`, allowing the existing Provider Adaptation layer to retrieve and verify the full authorized collection rather than rendering an incidental scalar `site` identifier.

Validated/deployed source checkpoint: `5b2c6c6` (`Separate inquiry hints from resource fact hints`). Runtime rebuild/deployment and health verification passed. The same production Teams request was retested and operator-accepted as correct.

Durable evidence: `docs/sessions/Datto-Governed-Read-Adaptation-Proof-2026-08-12.md`.

Construction rule: recognition aliases are not evidence contracts. Future resource capabilities must distinguish recognition vocabulary from returnable facts and declare a canonical collection fact when they expose a collection. Representable varied/vague questions must be repaired at the reusable interpretation/capability/evidence layer, never with question-specific scripts.

Next priority remains native Microsoft Teams processing feedback through OpenClaw's supported runtime/typing lifecycle.

<!-- BEGIN 2026-08-13 SEMANTIC CAPABILITY DISCOVERY -->
## Latest durable success — governed semantic capability discovery

Jason now has a bounded observe-only semantic capability-discovery path for requested facts that are not yet supported by registered capability/evidence metadata.

The validated progression is:

`intent → semantic planning → sufficiency validation → governed context progression → fulfillment infeasibility → capability-registry gap → registered-provider discovery → documentation-review target → governed documentation-source resolution → bounded documentation read → candidate evidence → semantic/corroborating evidence review`

The acceptance fact was:

`operating system display version`

Jason correctly determined that its current registered capability/evidence/derivation surface did not prove support for that fact. It produced a structured Technology Steward capability gap rather than inventing a mapping or requesting a bespoke script.

Registered-provider discovery identified Datto RMM as the existing `managed_endpoint` authority and exposed its authoritative API documentation for review.

A governed live read of the Datto OpenAPI source succeeded:

- OpenAPI `3.1.0`
- 53 paths
- 113 schemas
- SHA-256 provenance
- no credentials
- no operational provider invocation

The generic interpreter surfaced `Device.displayVersion` as candidate evidence. Semantic review remained correctly `ambiguous` because the OpenAPI property has no field description. Corroborating OpenAPI evidence established that `displayVersion` is a `string`, belongs to the `Device` schema beside `operatingSystem`, and is returned by three documented read-only device operations, but this still does not constitute semantic proof.

No semantic mapping, capability registration, runtime activation, or deployment was performed.

Current source checkpoint:

`060de83` — `Add live Datto corroborating evidence probe`

Reusable guidance:

`docs/engineering/capabilities/Resource-Inquiry-Evidence-Pattern.md`

Historical proof:

`docs/sessions/Governed-Semantic-Capability-Discovery-Proof-2026-08-13.md`

### Next safe action

Register the independent Kaseya Datto RMM product/help documentation as a second governed authoritative documentation source and use it to corroborate the meaning of `Device.displayVersion`.

If independent authoritative evidence is sufficient, create only a governed semantic-mapping proposal. Do not activate/register that mapping without Technology Steward/governance approval.
<!-- END 2026-08-13 SEMANTIC CAPABILITY DISCOVERY -->
