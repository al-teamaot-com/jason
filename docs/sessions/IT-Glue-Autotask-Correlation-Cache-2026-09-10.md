# IT Glue + Autotask Governed Provider Reads: Correlation, Accountability, and Cache — 2026-09-10

## Scope

This record captures the source-side completion state for adding IT Glue and Autotask to Jason's governed provider-read architecture alongside Datto RMM. The work remains read-only and preserves the existing MCP surface. It does not deploy, restart, merge, activate production capabilities, or enable any provider write path.

## Architectural boundary

The intended reasoning/execution split remains:

ChatGPT Business
→ Jason MCP (`discover_capabilities` / `execute_read_capability`)
→ identity, authorization, organization/client scope
→ Central Orchestrator
→ provider-neutral capability/resource resolution
→ canonical entity/correlation layer
→ governed provider connectors
→ Autotask / IT Glue / Datto RMM
→ normalized governed evidence
→ ChatGPT Business reasoning

Jason performs deterministic authentication, authorization, provider selection, argument adaptation, provider API reads, bounded pagination, normalization, entity correlation, cache policy, evidence handling, timing, and auditing. Normal connector-backed reads do not invoke a second hosted model.

## Provider-backed acceptance already established

The earlier guarded live acceptance initially reached `capability_invocation_failed` for both IT Glue and Autotask. The shared cause was local access to the existing OpenBao AppRole bootstrap files: the files were root-owned mode `0600`. A bounded acceptance run using local root privilege solely to consume those existing read-only bootstrap credentials then passed for both providers through Central Orchestrator.

The accepted provider-backed proofs remain intentionally narrow:

- IT Glue: `documentation.organization.search` → `it_glue.entity.query`
- Autotask: `service.ticket.search` → `autotask.ticket.search`

Both proofs were read-only, bounded to one returned record, used the OpenBao logical-secret boundary, persisted no raw provider records, printed no credentials, performed no durable activation, and used no hosted model.

The source defaults remain fail-closed. The successful acceptance does not authorize production activation and does not prove every declared read capability.

## Safe failure classification

Shared provider-read failures now carry bounded machine classifications through Central Orchestrator instead of collapsing all failures into a generic invocation error.

Current bounded classifications include:

- `CONNECTOR_CREDENTIAL_UNAVAILABLE`
- `OPENBAO_AUTH_FAILED`
- `OPENBAO_SECRET_RESOLUTION_FAILED`
- `OPENBAO_TRANSPORT_FAILURE`
- `PROVIDER_HTTP_STATUS_<status>` for bounded HTTP statuses
- `PROVIDER_TRANSPORT_FAILURE`
- `PROVIDER_EXECUTION_DEADLINE_EXCEEDED`

The classifications do not retain or surface RoleIDs, SecretIDs, API keys, tokens, raw provider response bodies, or full exception text. The live acceptance harness now includes the bounded error code in a failed acceptance result so an operator can distinguish credential/bootstrap, OpenBao, provider HTTP, and transport classes without exposing protected material.

## Canonical cross-provider identity

Entity identity is kept separate from field-semantic mapping.

Supported canonical entity classes:

- organization
- endpoint
- person

A canonical entity may carry mappings such as:

- organization → Autotask Company ID → IT Glue Organization ID → Datto RMM Site ID
- endpoint → Autotask Configuration Item ID → IT Glue Configuration ID → Datto RMM Device ID
- person → Autotask Contact ID → IT Glue Contact ID → other governed identity evidence

Each provider mapping retains:

- canonical ID
- provider/resource/external ID
- organization scope
- correlation basis
- verification state
- confidence
- provenance
- observation timestamp
- optional source version

Correlation precedence is deterministic:

1. configured
2. explicit
3. corroborated
4. inferred

Configured/explicit mappings outrank inferred evidence even if an inference has a high confidence score. Equal-strength conflicting mappings remain ambiguous. An inferred relationship cannot silently become verified/certain.

The correlation registry grants no provider access or execution authority. All provider reads still pass current identity/authorization/client-scope checks and governed capability resolution.

## Cross-provider evidence composition

Jason can now deterministically expand a known governed provider resource into peer resources through the canonical correlation registry and compose successful reads into one reasoning package.

Example target flow:

1. Read/search Autotask ticket 12345 through the broad service-ticket capability.
2. Extract governed company/contact/configuration-item evidence from the ticket response.
3. Resolve the Autotask configuration item to a canonical endpoint.
4. Resolve only unambiguous mapped peer identities for IT Glue and Datto RMM.
5. Perform the approved broad provider-neutral reads through Central Orchestrator.
6. Preserve each provider capability, evidence reference, source reference, freshness class, mapping provenance, verification state, and confidence.
7. Compose one sanitized evidence package under the same correlation ID.
8. Hand that evidence package to ChatGPT Business for reasoning.

A failed/denied provider result cannot enter a successful cross-provider evidence package. Ambiguous peer mappings fail closed before provider routing rather than silently selecting a record.

## Governed evidence cache

The provider-neutral cache uses these freshness classes:

| Freshness | Intended examples | Reuse policy |
| --- | --- | --- |
| `static` | policies, SOPs, IT Glue documentation, explicit provider-ID mappings | reusable only with current authorization and source version/hash identity |
| `slow_change` | contacts, organization metadata, configuration metadata | bounded reuse; default source policy currently six hours |
| `transactional` | tickets and similar changing business records | short bounded reuse; default source policy currently five minutes |
| `realtime` | online state, CPU/memory, logged-in user, processes/services, current alerts | never admitted to reusable cache |

Static evidence requires a provider source version or source hash so source-change invalidation can be preferred over arbitrary TTL alone.

Every cache entry preserves organization/client scope, provider/source identity, source version/hash when available, observed/cached timestamps, provenance, evidence references, a payload hash, and sanitized data.

Every cache lookup requires a current authorization callback. The permissions of the actor that populated a cache entry never authorize a later reader. Exact organization/client scope is checked before a hit is returned.

## Accountability and model-cost telemetry

Central Orchestrator already records execution/correlation identity and now records bounded connector invocation telemetry for provider-backed reads.

The accountability envelope includes:

- execution ID
- correlation/trace ID
- initiating principal
- organization/client scope
- requester/authority context where present
- canonical capability
- selected provider
- provider capability/resource family
- provider evidence references
- correlation/mapping references when supplied
- invocation duration
- attempts/status/error classification
- hosted-model-used flag
- hosted-model name when applicable
- hosted-model input/output tokens
- hosted-model cost

The governed connector invoker explicitly attests for normal IT Glue / Autotask / Datto RMM deterministic reads:

- `hosted_model_used = false`
- input tokens = `0`
- output tokens = `0`
- Jason-side hosted-model cost = `$0`

This avoids treating zero model cost as an undocumented assumption.

## Generic resource convergence

Autotask is now routed through the same generic governed resource executor used by the existing resource-convergence layer rather than through a new provider-specific MCP tool. The shared Autotask resource adapter translates authorized generic resource queries to the existing broad connector capability boundary.

No phrase-specific functions or new provider-specific MCP tools were introduced.

## CI coverage

The provider-read validation workflow now directly covers:

- IT Glue and Autotask provider-read foundations
- shared OpenBao/connector safe failure classification
- Central Orchestrator failure-code preservation
- zero-model connector telemetry
- canonical entity correlation precedence and ambiguity
- governed cache freshness, source-change invalidation, and current-user authorization
- cross-provider evidence composition
- Autotask use of the generic resource-convergence executor
- credential-safe no-network live-acceptance preflight
- source-side fail-closed lifecycle/cost assertions

The resource-convergence workflow now validates Autotask alongside the existing convergence primitives while keeping provider behavior read-only.

## Production boundary / remaining checkpoint

Source work does not change production activation state. The following remain explicit later checkpoints rather than implicit consequences of this PR:

1. Run one bounded provider-backed acceptance against the final PR head to prove the new diagnostic path without changing provider data or durable activation.
2. Preferably run one targeted real-record correlation proof under a single correlation ID (for example a known Autotask ticket/configuration item correlated to IT Glue and/or Datto RMM) before production activation.
3. Verify how the production runtime identity will safely consume the root-owned AppRole bootstrap material without broadening credential exposure.
4. Obtain explicit approval before any production deployment, service restart, provider/capability activation, or PR merge.

IT Glue password/credential-vault secrets remain outside this workstream and outside the initial read surface.
