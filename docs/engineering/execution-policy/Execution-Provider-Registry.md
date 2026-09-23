# Execution Provider Registry

The Execution Provider Registry is the authoritative inventory of
governed execution providers available to Jason.

Primary references:

- `03-Components/Kernel/JKD-005-Execution-Provider-Registry.md`
- `architecture/adr/ADR-0007-Central-Execution-Provider-Registry.md`
- `03-Components/Kernel/JKD-004-Execution-Policy-Engine.md`

The first implementation is intentionally in-memory and contains no
credentials, live provider calls, persistence, or uncontrolled
discovery.

## Foundation Status

The first in-memory registry foundation is implemented under:

`implementation/kernel/execution_providers/`

It provides contracts, registry operations, candidate filtering,
governance validation, and focused tests.

Provider selection is not yet wired into the Execution Policy Engine.
