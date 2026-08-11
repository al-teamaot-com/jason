# Project Jason Documentation Register

**Status:** Active documentation control record  
**Owner:** Jason Architecture Authority  
**Purpose:** Single register for where Project Jason knowledge lives, which source is authoritative, and how historical documentation locations were consolidated into `docs/`.

## How to use this register

Start here when you need to answer any of these questions:

- Where is the authoritative document for this topic?
- Is a document current, supporting, generated, or historical?
- Where should a new document be created?
- Which source should win if two documents disagree?
- Which historical repository path did a document come from?

For consistent authoring, use `docs/control/HOW-TO-DOCUMENT-JASON.md`.

For remaining authority/reconciliation issues, use `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md`.

## Current physical rule

All governed human-facing Project Jason documentation is now physically consolidated under `docs/`, except implementation-local documentation that has a justified need to remain beside code, schemas, deployment packages, or tests.

The historical numbered documentation roots are retired. CI rejects their re-creation.

MkDocs consumes `docs/` directly. The former mixed-source `.build/docs` assembly step is retired.

## Authority model

| Knowledge type | Authoritative owner | Notes |
|---|---|---|
| Mission and constitutional rules | `docs/foundation/` | Conversation memory cannot override these records. |
| Governance rules | `docs/governance/` subject to the Constitution | Must remain consistent with Foundation authority. |
| Architecture | Canonical J-series records under `docs/architecture/` plus approved ADRs | `docs/architecture/README.md` classifies supporting foundation records. |
| Canonical organizational models | `docs/models/` | Provider-neutral concepts. |
| Component/capability/provider contracts | `docs/components/` plus versioned implementation contracts/tests | Code/tests prove implementation behavior; documents define governed intended contracts. |
| Current production topology/state | System Registry structured sources + append-only lifecycle history + verification evidence | Do not recreate current topology manually in narrative documents. |
| Operating procedure | `docs/operations/` | Procedures must reference current authority and evidence sources. |
| Historical proof | `docs/sessions/` and bounded evidence references | Proves what occurred at a point in time. |
| Current work/resume point | `docs/control/CURRENT.md` | References authoritative evidence instead of duplicating volatile state. |
| Architecture observations | `docs/journal/` | Non-governing until promoted through normal governance. |
| Active governed roadmap | `docs/roadmaps/` | Historical roadmaps belong in `docs/archive/`. |
| Milestone declarations | `docs/milestones/` | Release/documentation readiness tooling consumes this location. |
| Published website/search index | Generated output | Never authoritative. |
| Chat/session memory | Non-authoritative context | Convert material durable knowledge into governed records. |

## Canonical documentation structure

```text
docs/
  index.md
  control/
    CURRENT.md
    DOCUMENTATION-REGISTER.md
    DOCUMENTATION-MIGRATION-ISSUES.md
    HOW-TO-DOCUMENT-JASON.md
    HANDOFF-TEMPLATE.md
    DOCUMENT-TEMPLATE.md
  foundation/
  governance/
  architecture/
  models/
  components/
    kernel/
    capabilities/
    infrastructure/
    operations/
  standards/
  decisions/
  roadmaps/
  operations/
  sessions/
  journal/
  milestones/
  archive/
```

## Historical migration register

| Historical source | Canonical target | State / reconciliation note |
|---|---|---|
| `01-Foundation/` | `docs/foundation/` | Migrated; legacy root retired. |
| `01-Governance/` | `docs/governance/` | Migrated; J-003 consolidated. The conflicting historical `ARTICLE_VII_PLATFORM_INTEGRITY.md` remains explicitly subordinate to the current Constitution pending formal disposition. |
| `02-Architecture/` | `docs/architecture/` | Migrated; J-100 through J-103 are canonical for their named subjects. Existing blueprint/catalog/specification records are classified by `docs/architecture/README.md` as supporting foundational references. |
| `02-Canonical-Models/` | `docs/models/` | Migrated; legacy root retired. |
| `03-Components/` | `docs/components/` | Migrated; Kernel, capability, infrastructure, and component-operations records consolidated. |
| `04-Standards/` | `docs/standards/` | Migrated; J-401 through J-404 now share one standards location. |
| `05-ADR/` | `docs/decisions/` | Migrated after resolving duplicate ADR-004 identity. Datto RMM retains ADR-004; Teams proactive messaging was corrected to ADR-007. ADR-008 supersedes ADR-002 and governs the consolidated documentation control plane. |
| `06-Roadmaps/` | `docs/roadmaps/` | Active capability register migrated. |
| `07-Roadmap/` | `docs/archive/roadmaps/` | Historical roadmap preserved as explicitly superseded instead of competing with the active roadmap. |
| `07-Operations/` | `docs/operations/` | Physically migrated. Repeatable-procedure vs historical-proof classification remains an ongoing cleanup requirement for individual records. |
| `08-Session-Records/` | `docs/sessions/` | Migrated; former `CURRENT.md` preserved as `Legacy-CURRENT-2026-08-11.md`. `docs/control/CURRENT.md` is the only current resume point. |
| `09-Architecture-Journal/` | `docs/journal/` | Migrated; journal remains explicitly non-governing until promoted. |
| `10-Milestones/` | `docs/milestones/` | Migrated; documentation-readiness tooling updated. |
| `99-Archive/` if historically used | `docs/archive/` | Archive authority is historical by definition; new superseded records are retained under `docs/archive/`. |

## Machine-readable operational sources

These sources deliberately remain outside narrative documentation because they are executable/structured operational truth:

- `implementation/kernel/system_registry/production-registry.json`
- `implementation/kernel/system_registry/production-lifecycle-events.json`
- `implementation/kernel/system_registry/production-verification-plan.json`
- System Registry schemas, repository logic, probes, verifier, and related tests under `implementation/kernel/system_registry/`

Human documentation references these sources rather than creating a second operational inventory.

## High-value continuity records

- `docs/index.md` — documentation entry point.
- `docs/control/CURRENT.md` — canonical resume point.
- `docs/control/HOW-TO-DOCUMENT-JASON.md` — repeatable authoring/update procedure for future sessions.
- `docs/control/DOCUMENTATION-REGISTER.md` — this authority/source map.
- `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md` — remaining reconciliation issues.
- `docs/standards/J-404-Documentation-Governance-and-Continuity.md` — documentation governance.
- `docs/decisions/ADR-008-Documentation-Control-Plane-Consolidation.md` — decision superseding the old numbered-root layout.
- `docs/foundation/J-002-Constitution.md` — constitutional authority.
- `docs/architecture/J-103-System-Registry.md` — System Registry architecture.
- `docs/operations/System-Registry-Current-Operational-State.md` — generated human-readable operational-state representation where current.
- `implementation/kernel/system_registry/` — structured operational truth.

## Classification rules

Every durable human-facing record should be classifiable as one of:

- **Canonical:** authoritative source for its subject.
- **Supporting:** useful detail that references a canonical source.
- **Evidence:** historical proof of a bounded event or result.
- **Generated:** derived and disposable.
- **Superseded:** replaced by a newer canonical record but retained for history.
- **Historical:** accurate for a past state but not current authority.
- **Draft/Proposed:** not yet governing authority.
- **Conflict:** requires reconciliation before competing claims can be treated as authoritative.

Do not delete a conflicting record merely to make the repository cleaner. Reconcile authority and preserve material history.

## Rule for new work

New governed human-facing documentation belongs under `docs/`.

Before adding a document, future sessions must consult `docs/control/HOW-TO-DOCUMENT-JASON.md` and search the Documentation Register/current documentation tree to avoid duplicate authority.

Implementation-local README files may remain beside code only when adjacency is operationally useful. They must not quietly become the sole owner of a material architecture, governance, authority, or operating rule.

## Documentation-complete condition

Documentation consolidation is structurally complete when CI confirms:

- no retired numbered documentation roots exist;
- MkDocs builds directly from `docs/` with strict validation;
- required control records exist and are linked;
- release/documentation tooling uses consolidated paths; and
- no known broken links remain.

Documentation governance remains an ongoing responsibility after structural migration. Authority conflicts, stale records, and classification cleanup must continue to be resolved under J-404 rather than allowing the repository to fragment again.
