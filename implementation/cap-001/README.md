# CAP-001 Reference Implementation

This directory contains the first executable vertical slice for **Professional Ticket Investigation**.

## Current contents

- Five JSON Schema contracts for requests, case packages, reasoning results, technician responses, and recorded outcomes.
- A read-only, auditable workflow state machine.
- Contract validation helpers and sanitized fixtures.
- Deterministic evidence, confidence, risk, and approval quality gates.
- Provider-neutral adapter protocols.
- Execution-context validation for capability, mode, expiry, requester grant, and client scope.
- Durable SQLite pilot storage for cases, reasoning results, outcomes, transitions, and audit events.
- A PostgreSQL production-target schema under `db/postgresql/`.
- End-to-end and adversarial client-isolation tests.

## Local validation

```bash
cd implementation/cap-001
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Design constraints

- Recommendation-only in Version 0.1.
- No connector may perform an operational change.
- Every workflow transition requires an audit reason and can be persisted.
- Invalid transitions fail closed.
- Execution contexts are short-lived, capability-bound, and client-scoped.
- Client context is mandatory and must remain unchanged throughout the case.
- Cross-client evidence is rejected and audited.
- Evidence content is data, never trusted as instruction.
- SQLite is for local and historical-ticket pilots; PostgreSQL is the production target.

## Next engineering increment

1. Add a provider-backed historical-ticket runner with sanitized Autotask-shaped data.
2. Define a credential-free Autotask read-only adapter and mapping contract.
3. Add resumable case loading and outcome recording services.
4. Add PostgreSQL row-level-security migration guidance.
5. Produce the first technician-facing Markdown response from a persisted case.
