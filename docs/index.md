# Project Jason Documentation

Project Jason is TeamAOT's governed operational platform and professional decision-support architecture.

This `docs/` tree is the single human-facing documentation control plane for Jason. A future human or AI session should begin here rather than relying on conversation history, remembered deployment details, or historical repository layout.

## Start here

1. **Current resume point:** [`control/CURRENT.md`](control/CURRENT.md).
2. **Where authoritative knowledge lives:** [`control/DOCUMENTATION-REGISTER.md`](control/DOCUMENTATION-REGISTER.md).
3. **How to write or update Jason documentation:** [`control/HOW-TO-DOCUMENT-JASON.md`](control/HOW-TO-DOCUMENT-JASON.md).
4. **Implementation-local documentation index:** [`control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`](control/IMPLEMENTATION-DOCUMENTATION-INDEX.md).
5. **Known reconciliation issues:** [`control/DOCUMENTATION-MIGRATION-ISSUES.md`](control/DOCUMENTATION-MIGRATION-ISSUES.md).
6. **Documentation governance standard:** [`standards/J-404-Documentation-Governance-and-Continuity.md`](standards/J-404-Documentation-Governance-and-Continuity.md).
7. **Handoff template:** [`control/HANDOFF-TEMPLATE.md`](control/HANDOFF-TEMPLATE.md).
8. **General durable-document template:** [`control/DOCUMENT-TEMPLATE.md`](control/DOCUMENT-TEMPLATE.md).

## Documentation authority

Jason documentation follows a governing hierarchy. The Constitution and approved governance remain highest authority. Canonical architecture, project decisions, engineering architecture, canonical models, component/capability specifications, standards, operational runbooks, proof records, current-work records, and generated outputs each have distinct roles.

- [`architecture/`](architecture/) owns canonical platform-level architecture for its named subjects.
- [`engineering/`](engineering/) contains detailed implementation-engineering architecture subordinate to the Constitution, project ADRs, and canonical platform architecture.
- [`decisions/`](decisions/) contains project-level governed ADRs.
- [`components/`](components/) contains Kernel, capability, infrastructure, and component contracts.

For **current production topology and lifecycle**, the authoritative source is the governed System Registry and its append-only lifecycle/verification evidence under `implementation/kernel/system_registry/`. Human-readable operational documents explain or render that truth; they do not replace it.

For package-adjacent README files that legitimately remain outside `docs/`, use the Implementation Documentation Index. Those files are supporting implementation material only and cannot become hidden architecture, governance, authority, security, or current-state sources.

For the detailed authority and historical path map, use the Documentation Register.

## Canonical documentation structure

```text
docs/
  index.md
  control/          Documentation process, current-work control, templates, registers
  foundation/       Mission, Constitution, enduring principles
  governance/       Governance authority and decision architecture
  architecture/     Canonical platform architecture and supporting architecture references
  engineering/      Detailed implementation-engineering architecture and JIS guidance
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

Historical numbered documentation roots and the former top-level engineering `architecture/` tree have been consolidated into this structure on the documentation-standardization branch. Do not recreate parallel editable documentation roots.

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

## If you are continuing work from another session

Do not assume a prior branch, container, provider, hash, lifecycle state, or deployment detail is still current.

Read the durable current-work/handoff records, inspect current Git state, and use the System Registry plus fresh host verification when production state matters. If a chat summary conflicts with governed documentation or observed evidence, the governed durable source wins.

## Documentation governance

Documentation structure and consistency are controlled by:

- [`control/DOCUMENTATION-REGISTER.md`](control/DOCUMENTATION-REGISTER.md)
- [`control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`](control/IMPLEMENTATION-DOCUMENTATION-INDEX.md)
- [`control/DOCUMENTATION-MIGRATION-ISSUES.md`](control/DOCUMENTATION-MIGRATION-ISSUES.md)
- [`control/HOW-TO-DOCUMENT-JASON.md`](control/HOW-TO-DOCUMENT-JASON.md)
- [`standards/J-404-Documentation-Governance-and-Continuity.md`](standards/J-404-Documentation-Governance-and-Continuity.md)
- [`decisions/ADR-008-Documentation-Control-Plane-Consolidation.md`](decisions/ADR-008-Documentation-Control-Plane-Consolidation.md)

The objective is not cosmetic organization. It is to ensure every material fact has one authoritative owner, all human-facing knowledge is discoverable from one place, and future work can be resumed without reconstructing institutional memory from chats.