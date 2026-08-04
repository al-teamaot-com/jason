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
