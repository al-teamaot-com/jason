# Project Jason Documentation Register

**Status:** Active migration control record  
**Owner:** Jason Architecture Authority  
**Purpose:** Single register for where Project Jason knowledge lives, which source is authoritative, and how legacy documentation is being consolidated into `docs/`.

## How to use this register

Start here when you need to answer any of these questions:

- Where is the authoritative document for this topic?
- Is a document current, transitional, generated, or historical?
- Where should a new document be created?
- Has a documentation category already moved into `docs/`?
- Which source should win if two documents disagree?

For instructions on how to create, update, hand off, retire, or reconcile Jason documentation consistently, use `docs/control/HOW-TO-DOCUMENT-JASON.md`.

During migration, `docs/` is the single documentation control plane even when the canonical source for a category still physically resides in a legacy numbered directory.

## Authority model

| Knowledge type | Authoritative owner | Notes |
|---|---|---|
| Mission and constitutional rules | Jason Constitution / Foundation | Conversation memory cannot override these records. |
| Governance rules | Approved governance records | Must remain consistent with Constitution. |
| Architecture | Approved architecture records and ADRs | Enduring structure and boundaries. |
| Canonical organizational models | Approved canonical models | Provider-neutral concepts. |
| Component/capability/provider contracts | Governed component specifications and implementation contracts | Code/tests prove implementation behavior; specifications define intended contract. |
| Current production topology/state | System Registry + append-only lifecycle history + verification evidence | Do not manually recreate current topology in narrative documents. |
| Operating procedure | Approved runbook | Procedure must reference current authority and evidence sources. |
| Historical proof | Durable session/proof/evidence record | Proves what occurred at a point in time. |
| Current work/resume point | `docs/control/CURRENT.md` | Must point to authoritative evidence rather than duplicate volatile state. |
| Published website/search index | Generated output | Never authoritative. |
| Chat/session memory | Non-authoritative context | Must be converted to durable records when it matters. |

## Target documentation structure

All new human-facing governed documentation should use this structure unless an approved exception applies:

```text
docs/
  index.md
  control/
    CURRENT.md
    DOCUMENTATION-REGISTER.md
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

Implementation-local README files may remain beside code where adjacency is operationally useful. They must be discoverable from the documentation control plane when they contain material operating information.

## Migration register

| Current source | Target location | Current authority | Migration status | Retirement condition |
|---|---|---|---|---|
| `01-Foundation/` | `docs/foundation/` | `docs/foundation/` | **Migrated** | Complete on this migration branch: Foundation files moved, legacy root removed, assembly/navigation updated. Remaining inbound-reference issues, if discovered by validation, must be corrected before merge. |
| `01-Governance/` | `docs/governance/` | Legacy source plus existing `docs/governance/` material | Planned/reconciliation required | Duplicate governance authority reconciled and canonical paths established. |
| `02-Architecture/` | `docs/architecture/` | Legacy source plus existing `docs/architecture/` material | Planned/reconciliation required | Blueprint-style docs and J-series architecture records reconciled without losing history. |
| `02-Canonical-Models/` | `docs/models/` | Legacy source | Planned | All model references/navigation/tooling migrated. |
| `03-Components/` | `docs/components/` | Legacy source | Planned | Component/capability/infrastructure/operations documents moved with references intact. |
| `04-Standards/` | `docs/standards/` | Legacy source for existing standards; `docs/standards/` for new standards | In progress | Existing standards migrated and old directory retired or reduced to compatibility stubs. |
| `05-ADR/` | `docs/decisions/` | Legacy source | Planned | ADR tooling/navigation/references updated. |
| `06-Roadmaps/` | `docs/roadmaps/` | Legacy source | Planned | Roadmap links/tooling migrated. |
| `07-Roadmap/` | `docs/roadmaps/` | Legacy duplicate category | Reconciliation required | Content reconciled with `06-Roadmaps/`; obsolete duplicate root retired. |
| `07-Operations/` | `docs/operations/` | Legacy source | Planned | Runbooks/deployment records/proofs classified and moved to correct operation/session category. |
| `08-Session-Records/` | `docs/sessions/` | Legacy source except canonical current-work record | In progress | `CURRENT.md` redirected; durable records moved/indexed and legacy root retired. |
| `09-Architecture-Journal/` | `docs/journal/` | Legacy source | Planned | Journal content moved without treating observations as approved architecture. |
| `10-Milestones/` | `docs/milestones/` | Legacy source | Planned | Documentation readiness/release tooling updated to new location. |
| `99-Archive/` if present | `docs/archive/` | Legacy archive | Planned | Historical retention paths updated. |
| `docs/architecture/` | `docs/architecture/` | Existing publishing/source material | Reconciliation required | Each document classified as canonical, superseded, historical, or merged with J-series architecture. |
| `docs/governance/` | `docs/governance/` | Existing publishing/source material | Reconciliation required | Constitutional/governance status and relationship to Foundation records made explicit. |
| Implementation README files | Remain adjacent when justified; indexed from `docs/` | Implementation source | Ongoing exception | No architectural/governance rule exists only in an unindexed implementation README. |

## Machine-readable operational sources

These files are deliberately not moved into narrative documentation because they are executable/structured operational truth:

- `implementation/kernel/system_registry/production-registry.json`
- `implementation/kernel/system_registry/production-lifecycle-events.json`
- `implementation/kernel/system_registry/production-verification-plan.json`
- System Registry schemas and verifier implementation under `implementation/kernel/system_registry/`

Human documentation must reference these sources rather than creating a second operational inventory.

## High-value continuity records

Until migration is complete, the following records are especially important:

- `docs/index.md` — single documentation entry point.
- `docs/standards/J-404-Documentation-Governance-and-Continuity.md` — documentation governance rules.
- `docs/control/HOW-TO-DOCUMENT-JASON.md` — repeatable authoring/update procedure for future sessions.
- `docs/control/CURRENT.md` — canonical resume point.
- `docs/control/DOCUMENTATION-REGISTER.md` — this source/migration register.
- `docs/control/HANDOFF-TEMPLATE.md` — required structure for durable workstream handoff.
- `docs/control/DOCUMENT-TEMPLATE.md` — standard metadata and durable-document skeleton.
- `docs/foundation/J-002-Constitution.md` — constitutional authority.
- `02-Architecture/J-103-System-Registry.md` — authoritative System Registry architecture during migration.
- `07-Operations/System-Registry-Current-Operational-State.md` — generated human-readable operational-state view where current.
- `implementation/kernel/system_registry/` — structured operational truth.

## Classification rules during migration

A document encountered during migration must be classified as one of:

- **Canonical:** authoritative source for its subject.
- **Supporting:** useful detail that references a canonical source.
- **Evidence:** historical proof of a bounded event or result.
- **Generated:** derived and disposable.
- **Superseded:** replaced by a newer canonical record but retained for history.
- **Historical:** accurate for a past state but not current authority.
- **Draft/Proposed:** not yet governing authority.
- **Duplicate/Conflict:** requires reconciliation before either copy may be treated as authoritative.

Do not delete a conflicting record merely to make the repository look cleaner. Reconcile the authority and preserve material history.

## Migration sequencing

The recommended order is:

1. Documentation control plane and standards.
2. Foundation/governance authority.
3. Architecture and canonical models.
4. Standards and ADRs.
5. Component/capability/infrastructure specifications.
6. Operations/runbooks and current operational documentation.
7. Session/proof records.
8. Roadmaps, journal, milestones, and archive.
9. CI/tooling cleanup and retirement of compatibility roots.

This order prevents lower-level content from being reorganized before its authority framework is stable.

## Rule for new work

New governed human-facing documentation belongs under `docs/`.

If an existing legacy canonical document must be modified before its category is migrated, update that existing source and ensure the change remains discoverable from `docs/`. Do not create a duplicate replacement copy solely to satisfy the new directory convention.

Before adding a new document, future sessions must consult `docs/control/HOW-TO-DOCUMENT-JASON.md` so naming, authority, evidence, status, security, and handoff practices remain consistent.

## Completion criteria

Documentation consolidation is complete only when:

- all governed human-facing documentation is discoverable and physically organized under `docs/`, except approved implementation-local exceptions;
- each material topic has one authoritative source;
- legacy numbered roots are retired or contain only explicit compatibility stubs;
- MkDocs publishes directly from the consolidated source structure;
- CI validates documentation structure and stale/duplicate authority rules;
- release/documentation tooling uses the consolidated paths;
- current operational state is derived from structured truth;
- current work can be resumed from `docs/control/CURRENT.md`; and
- a future contributor can reconstruct how Jason is governed, built, operated, and verified without access to chat history.