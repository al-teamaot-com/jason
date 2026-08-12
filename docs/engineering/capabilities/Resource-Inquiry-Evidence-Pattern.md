# Project Jason — Resource Inquiry / Evidence Pattern

**Status:** Active engineering guidance  
**Owner:** Jason Architecture Authority  
**Updated:** 2026-08-12

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
