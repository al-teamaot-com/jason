# Execution Policy Engine

The Execution Policy Engine is Jason's provider-neutral decision service for selecting how an authorized capability should execute.

It evaluates:

- deterministic execution;
- local AI;
- hosted AI;
- human approval;
- human execution;
- denial.

It also produces versioned execution-cost estimates and completed Cost Records.

Primary documents:

- `03-Components/Kernel/JKD-004-Execution-Policy-Engine.md`
- `architecture/adr/ADR-0006-Execution-Policy-Engine.md`

The first implementation should remain in-memory and policy-driven until the contracts and operating assumptions are validated.

## Execution Provider Registry

`JKD-005 — Execution Provider Registry` supplies normalized and governed
candidate-provider records to the Execution Policy Engine.

The relationship is:

```text
Capability Registry
    |
    v
Execution Provider Registry
    |
    v
Execution Policy Engine
    |
    v
Execution Plan
```

The provider registry answers who may be considered.

The Execution Policy Engine answers whether and how a candidate may be
used.
