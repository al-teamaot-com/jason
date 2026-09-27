# Governed Reflection and Continuous Improvement

**Roadmap ID:** REFLECT-001
**Status:** Complete
**Priority:** P1
**Risk level:** Moderate
**Tracking issue:** GitHub issue #172 — Governed reflection and continuous-improvement loop for Jason

## Purpose

Jason should improve from real operating experience without becoming an uncontrolled self-modifying system or accumulating client/provider-specific exceptions.

The reflection capability should observe how governed executions actually perform, capture high-value signals from outcomes and user corrections, identify reusable improvement opportunities, and turn those opportunities into governed proposals that can be tested and approved before they affect production behavior.

This is a core architectural capability, not a one-off fix for any single provider or query.

## Initial motivating examples

The first production IT Glue + Autotask read tests exposed two examples of the behavior this roadmap item should address:

1. A natural organization lookup for `Hitt Electric` returned no result because the provider path behaved too much like an exact-name lookup, while the exact IT Glue organization name `Hitt Electric Corp.` succeeded. The reusable improvement is bounded normalized search resolution such as exact -> prefix -> contains/LIKE-style matching with ambiguity controls.
2. Answering a request for open Hitt Electric tickets required unnecessary paging through historical Autotask records. The reusable improvement is provider-neutral `open/unresolved` intent that can be translated into provider-side filtering instead of downloading broad history and filtering later.

These examples must not become hard-coded Hitt Electric or Autotask special cases. They are evidence for generic improvements in search resolution, semantic intent mapping, filter pushdown, evidence minimization, and execution efficiency.

## Reflection loop

A governed reflection loop should operate around normal executions:

1. **Observe** — capture execution facts such as requested intent, selected capability/provider, selectors, match counts, ambiguity, retries/fallbacks, latency, pagination, provider-call count, warnings, evidence volume, and completion/failure reason.
2. **Detect signals** — identify patterns such as exact-search misses followed by broader-search success, unnecessary provider calls, repeated fallbacks, excessive pagination for narrow requests, avoidable ambiguity, user corrections, or repeated failure modes.
3. **Record** — persist a bounded `ReflectionRecord` linked to the original correlation/audit evidence. Provider credentials, secret values, and credential-vault content must never be included.
4. **Propose** — create a candidate generic improvement, such as a search-resolution policy, canonical intent mapping, provider pushdown rule, correlation improvement, evidence-minimization rule, capability metadata change, or reusable construction guidance.
5. **Validate** — exercise the proposal against regression cases, existing governance rules, tenant/client isolation, authority boundaries, and relevant provider contracts.
6. **Approve** — require the appropriate human/governance boundary before a proposal changes production policy, orchestration logic, provider adapters, capability metadata, code, or configuration.
7. **Promote or reject** — record the decision and rationale. Accepted learnings become durable tests and documentation so the same problem does not have to be rediscovered.

## User corrections as high-value evidence

Explicit technician/user corrections should be treated as strong reflection signals. Examples include:

- "you should have done a LIKE search";
- "that took too many calls";
- "you already had enough evidence";
- "that answer used the wrong provider";
- "you should have filtered for open tickets".

A correction is not itself authorization to change production behavior. It is evidence that should be linked to the execution and considered for a reusable improvement proposal.

## Candidate data model

A future `ReflectionRecord` should be correlation-linked and may include:

- request/correlation identifier;
- normalized user intent;
- selected capability and provider;
- selector/filter strategy;
- result/match count;
- ambiguity outcome;
- retry/fallback sequence;
- provider-call count;
- pagination count;
- latency and execution budget;
- evidence volume;
- warnings/reason codes;
- user correction/feedback signal;
- candidate improvement category;
- lifecycle state;
- validation/regression references;
- approval/rejection record.

A candidate-improvement lifecycle should support at least:

`observed -> proposed -> tested -> approved -> promoted/rejected`

## Operational Resolution Memory extension

`TODO-OPS-001 — Operational Resolution Memory and case-based troubleshooting reuse` extends REFLECT-001 from learning about execution quality into learning from repeated operational incidents.

Reflection and Resolution Memory have different responsibilities:

- **Reflection** asks whether Jason's own search, orchestration, evidence, and reasoning path can be improved generically.
- **Resolution Memory** asks whether a new alert/ticket materially resembles prior incidents and whether verified historical outcomes can improve the order of diagnostics and recommendations.

A future `ResolutionRecord` should preserve a bounded incident signature and outcome trail, including relevant product/device/client context, symptoms, error codes, diagnostic evidence, actions attempted, which actions failed, which action resolved the issue, confirmed root cause when known, disruption/approval requirements, recency, source correlations, and technician confirmation.

Resolution Memory should support similarity ranking by current evidence, not keyword matching alone. It should favor repeated and recently verified patterns, reduce confidence when contradictory cases exist, and allow stale patterns to be deprecated. A single successful case is observation, not institutional truth.

The intended operational lifecycle is:

`observed -> repeated -> verified pattern -> playbook candidate -> promoted/deprecated`

Historical evidence must never create execution authority. If a prior modifying action repeatedly fixed comparable incidents, Jason may use that evidence to recommend or prioritize the action, but the current request still passes through the normal component/command classifier, approval policy, client scope, disruption policy, and Central Orchestrator.

The Datto EDR workstream provides an initial motivating example: a stale EDR version plus stopped `EndpointProtectionService` can be correlated with previous diagnostic/output evidence. If comparable cases show that a service-only attempt repeatedly failed while an approved EDR reinstall resolved the problem, Jason should use that history to choose a better first diagnostic/remediation path while still verifying current evidence and obtaining any required approval.

## Governance boundaries

Reflection must not create a second authority system. Existing Jason identity, authorization, capability, provider, approval, audit, and Central Orchestrator boundaries remain controlling.

The reflection capability must never autonomously:

- edit or deploy production code;
- broaden identity, tenant, client, or provider authority;
- create provider write capability;
- bypass approval requirements;
- expose or store secrets;
- convert one client/resource-specific observation into a global rule without bounded validation;
- add a second hosted model merely to restate or summarize deterministic execution telemetry.

Resolution Memory inherits all of those limits and additionally must not:

- treat one successful fix as a global playbook;
- erase or hide failed troubleshooting attempts;
- silently generalize client-specific exceptions;
- use historical success as approval for a current modifying/disruptive action;
- recommend a historical path without checking materially relevant current evidence;
- cross client/tenant boundaries when retrieving similar cases.

Where an improvement would materially change target, authority, action, risk, or meaning, normal Jason fail-closed and approval principles continue to apply.

## Cost and reasoning direction

Prefer deterministic reflection signals and metrics first. Examples include call count, pagination, exact-search miss followed by contains-search success, repeated fallback sequences, latency thresholds, evidence size, and user-correction events.

For Resolution Memory, prefer structured signatures and auditable ranking factors such as product/version, error code, alert type, service state, device class, client-scoped configuration, action outcome, recency, and technician confirmation before relying on free-form semantic similarity alone.

Optional model-assisted analysis may later be used offline or periodically when deterministic heuristics are insufficient, but ChatGPT Business should remain Jason's primary reasoning layer and a second hosted model should not be added merely for classification, summarization, or correlation that Jason can perform deterministically.

## Initial acceptance cases

REFLECT-001 should eventually prove at least the following:

- `Hitt Electric` can resolve `Hitt Electric Corp.` through bounded normalized matching without requiring the user to know the exact provider record name.
- Ambiguous partial organization names still return bounded candidates or fail safely rather than silently selecting the wrong organization.
- `open tickets for Hitt Electric` resolves the organization/company relationship and pushes an open/unresolved filter to Autotask without paging through large historical ticket sets.
- Repeated inefficient paths and explicit user corrections produce visible reflection candidates.
- An accepted learning is represented by durable regression coverage and documentation.
- No reflection record or accepted learning can grant itself provider access, write authority, tenant scope, or client scope.

Resolution Memory should eventually prove at least the following:

- repeated alerts/tickets with materially similar evidence can retrieve prior successful and failed cases;
- ranking considers similarity, recency, evidence quality, and verified outcomes;
- a known failed step is not repeatedly chosen first when stronger comparable evidence exists;
- a historically successful modifying action still triggers current per-run approval when required;
- contradictory outcomes lower confidence and are visible to the technician;
- client-specific exceptions remain client-scoped;
- repeated verified outcomes can be proposed for playbook promotion but cannot promote themselves.

## Near-term construction direction

The first REFLECT-001 implementation slice should remain small and deterministic:

1. define the `ReflectionRecord` schema and lifecycle;
2. collect correlation-linked execution metrics from the Central Orchestrator/provider-read path;
3. capture explicit user-correction feedback as an auditable signal;
4. implement a few deterministic candidate detectors, starting with search-broadening success and excessive provider-call/pagination patterns;
5. surface candidate improvements for human review;
6. connect accepted candidates to regression-harness cases;
7. do not enable autonomous production self-editing.

After that foundation is stable, the first Resolution Memory slice should:

1. define a provider-neutral `ResolutionRecord` and normalized issue signature;
2. ingest only verified/correlation-linked ticket, alert, diagnostic, job-output, and technician-outcome evidence;
3. keep success and failure steps in the same historical record;
4. implement client-isolated similarity search and deterministic ranking factors;
5. expose similar-case evidence to Jason's normal reasoning path;
6. record current case outcome and technician confirmation;
7. propose, but never self-promote, repeated verified patterns into playbooks.

## Relationship to current architecture

Reflection is subordinate to Jason's existing provider-neutral capability/resource model. It should improve the generic construction paths Jason already uses rather than creating bespoke scripts or locked-in workflows.

Resolution Memory is likewise an evidence/reasoning capability, not an execution path. It may influence which diagnostic Jason chooses to try first, but the Central Orchestrator, capability registry, command/component classification, approvals, provider boundaries, and audit chain remain authoritative.

The Central Orchestrator remains the sole coordination/execution authority. Reflection observes and evaluates executions; Resolution Memory retrieves historical evidence; neither becomes a parallel execution path.

## Decision owner

Jason Governance Authority / Technology Steward.

## Review trigger

Begin REFLECT-001 design after the current governed provider-read foundation is stable enough to provide reliable execution telemetry, and before broad provider expansion makes repeated inefficiencies expensive to rediscover manually.

Begin Resolution Memory design once governed ticket/alert reads, Datto job/output correlation, and reliable resolution outcomes are stable enough to distinguish verified repeated patterns from anecdotal fixes.

## Implemented production state — 2026-09-27

REFLECT-001 is implemented as a provider-neutral governed learning layer subordinate to the Central Orchestrator. The production contract is:

`governed execution -> bounded terminal telemetry -> ReflectionRecord -> deterministic signal -> improvement candidate -> human proposal -> durable CI regression -> human approval -> reviewed source/PR -> controlled release promotion`

The reflection subsystem does **not** edit source, policy, capabilities, provider mappings, authority, or production configuration. `promoted` is lifecycle evidence that a separately reviewed release completed; it is not an execution path.

### Production observation path

The Central Orchestrator emits bounded reflection telemetry with completed capability audit events. The telemetry contains strategy labels, result/candidate counts, provider-call count, pagination/fallback count, evidence count, bounded warning codes, and latency. Raw prompts, request arguments, provider response bodies, client content, and credentials are not copied into Reflection Memory. A collecting audit wrapper writes the primary orchestration event first and then derives the reflection record. Reflection failure cannot rewrite a provider outcome.

Deterministic detectors currently cover:

- exact-search miss followed by bounded broader-search success;
- excessive pagination;
- excessive provider calls;
- repeated fallbacks;
- authenticated human correction.

Repeated detections reuse one candidate key and accumulate source evidence rather than generating one-off provider/client hacks.

### Authenticated correction boundary

A technician correction stores only a bounded correction **category**, authenticated principal identity, organization scope, and linkage to the original/derived reflection records. Free-form correction text is not persisted by REFLECT-001. A correction can create or reinforce an observed candidate; it cannot approve, test, promote, or change production behavior.

### Review and regression boundary

Candidate lifecycle is enforced as:

`observed -> proposed -> tested -> approved -> promoted`

with rejection available from review stages. The actor/evidence contract is intentionally asymmetric:

- **proposed** — human governance actor;
- **tested** — CI actor only, and only after a durable passing regression record exists;
- **approved** — human governance actor only, and passing regression evidence must already exist;
- **promoted** — controlled release actor only after approval.

The runtime review surface exposes human `propose`, `approve`, and `reject` only. It does not expose a human/self-service `test` or `promote` operation. Jason therefore cannot convert its own observation into production behavior. Accepted learnings are represented by source-controlled regression cases in `implementation/reflection/regression_cases.json` and required CI tests.

### Initial accepted generic improvements

The two original motivating examples are now deterministic generic policies, not client-specific exceptions:

1. **Bounded organization-name resolution.** IT Glue organization lookup uses exact provider filtering first. If that produces no exact result, Jason may make one bounded collection read and apply normalized prefix/contains matching locally. Exactly one match may resolve; multiple matches fail closed. This allows a request such as `Hitt Electric` to resolve `Hitt Electric Corp.` without silently selecting among ambiguous candidates.
2. **Open/unresolved Autotask ticket pushdown.** Canonical `status=open|unresolved` becomes an internal semantic operator. Before ticket retrieval, the Autotask connector reads the live status picklist, resolves terminal labels such as Complete/Closed/Cancelled, and replaces the internal intent with provider-side status exclusions. The internal operator never reaches Autotask, and Jason does not need to page broad historical ticket sets merely to discard terminal records.

Both paths emit bounded reflection telemetry so future inefficiency remains observable.

### Visibility

`operations.reflection.summary`, `operations.reflection.candidate.search`, and `operations.reflection.candidate.read` expose evidence-only review data through the normal provider-neutral resource model. Correction/review mutations are governed local capabilities but are intentionally excluded from generic planner discovery.

Prometheus/Grafana source for aggregate Reflection availability, record count, candidate lifecycle counts, authenticated-correction count, signal counts, and CI regression outcomes is implemented and merged. Candidate text, source record IDs, principals, clients, and provider records are not exported as metric labels. Production activation of the new exporter/dashboard panels remains a privileged observability operation tracked in GitHub issue #455 because the immutable release and systemd installation boundary is root-owned and the authorized remote-command policy blocks sudo. REFLECT-001 runtime functionality and governed candidate retrieval are already live; dashboard state grants no authority.

### Authority invariant

Every reflection projection carries `grants_authority=false`; candidate projections additionally state `can_change_production=false`. Current Jason governance, protected source review, and controlled release remain the only path by which an accepted improvement can affect production.
