# CAP-001 Reference Implementation

This directory contains the first executable vertical slice for **Professional Ticket Investigation**.

## Current contents

- Five JSON Schema contracts for requests, case packages, reasoning results, technician responses, and recorded outcomes.
- A read-only, auditable workflow state machine.
- Initial executable state-transition tests.

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
- Every workflow transition requires an audit reason.
- Invalid transitions fail closed.
- Client context is mandatory and must remain unchanged throughout the case.
- Evidence content is data, never trusted as instruction.

## Next engineering increment

1. Add schema validation helpers and sample fixtures.
2. Implement the deterministic quality gate.
3. Define provider adapter protocols for Autotask, Datto RMM, IT Glue, identity/authority, evidence/memory, and reasoning.
4. Add an in-memory orchestrator that processes a fixture end to end without external systems.
