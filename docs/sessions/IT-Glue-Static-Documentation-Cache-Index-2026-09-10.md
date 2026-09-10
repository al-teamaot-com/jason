# IT Glue Static Documentation Retrieval + Governed Cache Index — 2026-09-10

## Scope

This record extends PR #171 with source-side support for governed IT Glue document, policy, procedure, and SOP reads plus provider-neutral static evidence indexing.

This work is read-only. It does not deploy or restart production services, stage credentials, mutate provider data, activate additional MCP capabilities, merge the PR, or enable any provider write path.

## Architecture preserved

The existing MCP surface remains unchanged:

- `jason_mcp_status`
- `discover_capabilities`
- `execute_read_capability`

No IT Glue-specific MCP tool and no phrase-specific policy lookup function was added.

The flow remains:

ChatGPT Business
→ Jason MCP
→ current identity / authorization / organization-client scope
→ Central Orchestrator
→ provider-neutral documentation capability/resource
→ governed IT Glue connector
→ sanitized evidence
→ governed evidence cache/index when eligible
→ ChatGPT Business reasoning

Jason performs deterministic provider access, cache/index policy, source freshness validation, evidence handling, and accounting. No second hosted model is required for the deterministic read/cache/index path.

## Canonical document resource

Two provider-neutral canonical capabilities were added:

- `documentation.document.search`
- `documentation.document.read`

They cover resource concepts such as document, policy, procedure, SOP, and standard without exposing IT Glue provider vocabulary at the MCP contract.

The provider adapter maps these only after governed provider selection:

- `documentation.document.search` → IT Glue bounded `Documents` collection query through `it_glue.entity.query`
- `documentation.document.read` → `it_glue.document.get`

The IT Glue password / credential-vault surface remains excluded.

Both new canonical capabilities remain `PILOT`. They are intentionally not part of the source-controlled initial production activation allowlist because they do not yet have provider-backed live acceptance evidence.

## Generic resource convergence

The shared IT Glue resource adapter now supports generic `document` GET and QUERY operations. Document collection reads retain the same bounded page-size/page-number model as other IT Glue collection reads.

This keeps document access behind the reusable resource interface instead of introducing a one-off policy workflow.

## Governed static evidence index

A provider-neutral `GovernedEvidenceIndex` now stores searchable pointers into `GovernedEvidenceCache`.

The index stores only:

- cache key
- organization/client scope
- provider/resource/external identity
- source reference
- source version/hash identity
- SHA-256 hashes of normalized search terms

It deliberately does not duplicate document bodies.

A candidate index hit is not authority to read cached evidence. Every returned result must pass the underlying governed cache lookup, which rechecks:

1. exact current organization/client scope;
2. caller-supplied current authorization;
3. current source version/hash identity.

Static search fails closed if current source version/hash cannot be established. If the source hash/version changed, the stale cache entry is not returned.

The current-source identity resolver can be backed later by inexpensive provider metadata observation, an event/webhook-maintained version ledger, or another governed source of current source identity. It must not expose protected content.

## Suitable policy-query behavior

The source foundation now supports this deterministic pattern for questions such as “What is this company’s policy on X?” after document-provider acceptance and runtime enablement:

1. resolve current organization/client scope;
2. search the authorized static documentation index;
3. validate current source version/hash;
4. re-authorize the current principal for each candidate cache entry;
5. return sanitized governed document evidence;
6. if no valid indexed evidence exists, use the canonical document search/read provider path and admit eligible sanitized evidence to the static cache/index;
7. hand the evidence to ChatGPT Business for reasoning.

The index does not itself grant provider access and does not bypass the Central Orchestrator/provider authorization path on a miss or refresh.

## Realtime boundary remains unchanged

Realtime DRMM operational evidence remains `REALTIME` and is not admitted to reusable cache. Existing tests continue to prove that realtime `put` operations bypass the cache, and cross-provider evidence composition labels DRMM endpoint operational observations as realtime where declared by the capability freshness map.

## Regression coverage

The scoped `Validate Governed Provider Reads` workflow now compiles/tests the new index and document-read boundaries, including:

- document capabilities remain provider-neutral, read-only, and `PILOT`;
- IT Glue sensitive password/credential-vault resources remain excluded;
- canonical document search/read argument adaptation;
- generic IT Glue document GET/QUERY translation;
- runtime registration without provider I/O;
- static index does not duplicate document content;
- exact organization/client scope enforcement;
- current-user authorization on every indexed cache hit;
- current source version/hash required for static index reuse;
- stale source hash invalidation;
- non-static evidence cannot enter the static index.

At feature head `7317c0b550a446f83dadc126d083e93579614874`, `Validate Governed Provider Reads` passed, as did the provider-read runtime activation, runtime credential, IT Glue, Autotask, Datto RMM, cross-provider convergence, provider-correlation, identity-authority, provider-secret, and Teams gateway workflows.

The broad `Validate Jason` and `Validate Conversation Experience Foundation` workflows still fail on pre-existing Conversation Experience composition/test issues outside this provider-read workstream (including missing `providers` arguments in Conversation Experience test/cutover paths and a test attempting to create `/var/lib/jason` in GitHub Actions). No provider-read failure was observed in those logs.

## Production boundary

The earlier provider-backed acceptance remains valid for the already-proven narrow IT Glue and Autotask read paths. The new document search/read capabilities are source-complete but not provider-backed accepted and therefore remain `PILOT`/undiscoverable through the normal active MCP surface.

The production host credential-staging metadata-only `--check-only` preflight was already completed without reading credential contents or mutating runtime state.

The next production action for the already-approved initial provider-read subset remains gated on explicit production approval because it would stage protected runtime credential copies and recreate `jason-runtime`.

Separately, document/policy capabilities must receive their own bounded provider-backed live acceptance before they may be considered for any future activation profile.
