# CAP-004 Provider-Neutral Operational Attention Briefing

**Status:** Foundation in progress

## Purpose

CAP-004 gives Jason a provider-neutral way to answer a higher-level operational question:

> What deserves human attention right now?

The capability is intentionally broader than a ticket queue, device alert list, or documentation exception report. It accepts normalized operational signals from governed provider integrations and produces a bounded, deterministic attention briefing.

## Architectural role

CAP-004 does not replace Autotask, IT Glue, Datto RMM, or other systems of record. Each provider remains authoritative for its own data and exposes governed read capabilities through Jason.

Provider-specific adapters convert relevant facts into the shared `OperationalSignal` contract. The briefing service then groups and ranks signals without requiring downstream consumers to know which product supplied them.

Initial provider sequence:

1. Autotask through the existing CAP-003 business-context foundation;
2. IT Glue read-only context;
3. Datto RMM read-only endpoint and alert context;
4. additional providers through the same signal contract.

## Capability contract

Canonical capability name:

`operations.attention.briefing`

An operational signal contains:

- source provider;
- organization boundary;
- durable subject type and identifier;
- human-readable subject name;
- category;
- normalized severity;
- concise summary;
- optional recommended action;
- optional evidence reference.

## Ranking model

The foundation uses deterministic ranking rather than an LLM to decide priority order. The score is based on:

- highest normalized severity;
- corroboration from multiple providers;
- bounded signal volume for the same subject.

This keeps prioritization inspectable and prevents free-form model output from silently becoming business authority.

The result is bounded to an operator-selected number of attention items, defaulting to ten.

## Governance boundaries

CAP-004 foundation rules:

- read-only inputs only;
- no provider-side changes;
- organization boundaries must match across every signal;
- evidence is referenced rather than copied into the briefing;
- signals from multiple providers may be correlated only through orchestrator-approved identity relationships;
- ranking is deterministic and explainable;
- agents do not communicate directly with one another; provider context enters through central orchestration and capability routing.

## Why this enables IT Glue and Datto RMM

IT Glue and Datto RMM should not each create a competing dashboard or AI workflow. Their integrations should contribute normalized signals such as documentation gaps, stale configuration records, endpoint health conditions, failed monitors, patch risk, or repeated alert patterns.

CAP-004 can then surface one company or endpoint as important because several independent systems agree that attention is warranted.

## Foundation acceptance criteria

The initial foundation is complete when:

- the provider-neutral signal contract is implemented;
- deterministic ranking is implemented and bounded;
- cross-organization input fails closed;
- multiple providers can contribute to one attention item;
- tests prove severity ranking and cross-provider corroboration;
- the roadmap and Command Center expose CAP-004 state.

## Next increment

Build the first Autotask signal producer using CAP-003 and live-read data, then validate a real operational briefing on the Jason host. After that, add IT Glue as the second provider against the same contract rather than creating a new briefing architecture.
