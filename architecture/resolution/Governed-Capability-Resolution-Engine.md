# Governed Capability Resolution Engine

The Governed Capability Resolution Engine is the Kernel composition layer
that resolves invokable capability requests into governed execution
outcomes.

Primary references:

- `03-Components/Kernel/JKD-007-Governed-Capability-Resolution-Engine.md`
- `architecture/adr/ADR-0009-Governed-Capability-Resolution-Engine.md`
- `03-Components/Kernel/JKD-006-Capability-Registry.md`
- `03-Components/Kernel/JKD-005-Execution-Provider-Registry.md`
- `03-Components/Kernel/JKD-004-Execution-Policy-Engine.md`

The engine composes three existing Kernel authorities:

- the Capability Registry defines the requested capability;
- the Execution Provider Registry identifies technically eligible providers;
- the Execution Policy Engine determines whether and how execution may proceed.

The engine does not execute providers, grant authority, obtain approval,
manage secrets, or orchestrate capability dependencies.

## Resolution Boundary

The initial resolution path is:

```text
Capability Resolution Request
    |
    v
Capability Registry
    |
    v
Execution Provider Registry
    |
    v
Execution Policy Engine
    |
    v
Governed Resolution Result
```

Resolution fails closed when capability identity, lifecycle, execution mode,
isolation context, provider eligibility, authority, approval, data handling,
budget, or policy requirements are not satisfied.

Providers never select themselves.

The Execution Policy Engine remains authoritative for the final execution
outcome and any governed execution plan.

## Foundation Status

Architecture defined.

Kernel implementation not yet started.

The first implementation will be in-memory and deterministic. It will
include request and result contracts, capability resolution, provider
candidate discovery and translation, policy invocation, structured denial
outcomes, and focused Kernel tests.

Persistence, dependency graph planning, dynamic discovery, live execution,
retries, fallback execution, audit persistence, Orchestration integration,
and external API exposure remain deferred.
