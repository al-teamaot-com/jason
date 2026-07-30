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

Planned foundation documents:

- J-004 — Architecture Overview
- J-005 — Governance Model

## Canonical Models

Canonical models define Jason's provider-neutral understanding of organizational reality.

Current models include:

- Organization Model
- State Model
- Object Model
- Relationship Model
- Event Model

See the [02-Canonical-Models](02-Canonical-Models/) directory for approved model documents.

## Kernel Design

The Jason Kernel is being specified and built through working vertical slices.

- [JKD-001 — Identity and Authority Service](03-Components/Kernel/JKD-001-Identity-and-Authority-Service.md)
- [JKD-002 — Evidence and Memory Service](03-Components/Kernel/JKD-002-Evidence-and-Memory-Service.md)

## Active Vertical Slice

- [CAP-001 — Professional Ticket Investigation](03-Components/Capabilities/CAP-001-Professional-Ticket-Investigation.md)

CAP-001 is the first complete implementation contract. Version 0.1 is read-only and recommendation-only. It defines the invocation contract, evidence plan, workflow state machine, reasoning schema, deterministic quality gates, progressive-disclosure response, outcome feedback, security requirements, test fixtures, metrics, and implementation sequence.

The immediate engineering deliverable is the initial CAP-001 code skeleton and executable contract tests.

## Build Standards

- [J-401 — Adaptive Build Method](04-Standards/J-401-Adaptive-Build-Method.md)

The project uses concrete, governed vertical slices before extracting broad frameworks. Architecture remains authoritative but evolves when implementation evidence reveals a durable lesson.

## Capability Roadmap

- [Jason Capability Register](06-Roadmaps/Jason-Capability-Register.md)

The first active vertical slice is:

**CAP-001 — Professional Ticket Investigation**

Version 0.1 will establish identity and client context, preserve evidence, distinguish observation from inference, rank hypotheses, produce a technician-facing recommendation, and record the outcome and learning candidate.

## Documentation Structure

```text
01-Foundation/       Mission, Constitution, professional principles, governance
02-Canonical-Models/ Enduring provider-neutral organizational models
03-Components/       Kernel and capability specifications
04-Standards/        Architectural and engineering standards
05-ADR/              Architecture Decision Records
06-Roadmaps/         Capability registers and approved development roadmaps
07-Operations/       Operational procedures and runbooks
99-Archive/          Superseded and historical records retained for continuity
```

## Governing Rules

If a proposed architectural decision cannot be justified by the Manifesto, Constitution, canonical models, or approved standards, the decision must be reconsidered or the foundation must be deliberately amended before proceeding.

Agents shall never invoke or communicate with other agents directly. All inter-agent coordination shall pass through the central orchestration layer.

A working governed capability is more valuable than a perfect speculative framework. A broader framework should be extracted only after real capabilities reveal a stable common pattern.

## Current Status

The foundation and initial canonical architecture are sufficiently mature to begin implementation.

Project Jason is now in the **CAP-001 implementation phase**. The next work is to create machine-readable schemas, the read-only orchestrator state machine, provider adapter boundaries, and executable test fixtures defined by the CAP-001 contract.