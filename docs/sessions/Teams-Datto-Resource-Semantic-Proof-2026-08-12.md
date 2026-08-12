# Teams → OpenClaw → Jason → Datto RMM Semantic Resource Proof — 2026-08-12

**Status:** Successful production proof  
**Branch:** `feature/jason-runtime-service`  
**Starting / last verified pre-documentation HEAD:** `25bc07a`

## Objective

Make a normal Teams question such as `Who last used AOT-50282?` return the actual provider-backed last logged-in user through Jason's governed, reusable resource inquiry path — without creating a workflow-specific script.

## Starting condition

Teams → OpenClaw → Jason → Datto RMM already worked end-to-end, but the response was semantically wrong:

`AOT-50282 — from: AOT-50282. Source: datto_rmm.`

Infrastructure, Teams identity, OpenBao, Microsoft credentials, Datto connectivity, prompt-size handling, and arbitrary JSON-pointer hallucination were not the active defect.

## Provider truth established

An exact live Datto RMM device read for UID `69571572-83f7-1e33-9cdf-01717d4e74a4` established:

- Hostname: `AOT-50282`
- Datto field: `/lastLoggedInUser`
- Value: `AzureAD\AlDavis`

The production-shaped Jason result exposed the same fact as:

`/provider_data/lastLoggedInUser`

## Evidence layer verification

The relevance-bounded structural evidence index contained `/provider_data/lastLoggedInUser` at position 1.

Live Ollama evidence selection, when asked for `last logged in user`, selected exactly:

`/provider_data/lastLoggedInUser`

Therefore provider retrieval, evidence indexing, constrained pointer schema, and evidence selection were working.

## Root cause

The defect was earlier in natural-language resource interpretation. For user-oriented questions, the inquiry reasoner emitted selector/inventory vocabulary such as `from`, `query`, `registry_id`, `name`, `resource_id`, and `serial_number` as requested facts.

This caused the downstream evidence layer to answer the wrong semantic question correctly.

## Generic fix

The fix remained capability/resource-driven:

- Production composition derives `resource_types`, `selector_keys`, and `fact_hints` from governed provider-neutral read-only capability metadata.
- `fact_hints` are supplied to `OllamaResourceInquiryReasoner`.
- Endpoint fact hints are canonicalized as discrete concepts rather than one broad inventory sentence.
- The inquiry prompt requires the smallest fact set needed to answer the user's actual question.
- Evidence JSON pointers remain bounded to pointers Jason actually supplied.
- No direct agent-to-agent behavior and no bespoke `Who is logged into X?` script were introduced.

## Validation

Focused automated tests passed: `20 passed`.

Static validation passed:

- `git diff --check`: 0
- Python compile validation: 0

Final live semantic checks produced:

- `Who last used AOT-50282?` -> selector `hostname=AOT-50282`; fact `last logged in user`
- `What operating system is AOT-50282 running?` -> fact `operating_system`
- `Is AOT-50282 online?` -> facts `status`, `online`

## Deployment

Authoritative deployment metadata was discovered from the running container rather than assumed:

- Compose directory: `/home/al/projects/jason/infrastructure/jason-runtime`
- Compose file: `/home/al/projects/jason/infrastructure/jason-runtime/compose.yaml`
- Compose project/service: `jason-runtime`

Required environment/mount values were derived from the running runtime. Microsoft Graph secret host paths were confirmed with privileged metadata checks because the normal account could not traverse the protected parent directory. Secret values were not read or printed.

Compose validation passed, image `jason-runtime:local` built successfully, the container restarted, and health passed.

## Final production proof

Teams returned:

`AOT-50282 — last logged in user: AzureAD\AlDavis. Source: datto_rmm.`

This proves the full production path:

Teams → OpenClaw transport/interface → Jason Central Orchestrator → governed resource inquiry → Datto RMM provider → bounded evidence interpretation → Teams response.

## Durable lesson

When a resource question returns the wrong field, diagnose the semantic contract from user language through requested facts before changing provider connectivity or creating a script. Provider truth, requested fact, evidence pointer, and rendered value must be verified as separate stages.

## Git durability note

At successful deployment, the modified runtime worktree was still uncommitted and HEAD remained `25bc07a`. Deployment was operationally successful but did not itself make the source changes durable in GitHub. Any later code commit must be separately reviewed/authorized.
