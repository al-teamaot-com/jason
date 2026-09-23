# ADR-001 — Build Jason Through Governed Vertical Slices

**Status:** Accepted  
**Date:** 2026-07-30  
**Decision owner:** Jason Architecture Authority

## Context

Jason has a mature constitutional and canonical foundation, but broad framework construction before operating evidence would create speculative abstractions and delay useful capability delivery.

## Decision

Jason will be implemented through complete governed vertical slices. Each slice must join identity, authority, evidence, policy, orchestration, communication, audit, and outcome feedback sufficiently to deliver one measurable organizational result.

CAP-001 — Professional Ticket Investigation is the first slice.

Shared services may be extracted only after at least one working capability demonstrates a stable reusable pattern. Foundational invariants, including client isolation and human authority, remain mandatory from the first implementation.

## Consequences

- Working capability evidence guides framework design.
- Early implementations may contain intentionally local abstractions.
- Reuse is earned through demonstrated recurrence rather than prediction.
- Every slice must remain replaceable, testable, explainable, and auditable.
- Architectural changes discovered during implementation require a versioned document or ADR update.

## Rejected alternatives

### Build the entire kernel before any capability

Rejected because it would optimize for architectural completeness without proving operational usefulness.

### Build vendor-specific automations directly

Rejected because it would couple Jason's identity and workflows to current providers.

### Begin with autonomous execution

Rejected because authority, evidence quality, and outcome verification must be demonstrated before execution authority expands.
