# Project Jason

Jason is TeamAOT's governed operational platform and professional decision-support architecture.

Its purpose is to help AOT deliver dependable, secure, compliant, efficient, and consistent service while preserving human authority, client isolation, evidence, explainability, auditability, and institutional memory.

## Current build

**Jason Kernel Foundation v0.1.0 is complete.**

The Kernel now provides governed identity and authority boundaries, execution policy, execution-provider registration, capability registration, and stateless governed capability resolution.

**CAP-001 — Professional Ticket Investigation** proves the first complete governed path. It validates execution context, resolves the canonical capability `operations.ticket.investigate`, discovers eligible providers, applies execution policy, receives a governed execution plan, and only then begins its read-only investigation workflow.

Denied or unresolved requests fail closed before evidence collection.

## Canonical sequence

```text
Capability Request
    |
    v
Execution Context Validation
    |
    v
Governed Capability Resolution
    |
    +--> Capability Registry
    +--> Execution Provider Registry
    +--> Execution Policy Engine
    |
    v
Governed Execution Plan
    |
    v
CAP-001 Investigation Workflow
```

## Start here

1. Read the Manifesto and Constitution.
2. Review the Professional Operating Principles.
3. Read [M-001 — Kernel Foundation](10-Milestones/M-001-Kernel-Foundation.md).
4. Review JKD-001 through JKD-007 for Kernel service boundaries.
5. Review CAP-001 for the first proven governed capability contract.
6. Use J-402 when assessing whether a capability is ready for pilot.

## Stable Kernel surface

The Version 0.1 stable Kernel API surface includes:

- execution context and authority decisions;
- capability definitions and queries;
- execution-provider definitions and candidate queries;
- execution requests, candidates, decisions, and plans;
- capability-resolution requests and results;
- data-handling policy and execution budgets.

Breaking changes require an ADR, affected-component updates, migration notes, tests, and a version increment.

## Validation baseline

The milestone baseline records:

- 79 passing Kernel tests;
- 21 passing CAP-001 tests;
- real CAP-001-to-Kernel integration tests;
- strict documentation build success;
- fail-closed authority and resolution behavior.

## Governing boundary

Agents do not invoke or communicate with other agents directly. All coordination, permissions, context transfer, approvals, retries, timeouts, escalation, audit logging, and final response assembly pass through the central orchestration layer.

The Kernel governs. Capabilities and approved providers perform business work. Providers never self-select, and policy remains authoritative.

## Next phase

Future work should focus on governed capability expansion and controlled pilot preparation. Live provider execution, production credentials, generalized agent runtime, and production operational approval remain deferred until separately designed, tested, and approved.
