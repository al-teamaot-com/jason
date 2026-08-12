# ADR-0009 — Governed Capability Resolution Engine

**Status:** Accepted

## Context

Jason now has separate Kernel foundations for:

- capability identity and lifecycle;
- execution provider identity and technical eligibility;
- execution policy evaluation and governed execution planning.

These services answer different questions:

- What capability is being requested?
- Which providers may technically support it?
- Whether and how execution may proceed?

No existing Kernel component composes those answers into one governed
resolution result.

Without a dedicated resolution component, Orchestration or interfaces
would need to:

- interpret capability metadata;
- discover provider candidates;
- translate providers into execution candidates;
- invoke the Execution Policy Engine;
- reconcile capability, provider, and policy outcomes;
- construct denial, approval, or execution-plan results.

That would move governance logic into Orchestration and risk duplicating
decision behavior across interfaces and workflows.

## Decision

Jason will introduce a Kernel-owned Governed Capability Resolution Engine
under JKD-007.

The engine will compose the Capability Registry, Execution Provider
Registry, and Execution Policy Engine to produce a deterministic governed
resolution result.

The engine will not execute work.

## Consequences

### Positive

- governed resolution has one authoritative Kernel path;
- Orchestration remains focused on sequencing and state management;
- providers cannot select themselves;
- capability, provider, and policy decisions remain separate but composable;
- denial and approval outcomes become deterministic and auditable;
- execution plans are produced only after capability and provider checks.

### Negative

- the engine depends on stable contracts from three Kernel services;
- translation between registry records and policy candidates must be explicit;
- policy and provider evolution may require resolution-contract updates;
- dependency handling remains a separate concern.

## Rejected Alternatives

### Put resolution logic in Orchestration

Rejected because Orchestration should coordinate governed work, not become
the authority for capability meaning, provider eligibility, or policy.

### Let the Execution Policy Engine query registries directly

Rejected because policy evaluation should remain focused on policy and
should not own registry discovery or provider translation.

### Combine all registries and policy into one service

Rejected because capability identity, provider identity, and execution
policy evolve independently.

### Let providers declare themselves eligible at runtime

Rejected because technical availability does not establish authority,
approval, data handling, risk suitability, or policy compliance.

## Review Triggers

Review this decision when:

- resolution requires multi-capability dependency planning;
- provider selection requires optimization beyond deterministic filtering;
- policy contracts no longer represent required resolution outcomes;
- persistence or historical replay becomes necessary;
- dynamic provider discovery is introduced;
- a dependable approved platform can replace custom resolution behavior;
- the boundary between resolution and Orchestration becomes unclear.
