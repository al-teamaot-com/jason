# Project Jason Documentation Control-Plane Consolidation — 2026-08-11

**Status:** In-progress governed documentation consolidation record  
**Classification:** Historical implementation/reconciliation evidence  
**Workstream:** Offline documentation standardization  
**Branch:** `docs/documentation-standardization-2026-08-11`  
**Draft PR:** `#161 — Standardize Project Jason documentation control plane`  
**Authority:** Jason continuity/institutional-memory principles, J-403, proposed J-404, ADR-008  
**Production mutation:** None

## Purpose

Preserve the bounded result of the 2026-08-11 offline documentation-standardization work so a future session does not have to reconstruct what was moved, why authority was reconciled, or which work remains from chat history.

The work was initiated while the operator was away from the physical Jason host. No host-sensitive or production-runtime remediation was performed.

## Problem being corrected

Jason documentation had accumulated across numbered repository roots, publishing directories, operational/session records, a separate engineering architecture tree, implementation-local README files, root backlog material, generated documentation, and conversation handoffs.

The information was present, but safe reconstruction required prior knowledge of where earlier sessions happened to put it.

The consolidation goal is:

> durable project knowledge is discoverable from one human-facing documentation control plane, while each material fact retains one authoritative owner and current operational truth remains structured rather than conversational.

## Structural result

The repository documentation control plane is now `docs/`.

Consolidated categories include:

- `docs/control/`
- `docs/foundation/`
- `docs/governance/`
- `docs/architecture/`
- `docs/engineering/`
- `docs/models/`
- `docs/components/`
- `docs/standards/`
- `docs/decisions/`
- `docs/roadmaps/`
- `docs/operations/`
- `docs/sessions/`
- `docs/journal/`
- `docs/milestones/`
- `docs/archive/`

The historical numbered documentation roots and former top-level engineering `architecture/` tree were retired on the documentation branch.

Root `TODO.md` was moved into the governed roadmap area.

Root `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` remain only as conventional repository entry/control files and now direct durable project knowledge into `docs/`.

## Documentation-control records created or standardized

- `docs/index.md`
- `docs/control/CURRENT.md`
- `docs/control/DOCUMENTATION-REGISTER.md`
- `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md`
- `docs/control/HOW-TO-DOCUMENT-JASON.md`
- `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`
- `docs/control/HANDOFF-TEMPLATE.md`
- `docs/control/DOCUMENT-TEMPLATE.md`
- `docs/standards/J-404-Documentation-Governance-and-Continuity.md`

The operator specifically required a durable “how to document” record so future sessions can maintain the same documentation discipline. `HOW-TO-DOCUMENT-JASON.md` is that canonical procedure.

## Architecture/decision reconciliations

### Documentation layout

ADR-008 — Documentation Control Plane Consolidation — explicitly supersedes ADR-002.

The supersession preserves the valid invariants from ADR-002:

- one authoritative canonical source per material fact;
- no duplicate editable canonical copies;
- generated outputs remain disposable;
- publishing tools remain replaceable;
- migration must protect institutional memory.

The changed conclusion is physical organization: operating evidence demonstrated that fragmentation itself created continuity risk, so governed human-facing documentation is now consolidated beneath `docs/` for institutional-memory reasons rather than to satisfy MkDocs.

### Duplicate project ADR-004

Git history established that Datto RMM Managed-Device Authority occupied ADR-004 before the later Teams proactive-messaging decision reused that identifier.

Resolution:

- Datto RMM Managed-Device Authority retains ADR-004;
- Teams proactive messaging is corrected to ADR-007;
- ADR-007 explicitly records that only the identifier changed, not the architectural decision;
- ADR-005 and ADR-006 remain unchanged.

### Platform vs engineering architecture

J-100 through J-103 are consolidated under `docs/architecture/` as canonical owners for their named platform-level subjects.

Earlier blueprint/catalog/deployment/core-service architecture records remain supporting foundational references and cannot silently override the Constitution, project ADRs, J-series architecture, governed component specifications, or System Registry state.

The historical top-level engineering `architecture/` tree is now `docs/engineering/`. Its JIS/provider/capability/execution-policy/resolution records are explicitly subordinate implementation-engineering architecture. Its historical engineering `ADR-000x` namespace remains distinct from project ADRs under `docs/decisions/`.

## Roadmap/current-work reconciliation

- active capability register -> `docs/roadmaps/Jason-Capability-Register.md`;
- machine-readable roadmap status -> `docs/roadmaps/Jason-Roadmap-Status.json`;
- governed backlog/future ideas -> `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md`;
- older narrative roadmap -> `docs/archive/roadmaps/Jason-Roadmap-Historical.md` as Historical/Superseded;
- canonical resume point -> `docs/control/CURRENT.md`;
- former session CURRENT -> `docs/sessions/Legacy-CURRENT-2026-08-11.md` as historical context.

## System Registry continuity rule preserved

System Registry structured truth remains under `implementation/kernel/system_registry/`; it was not moved into narrative documentation.

`tools/system_registry_docs.py` now generates/checks:

`docs/operations/System-Registry-Current-Operational-State.md`

Append-only lifecycle events were not rewritten for repository path migration. The generated human view may resolve historical session-record paths to their current `docs/sessions/` locations while preserving the original event unchanged.

No System Registry entity lifecycle was promoted, demoted, or otherwise changed by this documentation workstream.

## Implementation-local documentation rule

Material README files may remain beside implementation/deployment packages when adjacency is useful.

They are indexed through:

`docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`

The documentation validator inventories README files beneath `implementation/` and `infrastructure/` and requires indexed discoverability. These README files remain supporting implementation documentation and cannot become hidden higher architecture/governance/current-state authority.

## Tooling changes

- MkDocs uses `docs_dir: docs` directly.
- Historical mixed-source `tools/assemble_docs.py` is retired.
- `tools/documentation_readiness.py` uses `docs/milestones/`.
- `tools/catch_me_up.py` uses consolidated CURRENT, roadmap, operations, milestone, and session paths.
- `tools/system_registry_docs.py` uses the consolidated operational-state output path.
- documentation-sensitive CI/workflows are being converted from retired path roots to consolidated paths.
- `tools/validate_documentation_control.py` rejects retired roots, validates required control records, validates ADR reconciliation, validates MkDocs source, validates current continuity paths, audits active tooling for retired numbered paths, and indexes implementation-local README documentation.

## Authority conflict intentionally not normalized

`docs/governance/ARTICLE_VII_PLATFORM_INTEGRITY.md` historically calls itself an approved constitutional Article VII, while the current authoritative Constitution defines Article VII as **Knowledge as an Asset**.

This conflict is contained by `docs/governance/README.md`:

- current J-002 Constitution is higher authority;
- the Platform Integrity record must not be treated as current constitutional Article VII;
- non-conflicting content may be supporting context only;
- unique durable requirements require deliberate constitutional/governance reconciliation.

The offline documentation workstream did not silently amend the Constitution to make the conflict disappear.

## Remaining work

Before PR #161 may leave draft status:

1. strict MkDocs/documentation CI must be green;
2. current-use stale path references in tooling/workflows must be removed;
3. historical proof records physically located in `docs/operations/` should be classified and moved to `docs/sessions/` where evidence identity can be preserved;
4. the Platform Integrity Article VII conflict requires deliberate governance review;
5. the documentation branch must be reconciled with the latest concurrent `feature/jason-runtime-service` branch;
6. broader CI and authority-sensitive diffs must be reviewed.

## Production/host boundary

This workstream did **not**:

- restart or rebuild Jason runtime;
- modify OpenClaw or its bridge;
- alter production provider credentials;
- change OpenBao configuration;
- add/remove authority grants;
- change System Registry declared state or lifecycle;
- remediate live Teams behavior;
- make a host deployment.

Any future statement about live production state must come from fresh Git/System Registry/host evidence rather than this historical documentation record.
