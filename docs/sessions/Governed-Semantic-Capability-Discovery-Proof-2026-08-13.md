# Governed Semantic Capability Discovery Proof — 2026-08-13

## Status

Validated source-level and live documentation-discovery proof.

No runtime activation or production deployment of the semantic planner was performed in this workstream.

## Purpose

Prove that Jason can respond safely when a requested semantic fact is not yet represented by the registered capability/evidence surface.

The acceptance fact was:

`operating system display version`

The workstream was intentionally provider-neutral. Datto RMM was discovered through governed provider metadata rather than hard-coded into semantic planning.

## Governed progression proven

The validated chain is:

**intent → bounded semantic planning → plan sufficiency → governed context progression → fulfillment feasibility → structured capability gap → registered-provider discovery → bounded documentation review → governed documentation source resolution → bounded authoritative documentation read → candidate evidence interpretation → semantic-evidence review → corroborating-evidence review**

No stage may silently create execution authority or semantic truth.

## Key controls proven

The implementation demonstrated that:

- the local reasoner receives bounded provider-neutral governed context;
- repeated satisfied context requests fail closed;
- supplied views are removed from requestable context choices;
- insufficient plans cannot become valid merely because the model asserts expected evidence;
- conclusively infeasible fulfillment produces a structured capability-registry gap;
- provider discovery is limited to registered providers;
- documentation review is Technology-Steward-owned and review-only;
- symbolic documentation names resolve through a governed source registry;
- documentation-source definitions contain no credential values;
- HTTPS documentation retrieval is bounded by timeout and size limits;
- OpenAPI reads are content-addressed with SHA-256 provenance;
- documentation findings are candidate evidence only;
- documentation readers cannot set semantic proof;
- ambiguous semantic evidence remains unresolved;
- no one-off Datto/Windows question script was introduced.

## Live Datto documentation proof

The governed source:

`datto-rmm-openapi-v2`

resolved to the vendor-documented Datto RMM OpenAPI source.

Live read result:

- status: available
- OpenAPI version: `3.1.0`
- document size: approximately 94 KB
- path count: `53`
- schema count: `113`
- credentials used: no
- operational Datto provider call: no

The content was retained only as bounded in-memory documentation evidence and referenced by SHA-256 provenance.

## Candidate-evidence proof

For the requested fact `operating system display version`, the generic OpenAPI interpreter surfaced multiple lexical candidates, including unrelated version/system/display fields.

A materially relevant candidate was:

- provider: `datto_rmm`
- schema: `Device`
- field: `displayVersion`
- type: `string`

The candidate remained `semantic_proof=False`.

This demonstrated that lexical relevance alone is intentionally insufficient.

## Semantic evidence review

Authoritative OpenAPI review established three read-only operations returning the containing `Device` schema:

- `GET /v2/device/id/{deviceId}`
- `GET /v2/device/macAddress/{macAddress}`
- `GET /v2/device/{deviceUid}`

However, the `displayVersion` field contains no provider-authored description.

Result:

- review status: `ambiguous`
- proposal allowed: `False`
- semantic mapping approved: `False`

## Corroborating evidence

Additional authoritative OpenAPI context established:

- schema description: `Device data`
- sibling field: `operatingSystem`
- field example: none
- field default: none
- field enum: none
- semantic proof: false

The evidence is suggestive but does not independently establish semantic equivalence.

Jason therefore preserved the ambiguity instead of guessing.

## Durable source checkpoints

Important workstream checkpoints include:

- `22f4bea` — Bootstrap governed semantic planning context
- `ff05b1a` — Reconcile satisfied context during semantic planning
- `194afd0` — Enforce requestable context in semantic planning
- `4618267` — Recover bounded Ollama structured responses from truncation
- `e6655cb` — Fail closed on infeasible semantic fulfillment paths
- `db91685` — Expose governed semantic capability gaps
- `d5499ed` — Add governed provider capability discovery foundation
- `256ac72` — Wire governed provider discovery into capability gaps
- `e766b9c` — Add governed provider documentation review foundation
- `0d16acb` — Add governed provider documentation reader foundation
- `72b3cff` — Add governed provider documentation source registry
- `c55bc31` — Add governed OpenAPI documentation source adapter
- `bbc5d0f` — Correct Datto governed OpenAPI source locator
- `323088e` — Add governed live documentation transport
- `1f14405` — Add governed OpenAPI documentation interpretation
- `c277d3b` — Add governed semantic evidence review foundation
- `cca5830` — Add live Datto semantic evidence review probe
- `156b46d` — Add governed corroborating evidence review
- `060de83` — Add live Datto corroborating evidence probe

## GitHub transport incident

During checkpoint `323088e`, direct HTTPS push repeatedly returned GitHub `Internal Server Error` after successful authentication and pack receipt.

The same commit successfully pushed to a temporary diagnostic branch. Updating `feature/jason-runtime-service` from the already-uploaded diagnostic remote ref then succeeded.

This proved the local commit and authentication were valid and avoided unnecessary history rewriting.

The diagnostic branch may be removed later after normal push stability is established.

## Constitutional outcome

The workstream reinforced these Project Jason rules:

- integrate before innovate;
- capability/resource-driven orchestration instead of bespoke scripts;
- Central Orchestrator remains the authority boundary;
- evidence before assertion;
- documentation similarity is not semantic proof;
- provider discovery does not imply provider authority;
- model reasoning never creates semantic truth;
- unresolved ambiguity fails closed;
- Technology Steward governs provider/documentation evolution;
- mappings and registrations require separate governed approval and versioned evidence.

## Next safe work

1. Register the Kaseya Datto RMM human/product documentation as an additional authoritative governed source.
2. Retrieve that source through the same governed documentation architecture.
3. Correlate independent vendor semantic documentation with the OpenAPI `Device.displayVersion` evidence.
4. If cross-source evidence is sufficient, create a semantic-mapping **proposal**.
5. Do not activate or register the mapping until Technology Steward/governance approval.
6. After an approved mapping exists, update provider-neutral capability/evidence metadata.
7. Only then retest the original intent through the bounded planning path.

