# Project Jason Documentation

Project Jason is TeamAOT's governed operational platform and professional decision-support architecture.

This `docs/` tree is the single human-facing documentation control plane for Jason. A future human or AI session should begin here rather than relying on conversation history, remembered deployment details, or historical repository layout.

## Start here

1. **Mandatory fundamentals baseline:** [`control/JASON-FUNDAMENTALS.md`](control/JASON-FUNDAMENTALS.md).
2. **Current resume point:** [`control/CURRENT.md`](control/CURRENT.md).
3. **How to create/extend Jason component classes:** [`control/EXTENSION-CONSTRUCTION-MAP.md`](control/EXTENSION-CONSTRUCTION-MAP.md).
4. **Where authoritative knowledge lives:** [`control/DOCUMENTATION-REGISTER.md`](control/DOCUMENTATION-REGISTER.md).
5. **Standard Documentation Policy:** [`control/STANDARD-DOCUMENTATION-POLICY.md`](control/STANDARD-DOCUMENTATION-POLICY.md).
6. **How to write/update Jason documentation:** [`control/HOW-TO-DOCUMENT-JASON.md`](control/HOW-TO-DOCUMENT-JASON.md).
7. **Implementation-local documentation index:** [`control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`](control/IMPLEMENTATION-DOCUMENTATION-INDEX.md).
8. **Known reconciliation issues:** [`control/DOCUMENTATION-MIGRATION-ISSUES.md`](control/DOCUMENTATION-MIGRATION-ISSUES.md).
9. **Governing documentation standard (J-404):** [`standards/J-404-Documentation-Governance-and-Continuity.md`](standards/J-404-Documentation-Governance-and-Continuity.md).
10. **Handoff template:** [`control/HANDOFF-TEMPLATE.md`](control/HANDOFF-TEMPLATE.md).
11. **General durable-document template:** [`control/DOCUMENT-TEMPLATE.md`](control/DOCUMENT-TEMPLATE.md).

## No-rediscovery rule

Future work must not re-derive Jason's basic architecture from previous chats, memory, or code archaeology.

Before designing or creating a provider/connector, capability/resource, agent/reasoning component, governance/policy gate, ingress/interface, identity/authority component, secret integration, internal service, System Registry entity, evidence/audit component, or reusable operational mechanism:

- load the Fundamentals Baseline;
- use the Extension Construction Map to locate the established construction path;
- read the governing architecture/standards/ADRs/component records;
- reuse the closest governed implementation pattern;
- update construction guidance if a missing prerequisite or reusable pattern had to be discovered.

A material workstream is not complete merely because its code works. It must be reconstructable and extensible from durable sources.

## Documentation authority

Jason documentation follows a governing hierarchy. The Constitution and approved governance remain highest authority. Canonical architecture, project decisions, engineering architecture, canonical models, component/capability specifications, standards, operational runbooks, proof records, current-work records, and generated outputs each have distinct roles.

- [`architecture/`](architecture/) owns canonical platform-level architecture for its named subjects.
- [`engineering/`](engineering/) contains detailed implementation-engineering architecture and reusable construction guidance subordinate to the Constitution, project ADRs, and canonical platform architecture.
- [`decisions/`](decisions/) contains project-level governed ADRs.
- [`components/`](components/) contains Kernel, capability, infrastructure, and component contracts.

For **current production topology and lifecycle**, the authoritative source is the governed System Registry and its append-only lifecycle/verification evidence under `implementation/kernel/system_registry/`. Human-readable operational documents explain or render that truth; they do not replace it.

For package-adjacent README files that legitimately remain outside `docs/`, use the Implementation Documentation Index. Those files are supporting implementation material only and cannot become hidden architecture, governance, authority, security, construction, or current-state sources.

## Canonical documentation structure

```text
docs/
  index.md
  control/          Fundamentals, current-work control, construction/documentation maps, templates, registers
  foundation/       Mission, Constitution, enduring principles
  governance/       Governance authority and decision architecture
  architecture/     Canonical platform architecture and supporting architecture references
  engineering/      Detailed implementation-engineering architecture and reusable construction guidance
  models/           Provider-neutral canonical models
  components/       Kernel, capabilities, infrastructure, operational components
  standards/        Engineering, architecture, documentation, and operating standards
  decisions/        Project-level Architecture Decision Records
  roadmaps/         Governed future work and capability roadmaps
  operations/       Runbooks, deployment, recovery, and verification procedures
  sessions/         Durable session, reconciliation, and proof records
  journal/          Architecture observations not yet promoted to governing architecture
  milestones/       Completed milestone declarations and evidence
  archive/          Superseded and historical records
```

Historical numbered documentation roots and the former top-level engineering `architecture/` tree are retired. Do not recreate parallel editable documentation roots.

## Core architectural rules that documentation must preserve

- Human and organizational authority remain explicit; technical access never creates business authority.
- The Central Orchestrator is the sole coordination/execution authority between agents, capabilities, providers, and governed actions.
- Agents and connectors never coordinate directly with one another.
- Capability/resource-driven orchestration is preferred over bespoke workflow scripts.
- Provider-specific behavior stays behind governed provider/capability boundaries.
- Evidence comes before assertion.
- Missing authority, ambiguous scope, unsupported provider resolution, or invalid contracts fail closed.
- Operational topology must be reconstructable from structured truth rather than individual or conversational memory.
- Secret values never belong in documentation, generated outputs, audit evidence, or chat handoffs.
- Reusable construction knowledge must be durable enough to create the next component without rediscovering fundamentals.

## If you are continuing work from another session

Do not assume a prior branch, container, provider, hash, lifecycle state, or deployment detail is still current.

Read the Fundamentals Baseline and current-work records first, then inspect current Git state and use the System Registry plus fresh host verification when production state matters. If a chat summary conflicts with governed documentation or observed evidence, the governed durable source wins.

## Standard Documentation Policy

The umbrella name for Jason's documentation-governance, continuity, reconstruction, and reusable-construction framework is the **Standard Documentation Policy**.

Its canonical entry point is [`control/STANDARD-DOCUMENTATION-POLICY.md`](control/STANDARD-DOCUMENTATION-POLICY.md). The policy is implemented and governed through:

- [`control/JASON-FUNDAMENTALS.md`](control/JASON-FUNDAMENTALS.md)
- [`control/CURRENT.md`](control/CURRENT.md)
- [`control/EXTENSION-CONSTRUCTION-MAP.md`](control/EXTENSION-CONSTRUCTION-MAP.md)
- [`control/DOCUMENTATION-REGISTER.md`](control/DOCUMENTATION-REGISTER.md)
- [`control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`](control/IMPLEMENTATION-DOCUMENTATION-INDEX.md)
- [`control/HOW-TO-DOCUMENT-JASON.md`](control/HOW-TO-DOCUMENT-JASON.md)
- [`standards/J-404-Documentation-Governance-and-Continuity.md`](standards/J-404-Documentation-Governance-and-Continuity.md)
- [`standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md`](standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md)
- [`decisions/ADR-008-Documentation-Control-Plane-Consolidation.md`](decisions/ADR-008-Documentation-Control-Plane-Consolidation.md)

The objective is not cosmetic organization. It is to ensure every material fact has one authoritative owner, all human-facing knowledge is discoverable from one place, reusable component construction is discoverable before implementation starts, and future work can continue without reconstructing institutional memory from chats.
