# System Registry Governed Query Surface — 2026-08-11

## Purpose

Record the implementation of Jason's read-only governed System Registry query surface so operational topology and state can be obtained through Jason's normal capability/resource architecture rather than reconstructed from conversation memory or manually inspected files.

This record documents implementation and validation. It does not represent production deployment or lifecycle verification of the new query provider and capabilities.

## Authority

This work implements:

- J-002 Article XIX — Authoritative Operational State;
- J-103 — Jason System Registry;
- J-101 — Capability Registry architecture; and
- the constitutional rule that the System Registry is authoritative for operational topology but is not self-authorizing.

## Implemented query capabilities

Three provider-neutral, deterministic, read-only capabilities were added:

- `system.registry.search`
- `system.registry.read`
- `system.registry.trace`

The current internal execution provider is `system_registry`.

The provider reads the governed production System Registry baseline plus append-only lifecycle-event history so results reflect effective lifecycle state rather than stale baseline state alone.

## Runtime integration

The production runtime composition now registers the System Registry capabilities and provider alongside existing governed capabilities.

The three capabilities are registered with the normal `CapabilityInvokerRegistry`. Requests therefore remain subject to the existing Central Orchestrator path, including identity/authority context, capability resolution, provider resolution, policy, audit, and invocation controls.

The System Registry invoker rejects any permission mode other than `observe` and rejects any resolution that selects a provider other than `system_registry`.

## Query behavior

### Search

Search accepts grounded selectors for registered entity name, registry ID, entity type, environment, lifecycle, or a general query string.

Search results return durable System Registry `resource_id` values. Identity-like searches that produce multiple matches fail closed instead of selecting the first result.

### Read

Read requires a durable System Registry `resource_id` and returns the authoritative entity record plus derived relationship and verification information.

### Trace

Trace accepts two grounded System Registry references and computes a deterministic shortest relationship path across registered dependency and reverse-dependency edges.

The trace operation reads topology only. It does not invoke, test, repair, enable, disable, or reconfigure any entity in the returned path.

## Returned operational facts

The provider may return:

- registry ID and display name;
- entity type and environment;
- effective lifecycle state;
- declared state;
- direct dependencies and dependents;
- transitive dependencies and dependents;
- verification methods and current verification status;
- verification and evidence references;
- authority references;
- credential references, never credential values;
- steward; and
- source version.

No secret retrieval surface was added.

## Evidence boundary

Natural-language reasoning may describe the requested resource and requested facts, but it has no authority to invent topology or assert values.

System Registry facts are returned from deterministic registry data. Existing resource-evidence handling continues to require deterministic dereferencing of provider evidence before a value may be rendered to the human.

## Registered operational state

The production System Registry now contains four new `configured` entities:

- `provider.system-registry`
- `capability.system-registry-search`
- `capability.system-registry-read`
- `capability.system-registry-trace`

They intentionally remain `configured`, not `verified` or `active`.

Their registered verification methods are:

- provider: `governed-system-registry-read`
- capabilities: `capability-registry-and-runtime-proof`

The existing physical host verification plan remains bounded to physical Docker/container/file checks and does not falsely treat these logical runtime capabilities as host-probe-verifiable resources.

## CI validation

Before this documentation update, Validate Jason run `31511445371` completed successfully on the feature branch. The System Registry job successfully compiled and tested the governed query surface, validated schemas and topology, confirmed generated documentation currency, and passed constitutional System Registry tests. Runtime, capability, documentation, and repository-hygiene jobs also succeeded.

A fresh CI run is required after this documentation commit before merge.

## Production boundary

No production container was rebuilt or restarted as part of this implementation record.

The new query surface is not represented as production-verified until the governed runtime image is rebuilt/deployed through the normal deployment process and current runtime evidence demonstrates that:

1. `system.registry.search` resolves through the Central Orchestrator to `system_registry`;
2. `system.registry.read` returns authoritative effective lifecycle and dependency state;
3. `system.registry.trace` returns a registered topology path;
4. non-observe attempts fail closed;
5. ambiguous identity-like searches fail closed; and
6. the normal audit trail records the governed invocation path.

After successful production proof, lifecycle promotion must be recorded through append-only governed lifecycle events rather than by silently rewriting historical state.

## Expected next production proof

A suitable bounded proof should include at least:

- reading `component.jason-runtime` and confirming its effective lifecycle is `verified`;
- reading or searching `provider.datto-rmm` and confirming its registered dependencies;
- tracing `component.openclaw-jason-bridge` to `provider.datto-rmm` and confirming the path traverses registered topology; and
- confirming no System Registry mutation or remediation occurs during any query.

The proof evidence should be stored centrally and referenced by the resulting lifecycle events if promotion is approved.
