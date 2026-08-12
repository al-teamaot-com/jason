# Datto Governed Read and Provider Adaptation Proof — 2026-08-12

## Outcome

Project Jason successfully expanded the governed Datto RMM read surface and proved varied natural-language resource inquiries through Microsoft Teams and the production Jason runtime.

The workstream also produced the first live proof of generic Provider Adaptation.

## Proven Read Capabilities

The production Datto provider exposes governed read capabilities including:

- endpoint discovery/read;
- endpoint alerts;
- endpoint audit information;
- endpoint software inventory;
- account-wide alerts;
- managed sites.

These capabilities remain reusable provider-neutral resources at the orchestration layer.

## Identity and Authority

A durable organization-level read authority grant was activated:

- grant: `grant-aot-datto-provider-read-observe`
- subject: `organization:aot`
- capability family: `provider-read:datto_rmm`
- permission: `observe`
- approval required: `False`
- status: `active`

This permits governed read-only Datto access for the current AOT organizational policy.

It does not authorize write operations.

## Teams Device Proof

Device:

`AOT-50282`

Jason successfully answered read-only endpoint information through Teams.

Examples included:

- last logged-in user;
- alerts;
- software inventory.

### Last Logged-In User

Verified Teams result:

`AzureAD\AlDavis`

Source:

`datto_rmm`

### Endpoint Alert

Jason successfully retrieved the open Datto alert for AOT-50282.

The original provider evidence contained extensive raw diagnostics.

Response rendering was changed so normal Teams responses present bounded operational summaries instead of dumping provider diagnostics.

### Software Inventory

An initial provider paging behavior caused software inventory to appear empty.

Live provider proof established that a bounded request returned the actual software collection.

A structural evidence fix ensured `/provider_data/software` remained authoritative collection evidence rather than being reduced to one scalar.

Production Teams proof returned:

- 19 software records;
- first several applications;
- bounded `+14 more` summary.

## Managed Site Provider Adaptation Proof

An initial Datto site request returned:

- provider transport success;
- `totalCount = 46`;
- zero returned records.

Jason's Provider Adaptation Layer detected that the response was semantically inconsistent.

Bounded recovery identified a usable provider retrieval:

- page: `0`
- max: `25`

The first recovered page contained 25 sites.

Provider pagination evidence identified the next page.

For `completeness_requirement=complete`, Jason aggregated the remaining page.

Final proof:

- declared total: `46`
- final count: `46`
- pages aggregated: `2`
- complete: `True`
- adaptive recovery: PASS

No credential values were printed.

## Deterministic-First Language Interpretation

A production failure was traced to:

`ValueError: Ollama structured response is not JSON after bounded retry`

for a simple managed-site inquiry.

The resource pipeline was changed to prefer deterministic interpretation when capability metadata uniquely resolves the request.

Ollama remains the fallback for semantic ambiguity.

Production proof for:

`What sites are in Datto RMM?`

returned:

- resource type: `management_site`
- selector: `{}`
- facts: `sites`
- execution: `deterministic`
- permission: `observe`
- Ollama calls: `0`

## Resource Outcome Contract

The governed inquiry contract now distinguishes the requested outcome.

New first-class fields:

- `result_intent`
- `completeness_requirement`

Initial result intents:

- summary
- enumerate
- count
- search
- inspect

Completeness:

- sufficient
- complete

This prevents partial collections from being presented as complete answers.

## Production Validation

Final focused test suite:

PASS

Static diff validation:

PASS

Python compile validation:

PASS

Live complete Datto collection proof:

PASS

Production compose validation:

PASS

Production runtime build:

PASS

Production deployment:

PASS

Runtime health:

PASS

## Architectural Significance

This workstream demonstrated the desired Jason design principle:

Jason did not require a question-specific script or Datto-sites workaround.

Instead, the system detected contradictory provider evidence, safely adapted the read strategy, followed provider pagination evidence, verified completeness, and preserved governance.

This pattern is reusable for future provider behavior and API drift.
