# Project Jason Documentation Register

**Status:** Active documentation control record  
**Owner:** Jason Architecture Authority  
**Purpose:** Single register for where Project Jason knowledge lives, which source is authoritative, how reusable construction knowledge is discovered, and how historical documentation locations were consolidated into `docs/`.

## How to use this register

Start here when you need to answer:

- Where is the authoritative document for this topic?
- Which fundamentals govern the work?
- How do I create another component of this class without rediscovering the pattern?
- Is a document current, supporting, generated, or historical?
- Where should a new document be created?
- Which source wins if two documents disagree?
- Which historical repository path did a document come from?

For mandatory fundamentals, use `docs/control/JASON-FUNDAMENTALS.md`.

For reusable component construction, use `docs/control/EXTENSION-CONSTRUCTION-MAP.md`.

For consistent authoring, use `docs/control/HOW-TO-DOCUMENT-JASON.md`.

For implementation-local README discovery, use `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`.

For operations/proof classification, use `docs/operations/README.md`.

For remaining authority/reconciliation issues, use `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md`.

## Current physical rule

All governed human-facing Project Jason documentation is physically consolidated under `docs/`, except implementation-local documentation that has a justified need to remain beside code, schemas, deployment packages, or tests and is registered in `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`.

Conventional repository entry/control files may remain at repository root:

- `README.md` — repository entry point directing readers to `docs/index.md`;
- `CONTRIBUTING.md` — contributor entry point requiring the governed documentation workflow;
- `SECURITY.md` — security-reporting entry point deferring durable security architecture/current-state claims to governed sources under `docs/`.

These root files are not parallel documentation authorities.

Historical numbered documentation roots, the former top-level engineering `architecture/` tree, and root `TODO.md` are retired. CI rejects their re-creation. MkDocs consumes `docs/` directly.

## Authority model

| Knowledge type | Authoritative owner | Notes |
|---|---|---|
| Mission and constitutional rules | `docs/foundation/` | Conversation memory cannot override these records. |
| Governance rules | `docs/governance/` subject to the Constitution | Must remain consistent with Foundation authority. |
| Fundamentals discovery/reconstruction index | `docs/control/JASON-FUNDAMENTALS.md` | Discovery index only; it points to higher-authority owners and must not become competing authority. |
| Reusable extension/construction discovery | `docs/control/EXTENSION-CONSTRUCTION-MAP.md` plus owning engineering/component guidance | Maps component classes to their governed construction path. |
| Platform integrity and boundary enforcement | `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` subject to the Constitution | Governs prohibited bypasses, approved platform boundaries, provider/policy separation, exception handling, and production-readiness enforcement. |
| Platform architecture | Canonical J-series records under `docs/architecture/` plus approved project ADRs | `docs/architecture/README.md` classifies supporting foundational architecture records. |
| Detailed implementation-engineering architecture / reusable construction guidance | `docs/engineering/` | Subordinate to Constitution, project ADRs, canonical platform architecture. |
| Canonical organizational models | `docs/models/` | Provider-neutral concepts. |
| Component/capability/provider contracts | `docs/components/` plus versioned implementation contracts/tests | Code/tests prove implementation behavior; documents define governed intended contracts. |
| Current production topology/state | System Registry structured sources + append-only lifecycle history + verification evidence | Do not recreate current topology manually in narrative documents. |
| Operating procedure / deployment record / generated operational view | `docs/operations/` classified by `docs/operations/README.md` | Procedures do not self-authorize; generated current-state views derive from System Registry truth. |
| Historical proof | `docs/sessions/` and bounded evidence references | Point-in-time proof, not perpetual current-state authority. |
| Current work/resume point | `docs/control/CURRENT.md` | References authoritative evidence instead of duplicating volatile state. |
| Implementation-local README discovery | `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` | Discoverability only; package README files remain supporting implementation documentation. |
| Architecture observations | `docs/journal/` | Non-governing until promoted normally. |
| Active governed roadmap/backlog | `docs/roadmaps/` | Historical/superseded roadmaps belong in `docs/archive/`. |
| Milestone declarations | `docs/milestones/` | Release/documentation readiness tooling consumes this location. |
| Published website/search index | Generated output | Never authoritative. |
| Chat/session memory | Non-authoritative context | Convert durable knowledge into governed records; never use it to re-derive fundamentals. |

## Canonical documentation structure

```text
docs/
  index.md
  control/
    JASON-FUNDAMENTALS.md
    CURRENT.md
    EXTENSION-CONSTRUCTION-MAP.md
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
| `01-Governance/` | `docs/governance/` plus `docs/archive/governance/` | Migrated; former Platform Integrity Article VII conflict resolved. Current Constitution Article VII remains Knowledge as an Asset; historical Platform Integrity record is archived and durable requirements are governed by J-405. |
| `02-Architecture/` | `docs/architecture/` | Migrated; J-100 through J-103 canonical for their named subjects. |
| `architecture/` | `docs/engineering/` | Migrated; JIS/provider/capability/execution-policy/resolution engineering architecture subordinate to canonical platform architecture. |
| `02-Canonical-Models/` | `docs/models/` | Migrated; legacy root retired. |
| `03-Components/` | `docs/components/` | Migrated; Kernel, capability, infrastructure, component-operations records consolidated. |
| `04-Standards/` | `docs/standards/` | Migrated; J-401 through J-405 share one standards location. |
| `05-ADR/` | `docs/decisions/` | Migrated after duplicate ADR-004 reconciliation. Datto RMM retains ADR-004; Teams proactive messaging corrected to ADR-007. ADR-008 supersedes ADR-002. |
| `06-Roadmaps/` | `docs/roadmaps/` | Active capability register migrated. |
| `07-Roadmap/` | `docs/roadmaps/` and `docs/archive/roadmaps/` | Machine-readable roadmap status migrated; historical narrative roadmap preserved as superseded. |
| `TODO.md` | `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md` | Governed backlog moved into control plane; root TODO retired. |
| `07-Operations/` | `docs/operations/` and `docs/sessions/` for point-in-time evidence | Migrated and semantically classified. CAP-007 live-pilot proof reclassified to sessions without changing evidence identity. |
| `08-Session-Records/` | `docs/sessions/` | Migrated; former CURRENT preserved as `Legacy-CURRENT-2026-08-11.md`; `docs/control/CURRENT.md` is only current resume point. |
| `09-Architecture-Journal/` | `docs/journal/` | Migrated; journal remains non-governing until promoted. |
| `10-Milestones/` | `docs/milestones/` | Migrated; readiness tooling updated. |
| `99-Archive/` if historically used | `docs/archive/` | Historical authority only. |

## Platform Integrity reconciliation

The current Constitution's Article VII remains **Knowledge as an Asset**.

The former Platform Integrity Article VII is preserved at `docs/archive/governance/ARTICLE_VII_PLATFORM_INTEGRITY-Historical.md` as historical evidence, not current constitutional authority.

Its durable requirements are governed by `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md`.

## Machine-readable operational sources

These remain outside narrative documentation because they are executable/structured operational truth:

- `implementation/kernel/system_registry/production-registry.json`
- `implementation/kernel/system_registry/production-lifecycle-events.json`
- `implementation/kernel/system_registry/production-verification-plan.json`
- System Registry schemas, repository logic, probes, verifier, and tests under `implementation/kernel/system_registry/`

Human documentation references these sources instead of creating a second operational inventory. Historical repository paths inside append-only lifecycle/evidence events remain immutable evidence; generated views may resolve them to current canonical documentation paths.

## Implementation-local documentation exception

Implementation-local README files may remain beside code where adjacency is operationally useful.

This exception is bounded:

- README is supporting implementation documentation, not higher governance/architecture authority;
- material architecture, construction, authority, security, or operating rules must have governed owners under `docs/`;
- material implementation-local documentation must be discoverable from the control plane;
- future sessions must not copy every README into `docs/` merely for centralization.

`docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` controls this exception, and CI enforces README coverage beneath `implementation/` and `infrastructure/`.

## High-value continuity records

- `docs/index.md` — entry point.
- `docs/control/JASON-FUNDAMENTALS.md` — mandatory fundamentals reconstruction baseline.
- `docs/control/CURRENT.md` — canonical resume point.
- `docs/control/EXTENSION-CONSTRUCTION-MAP.md` — component-class construction/reuse discovery map.
- `docs/control/HOW-TO-DOCUMENT-JASON.md` — repeatable authoring/update procedure.
- `docs/control/DOCUMENTATION-REGISTER.md` — authority/source map.
- `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` — package-adjacent discovery boundary.
- `docs/standards/J-404-Documentation-Governance-and-Continuity.md` — documentation/continuity governance.
- `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` — platform-integrity standard.
- `docs/decisions/ADR-008-Documentation-Control-Plane-Consolidation.md` — control-plane consolidation decision.
- `docs/foundation/J-002-Constitution.md` — constitutional authority.
- `docs/architecture/J-100-Reference-Architecture.md` — central platform architecture.
- `docs/architecture/J-101-Capability-Registry.md` — capability architecture.
- `docs/architecture/J-102-Governed-Approval-Architecture.md` — approval architecture.
- `docs/architecture/J-103-System-Registry.md` — System Registry architecture.
- `docs/engineering/README.md` — engineering authority boundary/index.
- `docs/engineering/jis/JIS-Provider-Development-Guide.md` — provider/connector construction guide.
- `docs/operations/README.md` — operations/proof classification authority map.
- `implementation/kernel/system_registry/` — structured operational truth.

## Classification rules

Every durable human-facing record should be classifiable as Canonical, Supporting, Evidence, Generated, Superseded, Historical, Draft/Proposed, or Conflict.

Do not delete conflicts merely to make the repository cleaner. Reconcile authority and preserve material history.

## Rule for new work

Before material work begins, read `JASON-FUNDAMENTALS.md`, `CURRENT.md`, and the relevant path in `EXTENSION-CONSTRUCTION-MAP.md`.

Before adding documentation, consult `HOW-TO-DOCUMENT-JASON.md` and search the Register/current tree to avoid duplicate authority.

If work reveals a missing reusable prerequisite or forces the team to rediscover how an existing component class was built, that is a documentation defect. Update the owning construction guidance and Extension Construction Map before closing the workstream.

Implementation-local README files may remain beside code only when adjacency is useful; they must be indexed and cannot become sole owners of material architecture, construction, governance, authority, security, or operating rules.

## Documentation-complete condition

Documentation control is complete for a material workstream only when CI and review confirm, as applicable:

- required control records exist and are discoverable;
- no retired documentation roots are recreated;
- MkDocs builds directly from `docs/` with strict validation;
- material implementation-local documentation is indexed;
- current-use paths do not drift to retired locations;
- `CURRENT.md` reflects the actual workstream/resume point rather than a completed PR;
- the affected reusable component class has sufficient construction guidance indexed by `EXTENSION-CONSTRUCTION-MAP.md`;
- documentation impact was explicitly determined; and
- a future competent human or AI can continue and create the next component of the same class without reconstructing Jason fundamentals from chat history or code archaeology.
