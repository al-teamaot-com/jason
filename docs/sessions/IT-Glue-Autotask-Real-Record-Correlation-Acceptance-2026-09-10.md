# IT Glue + Autotask + Datto RMM Real-Record Correlation Acceptance — 2026-09-10

## Purpose

Record the bounded live acceptance proving that Jason can start from a real Autotask ticket, remain read-only, correlate provider identity across the governed provider-neutral layer, and preserve ambiguity instead of guessing when endpoint evidence is insufficient.

This proof did not deploy production code, restart services, activate MCP capabilities, modify provider data, modify credential files, print raw provider records, or invoke a hosted model.

## Source identity

Acceptance ran from:

- branch: `feature/jason-provider-reads-itglue-autotask-20260909`
- commit: `bdaea309cba4ee6842e0c0a3c36505766e806104`
- isolated detached worktree: `/home/al/projects/jason-cross-provider-live-20260910T150746Z`

The fetched commit matched the expected source identity before any provider read.

## Credential boundary

The existing read-only AppRole bootstrap files for Autotask, IT Glue, and Datto RMM were verified as root-owned mode `0600` regular files. Credential contents were not displayed.

The live proof used the existing provider-specific OpenBao read-only identities. Provider identities remained separate.

## Bounded sampling

Jason sampled at most 25 Autotask tickets and selected one deterministic acceptance candidate without printing or persisting the ticket identifier.

Observed sanitized sampling facts:

- candidate count: 25
- configuration-linked candidates: 2
- selection basis: greatest durable provider ID among configuration-linked candidates
- provider order was not treated as semantic identity
- selected ticket identifier was neither printed nor persisted
- raw provider payload was neither printed nor persisted
- hosted-model usage: none
- Jason-side hosted-model cost: `$0`

## Governed provider reads

The proof executed the following read-only capabilities under one correlation ID:

- Autotask `service.ticket.search`
- Autotask `service.company.read`
- IT Glue `documentation.organization.search`
- Autotask `service.configuration.read`
- IT Glue `documentation.configuration.search`
- Datto RMM `endpoint.device.search`

Provider responses were retained only in process memory for correlation. Durable evidence contains hashes and sanitized stage metadata rather than raw records or provider identifiers.

## Correlation results

### Autotask ticket seed

Status: **proven**.

The bounded ticket selector resolved to exactly one Autotask ticket.

### Autotask company to IT Glue organization

Status: **proven**.

The ticket supplied an explicit Autotask company relationship. Jason read that company and correlated it to exactly one IT Glue organization using exact normalized organization-name corroboration.

The canonical organization mapping retained:

- Autotask company mapping: explicit, verified, confidence `1.0`
- IT Glue organization mapping: corroborated, confidence `0.95`
- provenance showing the provider fields and exact-normalized-name match

This is a successful real-record cross-provider correlation from Autotask to IT Glue.

### Ticket to Autotask configuration item

Status: **proven**.

The ticket contained an explicit configuration relationship and Jason read the referenced Autotask configuration item.

### Autotask configuration to IT Glue configuration

Status: **ambiguous**.

Two IT Glue configuration candidates matched the provider-reported name. Jason did not select either candidate and did not promote either to canonical endpoint identity.

This is the required fail-closed behavior. Duplicate documentation records are evidence of ambiguity, not permission to choose the first result.

### Autotask configuration to Datto RMM endpoint

Status: **not found**.

No Datto RMM endpoint matched the provider-reported Autotask configuration hostname in the bounded governed search. Jason did not manufacture a hostname, infer a device prefix, or create a mapping without provider evidence.

## Accountability and cost

The complete proof remained under correlation ID:

`cross-provider-live-20260910T150746Z`

Sanitized orchestration evidence retained request/resolution/invocation/completion events across the provider reads. Connector request/completion events were also recorded without credentials or raw payloads.

Model accounting for the complete proof:

- hosted model used: false
- hosted-model input tokens: 0
- hosted-model output tokens: 0
- hosted-model cost: `$0`

This confirms the intended low-cost architecture: deterministic Jason provider work beneath ChatGPT Business reasoning rather than a second hosted model for provider routing/correlation.

## Acceptance outcome

`REAL_RECORD_CORRELATION=PASS`

The live proof establishes the required real-record cross-provider behavior because at least one peer-provider relationship was unambiguously proven: Autotask company → IT Glue organization.

The unresolved endpoint stages are not acceptance failures. They demonstrate that Jason preserves ambiguity and absence rather than turning weak evidence into false certainty.

## Production boundary

This acceptance does **not** authorize or imply production activation.

Before production provider reads are enabled through the runtime/MCP path, the remaining governed checkpoint is:

1. verify the non-root runtime credential staging preflight against the final feature head;
2. obtain explicit production approval;
3. stage provider read-only runtime credentials without changing bootstrap ownership/mode;
4. render and recreate only `jason-runtime` with the provider-specific read-only mounts;
5. verify runtime health and provider read behavior;
6. keep durable capability activation, MCP exposure, PR readiness/merge, and any write capability as separate explicit decisions.

Endpoint correlation should continue to prefer stronger deterministic evidence such as explicit configured mappings and corroborating durable attributes. Ambiguous duplicate IT Glue configurations and absent Datto matches must remain unresolved unless additional governed evidence legitimately distinguishes them.
