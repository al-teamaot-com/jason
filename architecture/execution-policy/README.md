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
