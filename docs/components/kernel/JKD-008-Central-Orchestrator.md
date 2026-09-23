# JKD-008: Central Orchestrator

**Status:** Foundation
**Owner:** Jason Architecture Authority

## Purpose

The Central Orchestrator is Jason's single runtime coordination boundary for named capability execution.

It composes existing Kernel services rather than duplicating them. It receives a structured request, asks the governed capability resolution engine for an approved execution plan, invokes only a registered implementation, records lifecycle events, and returns a structured result.

## Constitutional boundary

Agents must never invoke or communicate with other agents directly.

An agent may only:

- return a structured result to the Central Orchestrator; or
- request a named capability from the Central Orchestrator.

The orchestrator owns routing, context transfer, policy enforcement, approval state, retry and timeout coordination, escalation state, audit events, artifact references, and final response assembly.

## Reused Kernel services

ORCH-001 reuses:

- the Capability Registry;
- the Governed Capability Resolution Engine;
- the Execution Policy Engine;
- the Execution Provider Registry;
- existing execution budgets and data-handling contracts; and
- existing connector and capability implementations behind registered invocation bindings.

The orchestrator does not create parallel versions of these services.

## Request contract

Every request requires:

- execution ID;
- correlation ID;
- principal ID;
- organization ID;
- canonical capability name;
- requested execution mode;
- orchestration mode;
- authority state;
- approval state;
- risk classification;
- data-handling policy; and
- execution budget.

Optional artifacts are passed by reference. Large content is not copied through agents or embedded in orchestration events.

## Check-only mode

Check-only mode performs capability resolution and policy evaluation without invoking a capability implementation.

It must:

- emit correlated lifecycle events;
- return a validated or denied result;
- perform zero provider or capability calls;
- read no provider credential; and
- create no provider-side change.

## Capability invocation registry

The `CapabilityInvokerRegistry` maps one canonical capability name to one approved invocation implementation.

It:

- rejects duplicate registration;
- rejects unknown capabilities;
- rejects a mismatch between requested and resolved capability identity;
- exposes a read-only snapshot for inspection; and
- contains no provider selection, policy, secret, or agent-routing logic.

Provider and implementation selection remain governed by the Kernel resolution result. The registry only supplies the approved callable boundary for the resolved canonical capability.

## Audit lifecycle

The foundation emits events for:

- request received;
- capability resolved and policy decided;
- request terminated;
- check-only validated;
- capability invocation started;
- capability invocation failed; and
- capability invocation completed.

Failure responses are sanitized. Provider details and protected values belong only in approved correlated evidence stores, never in user-facing errors.

## Deferred-work coordination boundary

Operational playbooks may return persisted deferred states containing a `next_recheck_at` value. The Endpoint Availability Verification playbook is the first documented consumer of this pattern.

The Central Orchestrator remains the authority boundary for any future recheck execution. A scheduler may wake a workflow, but it must not create new authority. Before resumed work invokes a capability, Jason must rehydrate and validate the original execution/correlation identity, principal, organization/client, target, capability, policy, and terminal-state status.

Required scheduler properties include:

- durable storage across service restart;
- idempotent/deduplicated recheck identity;
- no execution before the requested time;
- cancellation/suppression after completion, escalation, retirement, or other terminal state;
- bounded retry/aging behavior defined by the calling playbook;
- lifecycle audit events;
- no cross-client or target substitution.

The scheduler remains separate from ORCH-001 and is tracked as `TODO-OPS-001`.

## Explicit exclusions

ORCH-001 does not yet provide:

- autonomous multi-step planning;
- dynamic workflow construction;
- direct agent invocation;
- provider HTTP clients;
- secrets retrieval;
- connector business logic;
- capability business logic;
- durable event storage;
- active cancellation; or
- production retry scheduling.

Those capabilities may be added only through later governed milestones without weakening the central boundary.
