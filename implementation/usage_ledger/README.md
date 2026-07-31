# Jason Model Usage Ledger

The Model Usage Ledger records every model invocation made through Jason's orchestration layer. Its purpose is accurate cost accounting, operational analysis, capacity planning, and optimization without allowing providers or agents to bypass governance.

## Governing principle

> Every model invocation must create an immutable usage entry. Provider-reported usage is authoritative. Estimated usage must be labeled as estimated. Retries, fallbacks, failures, streaming calls, background work, and local-model calls are recorded as separate attempts under one parent workflow.

## Required correlations

Each entry should be correlated to the identifiers available at execution time:

- workflow ID
- request ID
- attempt ID
- parent attempt ID when applicable
- ticket ID
- client ID
- organization ID
- capability name
- agent name
- provider
- model
- API project or routing profile

Client and organization identifiers must be validated by the orchestrator. Providers and agents may not choose their own accounting scope.

## Usage fields

- input tokens
- cached input tokens
- output tokens
- reasoning tokens
- total tokens
- provider-reported cost
- calculated cost
- currency
- request duration
- time to first token
- local evaluation duration
- request outcome
- finish reason
- usage source and confidence

## Usage source hierarchy

1. `provider_reported`: authoritative response or usage API data.
2. `local_runtime_reported`: native local runtime counts, such as Ollama prompt and evaluation counts.
3. `reconciled`: corrected from an authoritative provider usage or billing export.
4. `estimated`: tokenizer or text-based estimate when no authoritative usage is available.
5. `unknown`: request may have consumed resources, but reliable usage cannot be determined.

Estimates must never overwrite provider-reported values. Reconciliation creates an adjustment record rather than mutating history.

## Attempt model

One user-visible task may contain several billable attempts:

```text
Workflow WF-10082
  - Attempt 1: OpenAI, timeout, provider usage returned
  - Attempt 2: OpenRouter fallback, completed
  - Attempt 3: Ollama verification, completed
```

Every attempt receives its own ledger entry. Workflow totals are calculated from all entries, not only the successful attempt.

## Processing flow

```text
Orchestrator prepares model request
  -> usage context is bound to the request
  -> provider adapter executes the call
  -> adapter normalizes native usage
  -> ledger validates and appends the entry
  -> reconciliation job compares provider billing data
  -> reporting aggregates by workflow, ticket, client, capability, provider, and model
```

## Data integrity

- Entries are append-only.
- Request and attempt IDs are idempotency keys.
- Token counts cannot be negative.
- Total tokens must be consistent with the available component counts.
- Monetary values use decimal arithmetic.
- Raw provider response bodies are not stored in the ledger.
- Provider request IDs and evidence references are retained for audit.
- Prompts and responses are excluded by default to reduce privacy and client-separation risk.

## Initial implementation

The initial implementation provides:

- provider-neutral contracts
- an in-memory append-only ledger for testing and adapter development
- normalized adapters for OpenAI-style, OpenRouter-style, and Ollama-style usage payloads
- workflow and client aggregation
- reconciliation adjustment records
- validation and idempotency tests

A production deployment should replace the in-memory store with an append-only database table or event stream and protect it with organization-level row security.