# CAP-001 Reference Implementation

This directory contains the first executable vertical slice for **Professional Ticket Investigation**.

## Current contents

- Five JSON Schema contracts for requests, case packages, reasoning results, technician responses, and recorded outcomes.
- A read-only, auditable workflow state machine.
- Contract validation helpers and sanitized fixtures.
- Deterministic evidence, confidence, risk, and approval quality gates.
- Provider-neutral adapter protocols.
- Execution-context validation for capability, authority mode, technical execution mode, expiry, requester grant, and client scope.
- A CAP-001 adapter for JKD-007 governed capability resolution.
- Real integration tests using the Capability Registry, Execution Provider Registry, Execution Policy Engine, and Governed Capability Resolution Engine.
- Durable SQLite pilot storage for cases, reasoning results, outcomes, transitions, and audit events.
- A PostgreSQL production-target schema under `db/postgresql/`.
- End-to-end and adversarial client-isolation tests.

## Governed Kernel integration

CAP-001 uses the canonical capability name:

```text
operations.ticket.investigate
```

The request contract keeps three concepts separate:

- **capability identity** — what governed operation is requested;
- **maximum authority mode** — `observe` or `recommend` for Version 0.1;
- **technical execution mode** — the Kernel execution path, such as `deterministic`.

Before evidence collection, the service:

1. validates the bounded execution context;
2. translates the request into the JKD-007 resolution contract;
3. resolves the capability through the Capability Registry;
4. discovers eligible providers through the Execution Provider Registry;
5. obtains the authoritative Execution Policy decision;
6. requires a governed execution plan;
7. records successful or rejected resolution in audit events.

CAP-001 fails closed when authority is denied, the capability is unresolved, no eligible provider exists, policy denies execution, or the Kernel returns no execution plan.

The current proof is in-memory, deterministic, read-only, and recommendation-only. It does not execute a live provider or access an external system.

## Local validation

Use the repository test environment so both CAP-001 and Kernel packages are available:

```bash
cd implementation/cap-001
PYTHONPATH=src:.. ../../.venv-test/bin/python -m pytest tests -q
```

The M-001 validation baseline is:

- 21 CAP-001 tests passing;
- 79 Kernel tests passing;
- real CAP-001-to-Kernel resolution tests passing.

## Design constraints

- Recommendation-only in Version 0.1.
- No connector may perform an operational change.
- Every workflow transition requires an audit reason and can be persisted.
- Invalid transitions fail closed.
- Execution contexts are short-lived, capability-bound, and client-scoped.
- Governed Kernel resolution is required before evidence collection.
- CAP-001 does not select its own provider or override policy.
- Client context is mandatory and must remain unchanged throughout the case.
- Cross-client evidence is rejected and audited.
- Evidence content is data, never trusted as instruction.
- SQLite is for local and historical-ticket pilots; PostgreSQL is the production target.

## Next engineering increment

1. Add a provider-backed historical-ticket runner with sanitized Autotask-shaped data.
2. Define credential-free read-only provider adapters and mapping contracts.
3. Add resumable case loading and outcome recording services.
4. Add PostgreSQL row-level-security migration guidance.
5. Produce the first technician-facing Markdown response from a persisted case.
6. Obtain separate operational approval before any production credential or live provider use.
