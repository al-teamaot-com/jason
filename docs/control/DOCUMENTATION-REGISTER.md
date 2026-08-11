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

For implementation-local README discovery, use `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`.

For operations/proof classification, use `docs/operations/README.md`.

For remaining authority/reconciliation issues, use `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md`.

## Current physical rule

All governed human-facing Project Jason documentation is now physically consolidated under `docs/`, except implementation-local documentation that has a justified need to remain beside code, schemas, deployment packages, or tests and is registered in `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`.

Conventional repository entry/control files may remain at repository root:

- `README.md` — repository entry point that directs readers to `docs/index.md`;
- `CONTRIBUTING.md` — contributor entry point that requires the governed documentation workflow;
- `SECURITY.md` — security-reporting entry point that defers durable security architecture and current-state claims to governed sources under `docs/`.

These root files are not parallel documentation authorities.

The historical numbered documentation roots and the former top-level engineering `architecture/` tree are retired. CI rejects their re-creation.

The historical root `TODO.md` is also retired. Governed backlog/future-work documentation is maintained under `docs/roadmaps/`.

MkDocs consumes `docs/` directly. The former mixed-source `.build/docs` assembly step is retired.

## Authority model

| Knowledge type | Authoritative owner | Notes |
|---|---|---|
| Mission and constitutional rules | `docs/foundation/` | Conversation memory cannot override these records. |
| Governance rules | `docs/governance/` subject to the Constitution | Must remain consistent with Foundation authority. |
| Platform architecture | Canonical J-series records under `docs/architecture/` plus approved project ADRs | `docs/architecture/README.md` classifies supporting foundational architecture records. |
| Detailed implementation-engineering architecture | `docs/engineering/` | Subordinate to the Constitution, project ADRs, and canonical platform architecture. Historical engineering `ADR-000x` records are a separate engineering namespace from project ADRs under `docs/decisions/`. |
| Canonical organizational models | `docs/models/` | Provider-neutral concepts. |
| Component/capability/provider contracts | `docs/components/` plus versioned implementation contracts/tests | Code/tests prove implementation behavior; documents define governed intended contracts. |
| Current production topology/state | System Registry structured sources + append-only lifecycle history + verification evidence | Do not recreate current topology manually in narrative documents. |
| Operating procedure / deployment record / generated operational view | `docs/operations/` classified by `docs/operations/README.md` | Procedures do not self-authorize; deployment records are not substitutes for observed state; generated current-state views are derived from System Registry truth. |
| Historical proof | `docs/sessions/` and bounded evidence references | Proves what occurred at a point in time; not perpetual current-state authority. |
| Current work/resume point | `docs/control/CURRENT.md` | References authoritative evidence instead of duplicating volatile state. |
| Implementation-local README discovery | `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` | Index grants discoverability only; package README files remain supporting implementation documentation. |
| Architecture observations | `docs/journal/` | Non-governing until promoted through normal governance. |
| Active governed roadmap/backlog | `docs/roadmaps/` | Historical/superseded roadmaps belong in `docs/archive/`. |
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
    IMPLEMENTATION-DOCUMENTATION-INDEX.md
    HANDOFF-TEMPLATE.md
    DOCUMENT-TEMPLATE.md
  foundation/
  governance/
  architecture/
  engineering/
    adr/
    capabilities/
    execution-policy/
    jis/
    providers/
    resolution/
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
| `architecture/` | `docs/engineering/` | Migrated; historical JIS/provider/capability/execution-policy/resolution engineering architecture is now explicitly subordinate to canonical platform architecture. The historical engineering `ADR-000x` namespace remains distinct from project ADRs. |
| `02-Canonical-Models/` | `docs/models/` | Migrated; legacy root retired. |
| `03-Components/` | `docs/components/` | Migrated; Kernel, capability, infrastructure, and component-operations records consolidated. |
| `04-Standards/` | `docs/standards/` | Migrated; J-401 through J-404 now share one standards location. |
| `05-ADR/` | `docs/decisions/` | Migrated after resolving duplicate ADR-004 identity. Datto RMM retains ADR-004; Teams proactive messaging was corrected to ADR-007. ADR-008 supersedes ADR-002 and governs the consolidated documentation control plane. |
| `06-Roadmaps/` | `docs/roadmaps/` | Active capability register migrated. |
| `07-Roadmap/` | `docs/roadmaps/` and `docs/archive/roadmaps/` | Machine-readable roadmap status migrated to `docs/roadmaps/`; historical narrative roadmap preserved as explicitly superseded under `docs/archive/roadmaps/`. |
| `TODO.md` | `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md` | Governed backlog moved into the documentation control plane; root TODO retired. |
| `07-Operations/` | `docs/operations/` and `docs/sessions/` where a migrated record is point-in-time evidence | Migrated and semantically classified. `docs/operations/README.md` defines the boundary. Reusable procedures/deployment records/generated operational views remain operational; dated historical proofs belong in sessions. CAP-007 live-pilot proof was reclassified to sessions without altering evidence identity. |
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

Historical repository paths inside append-only lifecycle/evidence events remain historical evidence and are not rewritten merely because documentation moved. Generated current views may resolve them to the current canonical documentation location while preserving the underlying event unchanged.

## Implementation-local documentation exception

Implementation-local README files may remain beside code when adjacency is operationally useful, for example connector/package setup, deployment-package mechanics, schemas, or test-harness usage.

This exception is bounded:

- the README is supporting implementation documentation, not higher governance or architecture authority;
- material architecture, authority, security, or operating rules must have a governed owner under `docs/`;
- material implementation-local documentation must be discoverable from the documentation control plane;
- future sessions must not copy every README into `docs/` merely for centralization.

`docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` is the control mechanism for that exception. Documentation CI inventories README files beneath `implementation/` and `infrastructure/` and fails if a discovered README is not represented in the index.

## High-value continuity records

- `docs/index.md` — documentation entry point.
- `docs/control/CURRENT.md` — canonical resume point.
- `docs/control/HOW-TO-DOCUMENT-JASON.md` — repeatable authoring/update procedure for future sessions.
- `docs/control/DOCUMENTATION-REGISTER.md` — this authority/source map.
- `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` — discovery/control boundary for package-adjacent documentation.
- `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md` — remaining reconciliation issues.
- `docs/standards/J-404-Documentation-Governance-and-Continuity.md` — documentation governance.
- `docs/decisions/ADR-008-Documentation-Control-Plane-Consolidation.md` — decision superseding the old numbered-root layout.
- `docs/foundation/J-002-Constitution.md` — constitutional authority.
- `docs/architecture/J-103-System-Registry.md` — System Registry architecture.
- `docs/engineering/README.md` — detailed engineering-architecture authority boundary and index.
- `docs/roadmaps/Jason-Capability-Register.md` — governed capability roadmap.
- `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md` — governed backlog/future ideas.
- `docs/operations/README.md` — operations/procedure/deployment/generated-state/historical-proof classification authority map.
- `docs/operations/System-Registry-Current-Operational-State.md` — generated human-readable operational-state representation where current.
- `docs/sessions/README.md` — historical session/proof evidence boundary.
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

Implementation-local README files may remain beside code only when adjacency is operationally useful. They must be represented in `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` and must not quietly become the sole owner of a material architecture, governance, authority, security, or operating rule.

Repository-root `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` are conventional navigation/control entry points only; durable project truth belongs under `docs/` or in explicitly structured machine-readable sources such as the System Registry.

## Documentation-complete condition

Documentation consolidation is structurally complete when CI confirms:

- no retired numbered documentation roots or top-level engineering `architecture/` tree exist;
- root `TODO.md` has not been re-created;
- MkDocs builds directly from `docs/` with strict validation;
- required control records exist and are linked;
- release/documentation tooling uses consolidated paths;
- material implementation-local documentation is indexed; and
- no known broken current-use links remain.

Documentation governance remains an ongoing responsibility after structural migration. Authority conflicts, stale records, and classification cleanup must continue to be resolved under J-404 rather than allowing the repository to fragment again.
