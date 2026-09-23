# IT Glue and Autotask Provider-Read Acceptance — 2026-09-10

## Purpose

Record the first provider-backed acceptance of Jason's governed read path for IT Glue and Autotask. This is point-in-time evidence for the specifically exercised canonical capabilities only. It is not a production activation record and does not imply that every declared IT Glue or Autotask capability has been live-verified.

## Source identity

- Repository: `al-teamaot-com/jason`
- Branch under test: `feature/jason-provider-reads-itglue-autotask-20260909`
- Exact source commit: `1a8feac90ab77fbcc5596f3c36fe986dec543db1`
- Host worktree: isolated detached worktree; protected production worktree was not modified.

## Safety boundary

The acceptance was explicitly read-only. No production deployment, service restart, provider-data mutation, MCP capability activation, durable provider/capability lifecycle mutation, raw provider payload persistence, credential output, or hosted-model call occurred.

The IT Glue and Autotask AppRole bootstrap files were observed as root-owned mode `0600`. The live acceptance therefore ran with local root privilege solely to allow the existing Jason OpenBao read-only AppRole bootstrap credentials to be consumed by the existing secret resolver. Credential values were not read into operator-visible output or displayed.

## IT Glue result

- Result: **PASS**
- Canonical capability proven: `documentation.organization.search`
- Provider capability exercised: `it_glue.entity.query`
- Provider-backed: `true`
- Read-only: `true`
- Maximum returned records: `1`
- Collection count: `0`
- Hosted model used: `false`
- Durable activation mutated: `false`
- Credential boundary proven: OpenBao logical secret resolver
- Provider credentials printed: `false`
- Raw provider payload persisted: `false`
- Raw provider payload printed: `false`
- Observed at: `2026-09-10T09:44:19.936127+00:00`
- Sanitized response SHA-256: `ea288d6f1ee0839c5704f9cc4a1ae71377b849f345ede39d50dedf9a6bd9f070`
- Correlation ID: `itg-live-acceptance-root-20260910T0935Z`

Observed governed event sequence:

1. `orchestration.request.received`
2. `orchestration.capability.resolved`
3. `orchestration.capability.invoking`
4. `connector.requested`
5. `connector.completed`
6. `orchestration.capability.completed`

A zero-row result is acceptable for this acceptance because the objective was to prove authenticated provider contact, governed capability resolution, Central Orchestrator execution, bounded read behavior, secret isolation, and safe result handling. It does not prove that the supplied organization selector corresponds to an existing IT Glue organization.

## Autotask result

- Result: **PASS**
- Canonical capability proven: `service.ticket.search`
- Provider capability exercised: `autotask.ticket.search`
- Provider-backed: `true`
- Read-only: `true`
- Maximum returned records: `1`
- Collection count: `0`
- Hosted model used: `false`
- Durable activation mutated: `false`
- Credential boundary proven: OpenBao logical secret resolver
- Provider credentials printed: `false`
- Raw provider payload persisted: `false`
- Raw provider payload printed: `false`
- Observed at: `2026-09-10T09:44:21.126483+00:00`
- Sanitized response SHA-256: `ce86ec7f528ba2d598baf3c06e2a63c87670abd5d1e8b4ec91198054af1790f8`
- Correlation ID: `autotask-live-acceptance-root-20260910T0935Z`

Observed governed event sequence matched the IT Glue proof: request received, capability resolved, capability invoking, connector requested/completed, and capability completed.

A zero-row result is acceptable for this acceptance because the objective was the governed provider-read path rather than validation of a particular production ticket.

## Accepted conclusions

This evidence supports the following bounded conclusions:

- Jason can authenticate to the existing IT Glue read-only provider credential through OpenBao and complete `documentation.organization.search` through the Central Orchestrator.
- Jason can authenticate to the existing Autotask read-only provider credential through OpenBao and complete `service.ticket.search` through the Central Orchestrator.
- Both exercised paths remained deterministic and introduced no separately billed hosted-model execution.
- The acceptance harness preserved correlation and connector/orchestrator accountability without persisting raw provider records.
- Source-defined activation plans may now be produced for the specifically proven capabilities, but no durable activation was performed by this acceptance.

This evidence does **not** establish live acceptance of the other declared IT Glue or Autotask read capabilities. It also does not establish production runtime access to the root-owned bootstrap files under a non-root runtime identity; that is a separate deployment/composition concern and must be verified before production activation.

## Next safe work

Continue source-side work on provider-neutral canonical entity correlation and governed evidence caching. The cache must distinguish static/slow-changing/transactional/realtime evidence; realtime telemetry must bypass reusable cache, while static policy/document evidence may be reused only after current-principal authorization and source freshness/version validation. Cross-provider mappings must retain explicit-versus-inferred provenance and confidence. A later targeted real-record proof should correlate one Autotask record with IT Glue and/or Datto RMM under one correlation ID before production activation is considered.
