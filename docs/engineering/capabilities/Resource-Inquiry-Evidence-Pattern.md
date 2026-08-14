# Project Jason — Resource Inquiry / Evidence Pattern

**Status:** Active engineering guidance  
**Owner:** Jason Architecture Authority  
**Updated:** 2026-08-14

## Rule

Natural-language resource questions are capability/resource problems, not invitations to create one-off scripts.

Use this reusable flow:

1. Interpret a provider-neutral resource inquiry.
2. Keep resource selectors separate from requested facts.
3. Derive `resource_types`, `selector_keys`, and canonical `fact_hints` from governed provider-neutral read-only capability metadata.
4. Return the smallest set of facts needed to answer the human request; do not add adjacent inventory facts.
5. Resolve/invoke the provider through the Central Orchestrator.
6. Build a relevance-bounded structural evidence index from actual provider output.
7. Allow the reasoning model to select only JSON pointers Jason supplied.
8. Deterministically dereference the selected pointer and render the provider-backed value with source attribution.

The model interprets meaning; Jason controls authority, provider access, valid evidence locations, and returned values.

## 2026-08-12 failure mode and proof

For `AOT-50282`, Datto RMM returned:

`/lastLoggedInUser = AzureAD\AlDavis`

The Jason-shaped pointer was:

`/provider_data/lastLoggedInUser`

The bounded evidence index ranked that pointer first, and live Ollama evidence selection selected it correctly when the requested fact was correct.

The actual defect was upstream resource-language interpretation: selector/inventory vocabulary such as `from`, `query`, `registry_id`, `resource_id`, and `serial_number` was being emitted as `requested_facts`.

Production composition was corrected to pass capability-derived `fact_hints` into `OllamaResourceInquiryReasoner`. Endpoint fact hints were canonicalized into individual concepts such as `last logged in user`, `operating system`, `online`, `status`, `ip address`, and `serial number`. The prompt was strengthened to require only the smallest fact set actually requested.

Final live semantic checks:

- `Who last used AOT-50282?` -> `last logged in user`
- `What operating system is AOT-50282 running?` -> `operating_system`
- `Is AOT-50282 online?` -> `status`, `online`

Final Teams proof:

`AOT-50282 — last logged in user: AzureAD\AlDavis. Source: datto_rmm.`

## Non-negotiable

Do not create a bespoke `Who is logged into X?` script. If a representable resource question fails, identify and fix the reusable layer that is actually defective: interpretation, capability metadata, evidence indexing, bounded pointer selection, deterministic dereference, or rendering.

Historical proof: `docs/sessions/Teams-Datto-Resource-Semantic-Proof-2026-08-12.md`.

## 2026-08-14 deterministic canonical-fact qualifier resolution

Qualifier-rich language can be ambiguous even when Jason already has the necessary capabilities and evidence.

The production example was:

`What IP is AOT-50282 using internally?`

Generic interpretation could collapse this to `ip address`, losing the governed LAN/WAN distinction.

### Reusable rule

When eligible canonical facts share a generic recognition anchor, use deterministic tri-state qualifier analysis before generic semantic/model fallback:

- `not_applicable` — the contrast is not activated;
- `resolved` — the shared anchor exists and exactly one eligible fact has discriminating language;
- `ambiguous` — the shared anchor exists but no unique discriminator exists, or conflicting discriminators match.

For LAN/WAN:

- shared anchor: IP;
- LAN discrimination: internal, private, local;
- WAN discrimination: public, external, internet-facing.

The qualifier gate must run before ordinary longest-alias recognition.

`internal public IP` must therefore remain ambiguous rather than resolving through the longer `public IP` alias.

### Model boundary

Bounded Qwen experiments were rejected after one probe misclassified `internet-facing IP` and another guessed LAN for a bare IP request.

A model is not used merely to force selection between competing governed canonical facts.

### Execution boundary

Qualifier resolution may select only a canonical fact already exposed by governed capability metadata.

It does not select provider, provider field, connector, capability implementation, authorization, evidence pointer, or operational value.

Ambiguous requests stop before generic resource-language reasoning, action reasoning, capability planning, and orchestration.

### Live proof

Signed production ingress proved:

- internal IP -> LAN;
- internet-facing IP -> WAN;
- bare IP -> HTTP 400 / `conversation_unresolved`;
- ambiguous requests produced rejection rather than completion audit evidence;
- qualified requests completed normally; and
- runtime health remained good.

Historical proof:

`docs/sessions/Teams-Canonical-Fact-Qualifier-Proof-2026-08-14.md`

<!-- BEGIN 2026-08-13 SEMANTIC CAPABILITY DISCOVERY -->
## 2026-08-13 semantic capability-gap and provider-documentation discovery

The resource inquiry pattern now extends beyond selecting evidence already exposed by registered capabilities.

When the human asks for a representable fact but the current governed capability/evidence/derivation surface cannot establish it, Jason uses this generalized fail-closed progression:

1. Interpret the requested semantic fact.
2. Bootstrap the bounded planner with provider-neutral governed context.
3. Propose a provider-neutral fulfillment plan.
4. Validate plan sufficiency against the original requested facts.
5. Request additional governed context only when necessary and only from requestable views.
6. If capability/evidence/derivation context conclusively proves the fact cannot currently be fulfilled, return a structured capability-registry gap.
7. Review only registered provider candidates under Technology Steward ownership.
8. Resolve provider documentation through the governed documentation-source registry.
9. Read authoritative documentation using a bounded source adapter and transport.
10. Interpret operations, schemas, and fields as candidate evidence only.
11. Perform semantic-evidence and corroborating-evidence review.
12. If evidence remains ambiguous, preserve the unresolved gap.
13. If evidence is sufficient, permit creation of a governed semantic-mapping proposal only; approval and registry activation remain separate governed actions.

### Evidence-before-assertion rule

**Documentation similarity is not semantic proof.**

A field name such as `displayVersion`, `version`, `operatingSystem`, or any other plausible-looking provider property must not become a canonical Jason fact merely because its name resembles the requested concept.

Evidence review may consider:

- containing schema;
- provider-authored field description;
- field type;
- examples/defaults/enums;
- sibling fields;
- authoritative endpoint documentation;
- read-only operations returning the containing schema;
- independent authoritative provider documentation;
- immutable source/provenance references.

A documentation reader or reasoning model cannot approve a semantic mapping.

### Datto RMM proof case

The acceptance question was the provider-neutral fact:

`operating system display version`

The initial registered capability surface did not prove support for that fact.

The semantic planning path correctly returned a `capability_registry_gap` and identified `datto_rmm` as the registered managed-endpoint provider whose authoritative documentation should be reviewed.

The governed Datto OpenAPI source returned a valid OpenAPI 3.1.0 document with:

- 53 paths;
- 113 schemas; and
- SHA-256-addressed provenance.

The provider-neutral interpreter surfaced `Device.displayVersion` as candidate evidence and also surfaced unrelated textual matches such as BIOS, driver, display-hardware, and system-status fields. This demonstrated why lexical matching cannot establish semantics.

Further evidence established:

- schema: `Device`;
- field: `displayVersion`;
- type: `string`;
- sibling field: `operatingSystem`;
- schema description: `Device data`;
- read-only responses returning `Device`:
  - `GET /v2/device/id/{deviceId}`
  - `GET /v2/device/macAddress/{macAddress}`
  - `GET /v2/device/{deviceUid}`

The OpenAPI field itself has no description/example/default/enum, so OpenAPI-only semantic review correctly remained `ambiguous` and did not allow proposal creation.

That is the required behavior: missing semantic evidence produces an unresolved governed gap rather than an invented mapping.

Historical proof:

`docs/sessions/Governed-Semantic-Capability-Discovery-Proof-2026-08-13.md`
<!-- END 2026-08-13 SEMANTIC CAPABILITY DISCOVERY -->
