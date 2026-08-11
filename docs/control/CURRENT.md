# Project Jason — Current Resume Point

**Updated:** 2026-08-11  
**Status:** Documentation consolidation structurally complete; reconciliation/validation in progress  
**Canonical purpose:** Human-readable resume point for current work. Production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

A future session resuming Project Jason should read, in order:

1. `docs/index.md`
2. this file
3. `docs/control/DOCUMENTATION-REGISTER.md`
4. `docs/control/HOW-TO-DOCUMENT-JASON.md`
5. `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md` when documentation authority or historical paths matter
6. the governing architecture/ADR/runbook/component records for the intended workstream
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
- Foundation moved to `docs/foundation/`;
- governance moved to `docs/governance/` with an explicit authority map;
- J-series architecture moved into `docs/architecture/` with supporting older architecture records classified beneath it;
- canonical models moved to `docs/models/`;
- component/capability/infrastructure records moved to `docs/components/`;
- standards moved to `docs/standards/`;
- ADRs moved to `docs/decisions/`;
- active roadmaps moved to `docs/roadmaps/`, with the older roadmap preserved as historical under `docs/archive/`;
- operational records moved to `docs/operations/`;
- durable session/proof records moved to `docs/sessions/`;
- architecture journal moved to `docs/journal/`;
- milestones moved to `docs/milestones/`;
- the former numbered documentation roots are retired;
- MkDocs now uses `docs_dir: docs` directly;
- the mixed-source `tools/assemble_docs.py` staging mechanism is retired;
- CI now rejects recreation of retired numbered human-documentation roots.

## Important reconciliations completed

### Documentation layout decision

ADR-008 — Documentation Control Plane Consolidation — now explicitly supersedes ADR-002.

ADR-002's important invariants remain preserved: one authoritative source, no duplicate editable canonical copies, disposable generated output, publishing-tool independence, and preservation of institutional memory.

### Duplicate ADR-004

Historical order showed Datto RMM Managed-Device Authority occupied ADR-004 first.

- Datto RMM Managed-Device Authority remains ADR-004.
- Teams proactive messaging is corrected to ADR-007.
- ADR-007 records that the identifier correction does not change architectural meaning.

### Architecture overlap

`docs/architecture/README.md` defines J-100 through J-103 as canonical owners for their named architecture subjects and classifies earlier blueprint/catalog/core-services/deployment/foundation-build records as supporting foundational references.

### Roadmap overlap

The active capability register is under `docs/roadmaps/`; the older roadmap is retained under `docs/archive/roadmaps/` as historical/superseded.

### Legacy CURRENT

The former `08-Session-Records/CURRENT.md` is preserved as `docs/sessions/Legacy-CURRENT-2026-08-11.md`. It is historical context, not current runtime authority.

## Remaining offline documentation work

1. Complete strict MkDocs/CI validation after the final direct-`docs/` conversion and repair any broken links caused by moved paths.
2. Audit plain-text references that still point current operators to retired numbered paths; preserve references that intentionally describe historical repository state.
3. Classify records currently in `docs/operations/` into repeatable procedure vs historical proof and move historical proof to `docs/sessions/` where doing so will not damage evidence identity.
4. Audit implementation-local READMEs and add a documentation index so material implementation guidance is discoverable without copying every README into `docs/`.
5. Perform deliberate governance review of `docs/governance/ARTICLE_VII_PLATFORM_INTEGRITY.md`, whose historical Article VII label conflicts with the current Constitution's Article VII. The conflict is contained but not silently rewritten.
6. Reconcile draft PR #161 with the latest `feature/jason-runtime-service` state before any merge.
7. Keep the PR draft until documentation CI, broader CI, and authority-sensitive reconciliation are green.

## Work explicitly not performed by this documentation workstream

No production container, OpenClaw bridge, Jason runtime, provider credential, System Registry lifecycle state, authority grant, or host configuration is changed by this offline documentation-standardization work.

This record does not claim the latest production runtime state. If another workstream or chat has advanced runtime development, reconcile current Git/System Registry/host evidence before continuing host-sensitive work.

## Host-sensitive continuation

Before this offline documentation work began, live troubleshooting was underway in the governed Teams/OpenClaw/Jason path. This branch deliberately does not resolve or assert the current state of that live path while the operator is away from the Jason host.

A future host session must use fresh ingress/orchestration/System Registry evidence rather than this document or conversational memory to determine current runtime state.

## Documentation success condition

Structural consolidation is complete when CI proves the direct `docs/` tree builds cleanly and no retired numbered roots remain.

Ongoing documentation governance is successful when:

- each material fact has one authoritative owner;
- current operational topology comes from System Registry structured truth rather than narrative duplication;
- future sessions consistently use `docs/control/HOW-TO-DOCUMENT-JASON.md`;
- unresolved conflicts are recorded instead of silently normalized;
- documentation remains indexed, portable, versioned, and provider/tool independent; and
- a future contributor can reconstruct Jason's governance, architecture, implementation boundaries, operating method, proof history, and safe next action without access to chat history.
