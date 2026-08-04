# Capability Registry

The Capability Registry is the authoritative inventory of governed,
invokable capabilities known to the Jason Kernel.

Primary references:

- `03-Components/Kernel/JKD-006-Capability-Registry.md`
- `architecture/adr/ADR-0008-Central-Capability-Registry.md`
- `02-Architecture/J-101-Capability-Registry.md`
- `docs/architecture/JASON_CAPABILITY_CATALOG.md`
- `04-Standards/J-402-Capability-Definition-of-Done.md`

The registry distinguishes:

- architectural capability IDs such as `JAC-006`; and
- invokable canonical capability names such as `governance.action.evaluate`.

Architectural IDs describe enduring Jason capability classes.

Canonical capability names identify versioned operations requested through
Orchestration.

The first implementation will be intentionally in-memory and will contain
no provider calls, credentials, persistence, dynamic discovery, planning,
or execution.

## Foundation Status

Architecture defined.

The first in-memory Kernel foundation is implemented under:

`implementation/kernel/capabilities/`

It provides contracts, validation, registration, lookup, filtering, deterministic version resolution, governed lifecycle changes, and focused tests.

Persistence and runtime execution integration remain deferred.
