# Project Jason — Current Resume Point

**Updated:** 2026-08-11  
**Status:** Documentation consolidation structurally complete; implementation-index, path audit, semantic classification, and CI validation in progress  
**Canonical purpose:** Human-readable resume point for current work. Production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

A future session resuming Project Jason should read, in order:

1. `docs/index.md`
2. this file
3. `docs/control/DOCUMENTATION-REGISTER.md`
4. `docs/control/HOW-TO-DOCUMENT-JASON.md`
5. `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md` when documentation authority or historical paths matter
6. the governing architecture/ADR/runbook/component/engineering records for the intended workstream
7. current GitHub state and System Registry/host evidence before asserting live production state

## Current documentation workstream

The active offline documentation-standardization branch is:

`docs/documentation-standardization-2026-08-11`

Draft PR:

`#161 — Standardize Project Jason documentation control plane`

The branch was created from the then-current `feature/jason-runtime-service` state. That base is historical branch context, not a claim about the current active development branch or production runtime. Before merging or retargeting, refetch and reconcile the current base branch.

## Last durable documentation progress

The structural consolidation is now substantially complete:

- `docs/` is the single human-facing documentation control plane;
- `docs/control/HOW-TO-DOCUMENT-JASON.md` defines the repeatable documentation method future human and AI sessions must use;
- `docs/control/DOCUMENTATION-REGISTER.md` defines authoritative ownership and historical migration paths;
- `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md` preserves unresolved authority/classification issues;
- `docs/control/CURRENT.md` is the only canonical current resume point;
- Foundation is under `docs/foundation/`;
- governance is under `docs/governance/` with an explicit authority map;
- canonical J-series platform architecture is under `docs/architecture/` with supporting older architecture records classified beneath it;
- the former top-level engineering `architecture/` tree is under `docs/engineering/`, explicitly subordinate to platform architecture and project ADRs;
- canonical models are under `docs/models/`;
- component/capability/infrastructure records are under `docs/components/`;
- standards are under `docs/standards/`;
- project ADRs are under `docs/decisions/`;
- active roadmaps/backlog are under `docs/roadmaps/`;
- the older narrative roadmap is preserved as historical under `docs/archive/roadmaps/`;
- root `TODO.md` is retired and its governed backlog is `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md`;
- operational records are under `docs/operations/`;
- durable session/proof records are under `docs/sessions/`;
- architecture journal records are under `docs/journal/`;
- milestones are under `docs/milestones/`;
- the former numbered documentation roots and top-level engineering `architecture/` root are retired;
- MkDocs now uses `docs_dir: docs` directly;
- the mixed-source `tools/assemble_docs.py` staging mechanism is retired;
- CI validation rejects recreation of retired human-documentation roots and root `TODO.md`.

Repository-root `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` remain conventional entry/control files only and now direct durable project knowledge into `docs/` rather than maintaining parallel current-state narratives.

## Important reconciliations completed

### Documentation layout decision

ADR-008 — Documentation Control Plane Consolidation — explicitly supersedes ADR-002.

ADR-002's important invariants remain preserved: one authoritative source, no duplicate editable canonical copies, disposable generated output, publishing-tool independence, and preservation of institutional memory.

### Duplicate ADR-004

Historical order showed Datto RMM Managed-Device Authority occupied ADR-004 first.

- Datto RMM Managed-Device Authority remains ADR-004.
- Teams proactive messaging is corrected to ADR-007.
- ADR-007 records that the identifier correction does not change architectural meaning.

### Architecture overlap

`docs/architecture/README.md` defines J-100 through J-103 as canonical owners for their named platform-architecture subjects and classifies earlier blueprint/catalog/core-services/deployment/foundation-build records as supporting foundational references.

`docs/engineering/README.md` defines the former top-level engineering architecture as detailed implementation engineering beneath the Constitution, project ADRs, and canonical J-series platform architecture. Its historical engineering `ADR-000x` namespace remains distinct from project ADRs under `docs/decisions/`.

### Roadmap/backlog overlap

- active capability register: `docs/roadmaps/Jason-Capability-Register.md`;
- machine-readable roadmap status: `docs/roadmaps/Jason-Roadmap-Status.json`;
- governed TODO/future ideas: `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md`;
- superseded historical roadmap: `docs/archive/roadmaps/Jason-Roadmap-Historical.md`.

### Legacy CURRENT

The former `08-Session-Records/CURRENT.md` is preserved as `docs/sessions/Legacy-CURRENT-2026-08-11.md`. It is historical context, not current runtime authority.

### System Registry generated documentation

`tools/system_registry_docs.py` now generates/checks `docs/operations/System-Registry-Current-Operational-State.md`.

Append-only lifecycle events are not rewritten merely because documentation paths moved. The generated human view resolves historical `08-Session-Records/...` evidence references to their current `docs/sessions/...` path when the migrated evidence exists.

### CI/tooling path alignment

Documentation-sensitive tests/workflows are being updated to use consolidated paths, including:

- provider secret lifecycle documentation tests/workflow;
- identity/authority workflow documentation filters;
- AWS provider foundation documentation filters;
- approval-request documentation filters;
- OpenClaw ingress documentation filters;
- documentation readiness milestone paths;
- CatchMeUp continuity paths.

## Remaining offline documentation work

1. Build `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` after auditing code/deployment-adjacent README files so material implementation guidance is discoverable without copying every README into `docs/`.
2. Update the documentation index, J-404/HOW-TO/Register/MkDocs/validator to require and expose that implementation-documentation index.
3. Complete strict MkDocs/CI validation and repair broken Markdown links caused by moved paths.
4. Audit remaining workflows/tools/scripts and plain-text operator instructions for current-use references to retired paths; preserve references that intentionally describe historical repository state.
5. Classify records currently in `docs/operations/` into repeatable procedure vs historical proof and move historical proof to `docs/sessions/` where doing so will not damage evidence identity.
6. Perform deliberate governance review of `docs/governance/ARTICLE_VII_PLATFORM_INTEGRITY.md`, whose historical Article VII label conflicts with the current Constitution's Article VII. The conflict is contained but not silently rewritten.
7. Reconcile draft PR #161 with the latest `feature/jason-runtime-service` state before any merge.
8. Keep the PR draft until documentation CI, broader CI, and authority-sensitive reconciliation are green.

## Work explicitly not performed by this documentation workstream

No production container, OpenClaw bridge, Jason runtime, provider credential, System Registry lifecycle state, authority grant, or host configuration is changed by this offline documentation-standardization work.

This record does not claim the latest production runtime state. If another workstream or chat has advanced runtime development, reconcile current Git/System Registry/host evidence before continuing host-sensitive work.

## Host-sensitive continuation

Before this offline documentation work began, live troubleshooting was underway in the governed Teams/OpenClaw/Jason path. This branch deliberately does not resolve or assert the current state of that live path while the operator is away from the Jason host.

A future host session must use fresh ingress/orchestration/System Registry evidence rather than this document or conversational memory to determine current runtime state.

## Documentation success condition

Structural consolidation is complete when CI proves the direct `docs/` tree builds cleanly and no retired documentation roots remain.

Ongoing documentation governance is successful when:

- each material fact has one authoritative owner;
- current operational topology comes from System Registry structured truth rather than narrative duplication;
- future sessions consistently use `docs/control/HOW-TO-DOCUMENT-JASON.md`;
- implementation-local documentation is indexed and bounded as supporting material;
- unresolved conflicts are recorded instead of silently normalized;
- documentation remains indexed, portable, versioned, and provider/tool independent; and
- a future contributor can reconstruct Jason's governance, architecture, engineering boundaries, operating method, proof history, and safe next action without access to chat history.
