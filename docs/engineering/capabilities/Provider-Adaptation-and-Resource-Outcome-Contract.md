# Provider Adaptation and Resource Outcome Contract

**Project:** Project Jason  
**Status:** Production foundation implemented and live-proven  
**Initial production proof:** 2026-08-12  
**Architectural scope:** Central Orchestrator governed resource inquiries and provider read execution

## Purpose

Jason must support varied, natural, incomplete, and non-standard human questions without requiring question-specific scripts, hard-coded phrases, or provider-specific conversational workflows.

Human language is interpreted into a governed resource inquiry. The inquiry describes what resource is being requested, what facts are needed, the intended result shape, and whether the answer requires complete provider evidence.

Provider execution remains behind governed reusable capabilities.

## Core Architectural Rule

Jason must not depend on predefined question phrasing.

Natural-language requests are interpreted into governed resource inquiry contracts. Capabilities execute those contracts. Provider-specific implementation details remain behind provider/connector boundaries.

The human does not select providers, grant authority, bypass policy, or directly invoke connector operations by mentioning provider names.

## Governed Resource Inquiry Contract

The resource inquiry contract includes:

- `resource_type`
- `resource_selector`
- `requested_facts`
- `execution_mode`
- `permission_mode`
- `result_intent`
- `completeness_requirement`

### Result Intent

Supported initial result intents:

- `summary`
- `enumerate`
- `count`
- `search`
- `inspect`

### Completeness Requirement

Supported initial completeness requirements:

- `sufficient`
- `complete`

Completeness is part of correctness.

A partial collection must never be represented as a complete answer when the human requested a count, complete enumeration, exhaustive result, or other outcome that requires the full authorized collection.

## Deterministic-First Interpretation

Jason prefers deterministic interpretation when governed capability metadata unambiguously establishes the intended resource inquiry.

The language model is retained as a bounded semantic fallback for requests that cannot be safely resolved deterministically.

This prevents simple resource questions from failing merely because a language model produced malformed structured JSON.

Example production behavior:

`What sites are in Datto RMM?`

can resolve deterministically to:

- resource type: `management_site`
- selector: none
- requested fact: `sites`
- result intent: `summary`
- completeness requirement: `sufficient`
- execution mode: `deterministic`
- permission mode: `observe`

No Ollama invocation is required for that deterministic interpretation.

## Recognition Vocabulary and Canonical Evidence Facts

Human wording used to recognize a resource is not itself authoritative evidence vocabulary.

Capability metadata therefore distinguishes:

- `inquiry_hints` — words and phrases that identify the resource/capability being requested;
- `fact_hints` — facts that the capability can return; and
- `collection_fact` — the canonical collection evidence fact used when an exhaustive collection outcome is requested.

This separation prevents incidental fields from competing with the resource the human actually asked about. For example, a management-alert capability may return a `site` field, but the word `site` must not cause a request for Datto managed sites to resolve as an alert inquiry.

For exhaustive collection language such as `list every`, `list all`, or a count request, Jason normalizes recognized singular/plural/synonym wording to the governed `collection_fact` and carries the outcome contract through planning. A managed-site enumeration therefore resolves to the canonical `sites` fact with `result_intent=enumerate` and `completeness_requirement=complete`.

The rule is generic: recognition aliases help understand human language; canonical facts define what governed evidence must be retrieved. Do not create phrase-specific handlers for individual questions.

## Provider Adaptation Layer

Transport success is not equivalent to trustworthy evidence.

A provider may return HTTP success while returning incomplete, contradictory, malformed, truncated, incorrectly paginated, or otherwise semantically unreliable data.

Jason therefore includes a bounded Provider Adaptation Layer at the provider boundary.

### Provider Adaptation Responsibilities

The adaptation layer may:

- detect contradictory provider collection evidence;
- inspect provider-supplied pagination metadata;
- perform bounded read-only probes;
- recover a usable provider retrieval strategy;
- follow provider pagination evidence;
- aggregate complete authorized collections when required;
- verify declared count against collected count;
- detect repeated or prematurely terminated pagination;
- fail closed when provider evidence cannot be made trustworthy;
- emit audit evidence describing the adaptation.

### Provider Adaptation Must Not

Provider adaptation must not:

- mutate provider state;
- silently modify Jason source code;
- silently change production configuration;
- bypass Central Orchestrator authority;
- broaden authorized scope;
- invent missing provider evidence;
- convert contradictory evidence into a false empty result.

## Bounded Recovery

Adaptive discovery is bounded.

Initial implementation controls include:

- maximum probe count;
- maximum page count;
- maximum item count;
- provider-supplied page evidence preferred over arbitrary guessing;
- read-only execution only;
- failure closed when evidence remains inconsistent.

## Complete Collection Aggregation

When `completeness_requirement=complete`, Jason may aggregate provider pages until the declared authorized collection is complete.

Completion requires the resulting collection count to agree with provider-declared total evidence.

If pagination stops prematurely, repeats pages, exceeds bounded limits, or otherwise becomes inconsistent, Jason fails closed rather than presenting the partial collection as complete.

## Datto RMM Production Proof

Datto RMM `/api/v2/account/sites` exposed a real provider behavior inconsistency during production testing.

An initial request returned:

- `totalCount = 46`
- collection count = `0`

while still returning successful transport status.

Jason's Provider Adaptation Layer detected the contradiction.

Bounded recovery established:

- page: `0`
- max: `25`

The provider returned the first 25 records and supplied pagination evidence for the next page.

For a complete enumeration request, Jason then followed the provider pagination evidence and aggregated:

- pages aggregated: `2`
- final collection count: `46`
- declared total: `46`
- complete: `True`

The collection was therefore verified complete before being returned as complete evidence.

## Why This Matters

This behavior is intentionally generic.

Jason was not taught a special rule equivalent to:

> If the user asks about Datto sites, use page zero and max 25.

Instead, Jason was given a reusable mechanism to recognize contradictory provider evidence, perform bounded read-only adaptation, follow provider evidence, and verify completeness.

The same architecture can support future provider irregularities involving:

- pagination;
- page-size limits;
- continuation tokens;
- provider response envelopes;
- malformed collection metadata;
- API version drift;
- incomplete records;
- provider-side behavioral changes.

## Response Shaping

Evidence retrieval and response shaping are separate responsibilities.

Examples:

`What sites are in Datto RMM?`

may request:

- result intent: `summary`
- completeness: `sufficient`

A bounded preview is acceptable.

`Please list the sites in Datto RMM.`

requests:

- result intent: `enumerate`
- completeness: `complete`

The authorized complete collection must be considered.

`How many sites are in Datto RMM?`

requests:

- result intent: `count`
- completeness: `complete`

The count must be based on complete verified evidence.

This distinction is resource-contract behavior, not provider-specific question matching.

## Authority

All provider adaptation remains subject to Jason's existing identity-first authorization, capability governance, Central Orchestrator routing, provider selection, policy enforcement, audit, and tenant/client boundaries.

Provider adaptation changes retrieval behavior only inside an already authorized read capability.

It does not grant authority.

## Provider Read Authority

The initial AOT policy permits authenticated AOT organizational users to perform governed read-only Datto RMM inquiries under the organization-wide provider-read observe grant.

Consequential Datto write operations remain outside this read authority and will be governed separately.

## Evidence Selection

Direct structurally authoritative provider fields are preferred over arbitrary semantic traversal.

Collections such as:

- alerts;
- software;
- sites;

must be preserved as collections when the requested fact corresponds directly to the normalized provider result field.

Language reasoning must not collapse a structurally authoritative collection into an arbitrary nested scalar.

## Operational Principle

The architecture follows Project Jason's core rule:

**Integrate before innovate.**

Datto RMM remains the endpoint-management authority.

Jason does not duplicate Datto state collection. Jason provides governed, adaptive, provider-neutral access to existing authoritative information.

## Future Evolution

The Provider Adaptation Layer should evolve toward structured observed-provider behavior profiles associated with provider capabilities and System Registry state.

Future extensions may include:

- durable observed provider behavior profiles;
- provider behavior drift detection;
- continuation-token strategies;
- rate-limit adaptation;
- schema/version change observations;
- reusable provider pagination strategies;
- recommendation of retirement for obsolete workarounds.

Durable operational changes remain governed and may not be silently applied by adaptive runtime behavior.
