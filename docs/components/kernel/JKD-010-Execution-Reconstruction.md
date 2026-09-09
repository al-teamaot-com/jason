# JKD-010: Execution Reconstruction

**Status:** Foundation
**Owner:** Jason Architecture Authority

## Purpose

Execution Reconstruction provides a deterministic, read-only view of a previously recorded orchestration execution from the durable event history established by ORCH-002.

It exists to answer what Jason observed during an execution without invoking a capability, changing provider state, mutating stored events, or attempting recovery.

## Constitutional alignment

ORCH-003 strengthens the following Jason principles:

- **Evidence before assertion:** reconstructed state is derived only from durable recorded events.
- **Explainability:** reviewers can inspect the ordered lifecycle that produced the final observed state.
- **Auditability:** execution, correlation, organization, principal, capability, stage, and timestamps remain visible.
- **Deterministic runtime:** identical durable event history produces the identical reconstructed view.
- **Separation of responsibilities:** the event store persists history; the reconstructor only reads and interprets that history.
- **Vendor independence:** reconstruction depends on the event-reader contract rather than SQLite or another storage technology.
- **Institutional memory:** operational history remains understandable after process restart, implementation changes, or contributor turnover.

## Read-only boundary

`ExecutionReconstructor` accepts an event reader that exposes `list_by_execution(execution_id)`.

The reconstructor may:

- read durable orchestration events;
- verify execution identity consistency;
- assemble an ordered timeline;
- report the final observed event and stage; and
- return immutable reconstruction contracts.

The reconstructor must never:

- invoke a capability;
- call a provider;
- retrieve a secret;
- append, update, delete, or replace an event;
- retry or resume an execution;
- infer an action that was not recorded; or
- treat reconstruction as proof that an external provider remains in the same state today.

## Reconstruction contract

A reconstructed execution contains:

- execution ID;
- correlation ID;
- organization ID;
- principal ID;
- capability name;
- final observed event type;
- final observed stage;
- event count;
- first observed timestamp;
- last observed timestamp; and
- the ordered event timeline.

The reconstruction intentionally reports **observed historical state**. It does not claim current provider state.

## Identity consistency

Every event in one reconstructed execution must agree on:

- execution ID;
- correlation ID;
- organization ID;
- principal ID; and
- capability name.

If durable history disagrees on any of these fields, reconstruction fails closed through `ExecutionReconstructionError`.

Missing execution history and invalid execution identifiers use the same canonical failure contract. Callers therefore do not need to distinguish storage-specific or implementation-specific exception types.

## Deterministic ordering

The durable event store supplies events in deterministic chronological order, with event ID acting as the stable tie-breaker where timestamps are identical.

The reconstructor preserves this order and does not reorder lifecycle events using inferred workflow semantics.

## Relationship to replay

Reconstruction is not replay.

Reconstruction means:

> Read the durable record and produce an immutable historical view.

Replay or recovery would mean:

> Use historical state to cause new runtime behavior.

ORCH-003 implements only the first concept.

Any future replay, recovery, resume, retry, or compensation capability must be introduced through a separate governed milestone with explicit policy, authority, idempotency, approval, and audit controls.

## Explicit exclusions

ORCH-003 does not provide:

- capability re-execution;
- provider verification;
- current-state reconciliation;
- automated replay;
- workflow recovery;
- resume behavior;
- retry scheduling;
- compensation or rollback;
- event mutation;
- event projections;
- distributed workflow state;
- autonomous planning; or
- direct agent invocation.

These exclusions preserve the constitutional boundary between historical evidence and operational authority.
