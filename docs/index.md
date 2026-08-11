# Project Jason Documentation

Project Jason is TeamAOT's governed operational platform and professional decision-support architecture.

This `docs/` tree is the single human-facing documentation control plane for Jason. A future human or AI session should begin here rather than relying on conversation history, remembered deployment details, or scattered repository files.

## Start here

1. **Current resume point:** [`control/CURRENT.md`](control/CURRENT.md).
2. **Where authoritative knowledge lives:** [`control/DOCUMENTATION-REGISTER.md`](control/DOCUMENTATION-REGISTER.md).
3. **How to write or update Jason documentation:** [`control/HOW-TO-DOCUMENT-JASON.md`](control/HOW-TO-DOCUMENT-JASON.md).
4. **Known migration conflicts/blockers:** [`control/DOCUMENTATION-MIGRATION-ISSUES.md`](control/DOCUMENTATION-MIGRATION-ISSUES.md).
5. **Documentation governance standard:** [`standards/J-404-Documentation-Governance-and-Continuity.md`](standards/J-404-Documentation-Governance-and-Continuity.md).
6. **Handoff template:** [`control/HANDOFF-TEMPLATE.md`](control/HANDOFF-TEMPLATE.md).
7. **General durable-document template:** [`control/DOCUMENT-TEMPLATE.md`](control/DOCUMENT-TEMPLATE.md).

## Documentation authority

Jason documentation follows a governing hierarchy. The Constitution and approved governance remain highest authority. Architecture, canonical models, standards, ADRs, component/capability specifications, operational runbooks, proof records, current-work records, and generated outputs each have distinct roles.

For **current production topology and lifecycle**, the authoritative source is the governed System Registry and its append-only lifecycle/verification evidence under `implementation/kernel/system_registry/`. Human-readable operational documents explain or render that truth; they do not replace it.

For the detailed authority and migration map, use the Documentation Register.

## Target documentation structure

```text
docs/
  index.md
  control/          Documentation process, current-work control, templates, migration register
  foundation/       Mission, Constitution, enduring principles
  governance/       Governance authority and decision architecture
  architecture/     Reference architecture and enduring system boundaries
  models/           Provider-neutral canonical models
  components/       Kernel, capabilities, infrastructure, operational components
  standards/        Engineering, architecture, documentation, and operating standards
  decisions/        Architecture Decision Records
  roadmaps/         Governed future work and capability roadmaps
  operations/       Runbooks, deployment, recovery, and verification procedures
  sessions/         Durable session, reconciliation, and proof records
  journal/          Architecture observations not yet promoted to governing architecture
  milestones/       Completed milestone declarations and evidence
  archive/          Superseded and historical records
```

The repository is currently migrating older numbered documentation roots into this structure. During migration, the Documentation Register identifies which physical source remains canonical. Do not create duplicate editable copies simply to satisfy the target directory layout.

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

## During the documentation migration

The migration is controlled by:

- [`control/DOCUMENTATION-REGISTER.md`](control/DOCUMENTATION-REGISTER.md)
- [`control/DOCUMENTATION-MIGRATION-ISSUES.md`](control/DOCUMENTATION-MIGRATION-ISSUES.md)
- [`standards/J-404-Documentation-Governance-and-Continuity.md`](standards/J-404-Documentation-Governance-and-Continuity.md)

The objective is not cosmetic reorganization. It is to ensure every material fact has one authoritative owner, all human-facing knowledge is discoverable from one place, and future work can be resumed without reconstructing institutional memory from chats.