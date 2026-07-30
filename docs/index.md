# Project Jason

Jason is TeamAOT's governed operational platform and professional decision-support architecture.

Its purpose is to help AOT deliver dependable, secure, compliant, efficient, and consistent service while preserving human authority, client isolation, evidence, explainability, auditability, and institutional memory.

## Current build

Jason is in the CAP-001 implementation phase.

**CAP-001 — Professional Ticket Investigation** is a read-only, recommendation-only vertical slice that accepts a governed ticket-investigation request, establishes client context, collects and normalizes evidence, obtains structured reasoning, applies deterministic quality gates, and produces a technician-facing recommendation.

## Start here

1. Read the Manifesto and Constitution.
2. Review the Professional Operating Principles.
3. Review JKD-001 and JKD-002 for kernel service boundaries.
4. Review CAP-001 for the first complete capability contract.
5. Use J-402 when assessing whether a capability is ready for pilot.

## Engineering artifacts

The repository includes:

- versioned JSON Schema contracts;
- a provider-neutral internal OpenAPI specification;
- a read-only Python orchestration reference implementation;
- deterministic evidence and confidence quality gates;
- provider adapter protocols;
- unit, isolation, and end-to-end tests;
- GitHub Actions validation;
- Architecture Decision Records;
- a generated documentation site configuration.

## Governing boundary

Agents do not invoke or communicate with other agents directly. All coordination, permissions, context transfer, approvals, retries, timeouts, escalation, audit logging, and final response assembly pass through the central orchestration layer.
