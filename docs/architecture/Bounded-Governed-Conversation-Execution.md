# Bounded Governed Conversation Execution

## Purpose

Jason must treat a conversational turn as a governed transaction rather than a chain of unrelated backend timeouts. The user-facing experience must not be determined by the timeout behavior of an LLM, connector, or execution provider.

## Observed failure class

A conversational read can currently spend substantial time in multiple sequential reasoning and provider operations. A slow reasoning call or provider invocation can consume the entire request path and surface as a generic transport failure to Teams.

The triggering endpoint example is regression evidence only. This design applies to every conversational request, capability, provider, and reasoning backend.

## Required invariants

1. The conversation model interprets language; it does not repeatedly drive deterministic control flow.
2. Once the information need, target, and authority are sufficiently structured, the Central Orchestrator owns execution.
3. Every conversational turn has an explicit overall execution budget.
4. Every reasoning call and capability invocation receives a bounded sub-budget derived from the remaining turn budget.
5. Provider and capability failures are typed and machine-actionable internally.
6. A backend timeout must not become a raw transport failure at a human-facing interface.
7. Retry, alternate-provider selection, partial-result handling, and graceful failure are deterministic orchestration concerns unless semantic judgment is genuinely required.
8. Evidence already obtained must not be discarded merely because a later provider or reasoning step fails.
9. Provider limit metadata is operational policy, not documentation only. `maximum_execution_seconds` must be enforced by the execution path or by a provider transport contract that is itself bounded and observable.
10. Cost optimization remains a backend concern. A cheaper/slower reasoning path may be attempted first when the remaining turn budget permits safe fallback.

## Responsibility split

### Conversation reasoning

Reasoning is used to determine:

- the user's information need;
- the target or subject;
- requested authority/action class;
- genuine semantic ambiguity;
- natural final presentation when deterministic rendering is insufficient.

### Central Orchestrator

The orchestrator owns:

- capability discovery and selection from governed registry truth;
- authorization and policy gates;
- provider selection;
- argument grounding from declared capability contracts;
- deadlines and remaining-budget accounting;
- retries and provider fallback;
- evidence accumulation;
- typed failure handling;
- audit and provenance;
- final outcome classification.

### Providers/connectors

Providers expose governed operations and must return either evidence/results or typed failures within their assigned execution deadline. They do not own conversational semantics.

## Failure taxonomy

At minimum, execution failures should be distinguishable as:

- timeout;
- unavailable;
- authentication/credential failure;
- authorization/permission failure;
- rate limited;
- resource not found;
- invalid request or contract mismatch;
- upstream server failure;
- network/transport failure;
- internal provider implementation failure.

Human-facing messages may intentionally collapse some of these categories, but Jason's orchestration layer must retain the typed internal cause.

## Turn-budget model

A turn budget is an orchestration contract. It should include:

- total permitted elapsed time;
- reasoning budget;
- evidence-acquisition budget;
- provider-attempt budget;
- synthesis/final-response reserve.

Sub-operations may consume less than their allowance. No sub-operation may silently expand its budget. A retry or stronger-model escalation is permitted only when sufficient turn budget remains.

## Existing architectural support

Jason's execution-provider contract already includes `ProviderLimits.maximum_execution_seconds`. The bounded-execution workstream should reuse that existing structured metadata rather than inventing a second provider timeout source of truth.

## Initial implementation sequence

1. Introduce provider-neutral typed invocation failures.
2. Propagate provider/capability execution deadlines through the invocation contract.
3. Enforce declared execution limits at the provider transport boundary.
4. Preserve typed failures in orchestration audit events and results.
5. Add a conversation-turn budget that allocates bounded reasoning and evidence-acquisition time.
6. Prevent failed evidence acquisition from triggering an unbounded large-model recovery call.
7. Add deterministic graceful-response paths for exhausted budgets and typed provider failures.
8. Add model escalation only as a bounded backend optimization.

## Acceptance criteria

- A slow provider cannot hold a conversational turn beyond its governed execution deadline.
- A slow reasoning backend cannot surface a raw transport failure to Teams.
- The same execution-budget behavior works across unrelated capabilities and providers.
- No question-specific, provider-specific, or phrase-specific semantic mappings are introduced.
- Existing provider limits remain authoritative and are actually enforced.
- Typed failures are recorded in the audit trail without exposing secrets.
- A routine factual read normally requires one semantic interpretation stage before deterministic orchestration begins.
