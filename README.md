# Jason

Jason is TeamAOT's governed operational platform and professional decision-support architecture.

Its mission is to help TeamAOT deliver dependable, secure, compliant, efficient, and consistent service to its clients while preserving human authority, architectural discipline, explainability, auditability, organizational attention, and institutional memory.

## Source of Truth

This repository is the authoritative record for Project Jason.

Approved project documentation, architectural decisions, component charters, standards, roadmaps, implementation specifications, and operational guidance shall be maintained here rather than relying on conversation history or any individual contributor.

## Foundation

- [J-001 — The Jason Manifesto](01-Foundation/J-001-Manifesto.md)
- [J-002 — The Jason Constitution](01-Foundation/J-002-Constitution.md)
- [J-003 — Professional Operating Principles](01-Foundation/J-003-Professional-Operating-Principles.md)

## Kernel Foundation

The first governed Jason Kernel baseline is complete.

- [M-001 — Kernel Foundation](10-Milestones/M-001-Kernel-Foundation.md)
- [JKD-001 — Identity and Authority Service](03-Components/Kernel/JKD-001-Identity-and-Authority-Service.md)
- [JKD-002 — Evidence and Memory Service](03-Components/Kernel/JKD-002-Evidence-and-Memory-Service.md)
- [JKD-003 — Secrets Broker](03-Components/Kernel/JKD-003-Secrets-Broker.md)
- [JKD-004 — Execution Policy Engine](03-Components/Kernel/JKD-004-Execution-Policy-Engine.md)
- [JKD-005 — Execution Provider Registry](03-Components/Kernel/JKD-005-Execution-Provider-Registry.md)
- [JKD-006 — Capability Registry](03-Components/Kernel/JKD-006-Capability-Registry.md)
- [JKD-007 — Governed Capability Resolution Engine](03-Components/Kernel/JKD-007-Governed-Capability-Resolution-Engine.md)

The Version 0.1 stable Kernel API surface covers execution context, capability definitions, provider definitions, execution-policy contracts, governed resolution contracts, data-handling policy, and execution budgets. Breaking changes require an ADR, affected-component updates, migration notes, tests, and a version increment.

## Proven Vertical Slice

- [CAP-001 — Professional Ticket Investigation](03-Components/Capabilities/CAP-001-Professional-Ticket-Investigation.md)
- [CAP-001 Reference Implementation](implementation/cap-001/README.md)
- [Internal OpenAPI 0.1](implementation/openapi/jason-internal-v0.1.yaml)

CAP-001 Version 0.1 is read-only and recommendation-only. It now validates authority and resolves through the real Capability Registry, Execution Provider Registry, Execution Policy Engine, and Governed Capability Resolution Engine before evidence collection begins.

The proven path is:

```text
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

Denied or unresolved requests fail closed before evidence collection. CAP-001 does not select its own provider or bypass policy.

## Validation Baseline

At completion of M-001:

- 79 Kernel tests pass;
- 21 CAP-001 tests pass;
- real CAP-001-to-Kernel integration tests pass;
- authority denial and resolution denial fail closed;
- strict MkDocs validation passes;
- repository whitespace validation passes.

These results establish the foundation baseline; they do not constitute production pilot approval.

## Canonical Models

Canonical models define Jason's provider-neutral understanding of organizational reality.

Current models include:

- Organization Model
- State Model
- Object Model
- Relationship Model
- Event Model

See the [02-Canonical-Models](02-Canonical-Models/) directory for approved model documents.

## Engineering Governance

- [J-401 — Adaptive Build Method](04-Standards/J-401-Adaptive-Build-Method.md)
- [J-402 — Capability Definition of Done](04-Standards/J-402-Capability-Definition-of-Done.md)
- [J-403 — Canonical Sources and Generated Artifacts](04-Standards/J-403-Canonical-Sources-and-Generated-Artifacts.md)
- [ADR-001 — Build Jason Through Governed Vertical Slices](05-ADR/ADR-001-Vertical-Slice-First.md)

The project uses concrete, governed vertical slices before extracting broad frameworks. Architecture remains authoritative but evolves when implementation evidence reveals a durable lesson.

## Documentation Site

The repository includes a MkDocs Material configuration and generated documentation workspace. Build locally with the repository's documentation environment and strict validation:

```bash
.venv-docs/bin/python -m mkdocs build --strict
```

Canonical documentation is authored in the numbered repository directories. Generated `.build/` and `site/` outputs are disposable and must not be edited as authoritative sources.

## Capability Roadmap

- [Jason Capability Register](06-Roadmaps/Jason-Capability-Register.md)

The default question is now which governed capability should use the stable Kernel next, not which speculative Kernel component should be added.

## Documentation Structure

```text
01-Foundation/       Mission, Constitution, professional principles, governance
02-Canonical-Models/ Enduring provider-neutral organizational models
03-Components/       Kernel and capability specifications
04-Standards/        Architectural and engineering standards
05-ADR/              Architecture Decision Records
06-Roadmaps/         Capability registers and approved development roadmaps
07-Operations/       Operational procedures and runbooks
08-Session-Records/  Governed session records where retained
09-Architecture-Journal/ Architectural observations and bounded lessons
10-Milestones/       Completed milestone declarations and evidence
implementation/      Executable vertical slices, schemas, tests, adapters, and APIs
.github/workflows/   Continuous validation
99-Archive/          Superseded and historical records retained for continuity
```

## Governing Rules

If a proposed architectural decision cannot be justified by the Manifesto, Constitution, canonical models, or approved standards, the decision must be reconsidered or the foundation must be deliberately amended before proceeding.

Agents shall never invoke or communicate with other agents directly. All inter-agent coordination shall pass through the central orchestration layer.

The Kernel governs; capabilities and approved providers perform business work. Providers never self-select, policy remains authoritative, and missing authority or isolation context fails closed.

## Current Status

**Jason Kernel Foundation v0.1.0 is complete.**

The next phase is governed capability expansion and controlled pilot preparation on top of the stable Kernel surface. Live provider execution, production credentials, generalized agent runtime, and production operational approval remain deferred until separately designed, tested, and approved.
