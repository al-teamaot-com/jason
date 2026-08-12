# JKD-009: Durable Orchestration Event Store

**Status:** Foundation
**Owner:** Jason Architecture Authority

## Purpose

ORCH-002 provides Jason with a durable, append-only record of Central Orchestrator lifecycle events.

The event store preserves what the orchestrator did, under which identity and organization context, for which capability, and in which lifecycle stage. It exists to support auditability, explainability, recovery, and institutional memory without moving business logic into persistence.

## Constitutional alignment

This component implements the following Jason principles:

- **Evidence before assertion:** lifecycle claims are backed by stored events.
- **Explainability:** each execution can be reconstructed from ordered events.
- **Auditability:** events preserve execution, correlation, identity, organization, capability, stage, and timestamp context.
- **Separation of responsibilities:** the orchestrator emits events; the store persists and retrieves them.
- **Vendor independence:** the event contract is independent of SQLite, PostgreSQL, Python, or any specific storage technology.
- **Institutional memory:** runtime history survives process restart and contributor turnover.

## Event contract

`OrchestrationEvent` is an immutable, schema-versioned record containing:

- event ID;
- schema version;
- event type;
- execution ID;
- correlation ID;
- organization ID;
- principal ID;
- canonical capability name;
- lifecycle stage;
- immutable JSON-compatible payload; and
- timezone-aware occurrence timestamp.

The payload is copied and normalized when the event is created. Later mutation of the caller's source object cannot alter the event.

## Storage boundary

`OrchestrationEventStore` exposes only:

- append one immutable event;
- retrieve one event by event ID;
- list events by execution ID; and
- list events by correlation ID.

The canonical boundary does not expose update, replace, delete, or truncate operations.

## SQLite adapter

`SQLiteOrchestrationEventStore` is the local pilot adapter.

It:

- creates an append-only orchestration event table;
- rejects duplicate event IDs;
- stores JSON payloads deterministically;
- orders retrieval by occurrence time and event ID;
- persists across process restart;
- protects file-backed databases with mode `0600`; and
- implements the existing `OrchestrationAuditSink` interface used by the Central Orchestrator.

SQLite is an implementation adapter, not an architectural dependency. A future PostgreSQL or event-stream adapter must preserve the same event contract and append-only behavior.

## Central Orchestrator integration

The Central Orchestrator continues to depend only on `OrchestrationAuditSink`.

The SQLite adapter translates each emitted lifecycle event into the canonical immutable event contract. The orchestrator does not import SQLite, issue SQL, manage database paths, or know which durable implementation is active.

The following lifecycle events are durably recorded when emitted:

- request received;
- capability resolved and policy decided;
- request terminated;
- check-only validated;
- capability invocation started;
- capability invocation failed; and
- capability invocation completed.

Check-only history explicitly records that no provider was invoked.

## Failure behavior

The store fails closed when:

- required event fields are empty;
- a timestamp is not timezone-aware;
- a payload cannot be normalized as JSON-compatible data; or
- an event ID already exists.

The store does not silently replace or merge existing events.

## Explicit exclusions

ORCH-002 does not provide:

- workflow replay or automatic re-execution;
- event-driven subscriptions;
- message queues or distributed streaming;
- projections or analytics;
- event mutation or deletion;
- scheduled retries;
- active cancellation;
- autonomous planning; or
- connector, provider, secret, or agent-routing logic.

Those capabilities require separate governed milestones and must not weaken the append-only evidence boundary.
