# JKD-011: Interrupted Execution Assessment

**Status:** Foundation
**Owner:** Jason Architecture Authority

## Purpose

The Interrupted Execution Assessment layer determines whether durable orchestration history has reached a canonical terminal event or ends in a nonterminal observed state.

It builds on `ExecutionReconstructor` rather than interpreting durable events independently. This preserves one canonical read path from persisted evidence to higher-level operational understanding.

## Constitutional alignment

ORCH-004 strengthens the following Jason principles:

- **Evidence before assertion:** assessment is based only on reconstructed durable events.
- **Explainability:** the classification identifies the final observed event and stage that produced the result.
- **Auditability:** execution, correlation, organization, principal, capability, event count, and final observed time remain part of the assessment context.
- **Deterministic runtime:** identical durable history produces the same assessment.
- **Separation of responsibilities:** reconstruction interprets ordered event history; assessment classifies only the reconstructed final observed state.
- **Vendor independence:** assessment depends on reconstruction contracts rather than SQLite or provider APIs.
- **Institutional memory:** interrupted work can be identified after process restart or contributor turnover without relying on transient runtime memory.
- **Least authority:** assessment grants no permission to retry, resume, replay, cancel, compensate, or contact a provider.

## Canonical terminal events

The Central Orchestrator currently records four canonical terminal lifecycle events:

- `orchestration.request.terminated`
- `orchestration.check_only.validated`
- `orchestration.capability.failed`
- `orchestration.capability.completed`

An execution whose reconstructed final observed event is one of these events is classified as `terminal`.

Any execution with valid reconstructed history whose final observed event is not one of these terminal events is classified as `interrupted`.

## Assessment contract

`InterruptedExecutionAssessor` accepts an execution ID and delegates all history reading and identity validation to `ExecutionReconstructor`.

It returns an immutable `InterruptedExecutionAssessment` containing:

- execution ID;
- correlation ID;
- organization ID;
- principal ID;
- capability name;
- assessment status;
- final observed event type;
- final observed stage;
- final observed timestamp;
- event count;
- `is_terminal`; and
- `is_interrupted`.

The assessment does not include an inferred provider outcome, a retry recommendation, or a recovery command.

## Assessment is not provider-state verification

An interrupted classification means only that Jason's durable orchestration history ends without a recorded canonical terminal event.

It does **not** mean that:

- the provider operation failed;
- the provider operation succeeded;
- the provider operation is still running;
- the provider state is unknown because of a timeout; or
- the capability is safe to execute again.

Those conclusions require separate governed evidence and, where appropriate, provider-specific verification through approved capabilities.

## No timeout inference

ORCH-004 does not introduce elapsed-time thresholds or stale-execution timers.

A nonterminal execution is classified from recorded lifecycle evidence alone. Time-based recovery or escalation policy may be introduced only through a later governed milestone with explicit policy ownership and audit requirements.

## Failure behavior

Assessment reuses the reconstruction failure contract.

If execution history is missing, malformed, or internally inconsistent, the underlying `ExecutionReconstructionError` is propagated. The assessor does not downgrade invalid evidence into an interrupted classification.

## Explicit exclusions

ORCH-004 does not provide:

- provider-state verification;
- current-state reconciliation;
- capability retry;
- capability resume;
- automatic replay;
- workflow recovery;
- retry scheduling;
- elapsed-time interruption detection;
- cancellation;
- compensation or rollback;
- event mutation;
- provider HTTP clients;
- secrets retrieval;
- connector business logic;
- autonomous planning; or
- direct agent invocation.

Any future recovery capability must consume this assessment as evidence while passing through normal orchestration, policy, approval, and audit boundaries. It must never treat `interrupted` as implicit authority to perform another provider action.
