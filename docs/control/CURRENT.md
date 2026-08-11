# Project Jason — Current Resume Point

**Updated:** 2026-08-11  
**Status:** Documentation consolidation structurally complete; implementation-local indexing and operations/proof classification complete; strict MkDocs and Validate Jason green; final plain-text path audit and one deliberate constitutional reconciliation remain  
**Canonical purpose:** Human-readable resume point for current work. Production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

A future session resuming Project Jason should read, in order:

1. `docs/index.md`
2. this file
3. `docs/control/DOCUMENTATION-REGISTER.md`
4. `docs/control/HOW-TO-DOCUMENT-JASON.md`
5. `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` when implementation-local guidance is relevant
6. `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md` when documentation authority or historical paths matter
7. `docs/operations/README.md` for the procedure/deployment/generated-state/evidence boundary
8. the governing architecture/ADR/runbook/component/engineering records for the intended workstream
9. current GitHub state and System Registry/host evidence before asserting live production state

## Current documentation workstream

The active offline documentation-standardization branch is:

`docs/documentation-standardization-2026-08-11`

Draft PR:

`#161 — Standardize Project Jason documentation control plane`

The current base branch observed during this documentation pass is `feature/jason-runtime-service` at commit `28719135e25639c48b5cce847ff83b6e4825d502`. Treat that SHA only as the last observed Git fact; refetch the base immediately before any further write, merge, retarget, or release decision.

## Last durable documentation progress

The consolidation/control-plane work now establishes:

- `docs/` as the single human-facing documentation control plane;
- `docs/control/HOW-TO-DOCUMENT-JASON.md` as the repeatable documentation method for future human and AI sessions;
- `docs/control/DOCUMENTATION-REGISTER.md` as the ownership/classification register;
- `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` as the governed discovery/control index for implementation- and infrastructure-local README files;
- CI enforcement that every tracked `implementation/**/README.md` and `infrastructure/**/README.md` is represented in that index;
- `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md` as the reconciliation register for unresolved documentation authority/path issues;
- `docs/control/CURRENT.md` as the only canonical current resume point;
- canonical Foundation, Governance, Architecture, Models, Components, Standards, Decisions, Roadmaps, Operations, Sessions, Journal, and Milestones beneath `docs/`;
- the former top-level engineering `architecture/` tree under `docs/engineering/`, explicitly subordinate to the Constitution, project ADRs, and canonical J-series platform architecture;
- the former numbered documentation roots retired and rejected by documentation validation;
- direct MkDocs publication from `docs_dir: docs` without a mixed-source assembly staging tree;
- strict MkDocs navigation repaired for JIS, engineering ADR, provider, capability, execution-policy, and governed-resolution records;
- `Validate Jason` green on the repaired direct-docs tree;
- `docs/operations/README.md` as the authority/classification boundary for repeatable operational material, deployment records, generated current-state representation, and historical proof evidence;
- point-in-time `CAP-007-Live-Pilot-Proof-2026-08-11.md` preserved under `docs/sessions/` with evidence identity and conclusions unchanged;
- `OPS-ITGLUE-DATTO-LIVE-CONVERGENCE-PROOF.md` intentionally retained under `docs/operations/` because its primary content is a reusable observe-only runbook despite its filename;
- known current-use path drift in that convergence runbook and the CAP-007/session indexes repaired to current `docs/operations/`, `docs/sessions/`, and `docs/control/` paths.

Repository-root `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` remain conventional entry/control files only and direct durable project knowledge into `docs/` rather than maintaining parallel current-state narratives.

## Important reconciliations completed

### Documentation layout decision

ADR-008 — Documentation Control Plane Consolidation — explicitly supersedes ADR-002 while preserving the important invariants of one authoritative source, no duplicate editable canonical copies, disposable generated output, publishing-tool independence, and institutional-memory preservation.

### Duplicate ADR-004

Datto RMM Managed-Device Authority retains ADR-004. Teams proactive messaging is corrected to ADR-007, with the identifier correction recorded as non-semantic.

### Architecture and engineering boundary

`docs/architecture/README.md` defines J-100 through J-103 as canonical platform-architecture owners for their named subjects. `docs/engineering/README.md` defines the detailed engineering tree as subordinate implementation engineering. New JIS, engineering-ADR, and provider landing pages preserve that authority boundary and make the tree navigable.

### Roadmap/backlog overlap

- active capability register: `docs/roadmaps/Jason-Capability-Register.md`;
- machine-readable roadmap status: `docs/roadmaps/Jason-Roadmap-Status.json`;
- governed TODO/future ideas: `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md`;
- superseded historical roadmap: `docs/archive/roadmaps/Jason-Roadmap-Historical.md`.

### Legacy CURRENT

The former session checkpoint is preserved as `docs/sessions/Legacy-CURRENT-2026-08-11.md`. It is historical context, not current runtime authority.

### Implementation-local documentation

Package-adjacent README files are supporting implementation documentation only. The implementation-documentation index makes them discoverable and maps them to governed owners or related records; index presence does not grant architecture, governance, security, or current-state authority.

### Operations and historical proof classification

`docs/operations/README.md` now defines the rule:

- reusable procedures/runbooks/checklists remain in `docs/operations/`;
- deployment/bootstrap records may remain operational records but are not substitutes for observed runtime state;
- `System-Registry-Current-Operational-State.md` is a generated human view derived from System Registry structured truth;
- point-in-time host proofs, pilot evidence, and reconciliation evidence belong in `docs/sessions/`;
- classification changes do not rewrite what historical evidence established.

MIG-DOC-005 is therefore resolved/controlled.

### System Registry generated documentation

`tools/system_registry_docs.py` generates/checks `docs/operations/System-Registry-Current-Operational-State.md`. Append-only lifecycle events are not rewritten merely because documentation paths move; human rendering may resolve historical evidence references to their migrated `docs/sessions/` path.

## Remaining documentation work

1. Complete the final plain-text/current-use path audit described by MIG-DOC-007. Strict MkDocs and known current operator-path repairs are already green; preserve historical path text when it intentionally describes former repository state.
2. Perform deliberate governance review of `docs/governance/ARTICLE_VII_PLATFORM_INTEGRITY.md`, whose historical Article VII label conflicts with the current Constitution's Article VII. The conflict is contained and must not be silently rewritten.
3. Refetch/reconcile draft PR #161 with the latest `feature/jason-runtime-service` state immediately before merge or retargeting.
4. Keep PR #161 draft until the remaining authority-sensitive reconciliation is deliberately disposed and final CI remains green.

## Work explicitly not performed by this documentation workstream

No production container, OpenClaw bridge, Jason runtime, provider credential, System Registry lifecycle state, authority grant, or host configuration is changed by this offline documentation-standardization work.

This record does not claim the latest production runtime state. If another workstream has advanced runtime development, reconcile current Git/System Registry/host evidence before continuing host-sensitive work.

## Host-sensitive continuation

Live Teams/OpenClaw/Jason work is outside the authority of this offline documentation cleanup. A future host session must use fresh ingress/orchestration/System Registry evidence rather than this document or conversational memory to determine current runtime state.

## Documentation success condition

Structural consolidation is now evidenced by the direct `docs/` tree building cleanly under strict MkDocs and by `Validate Jason` passing after navigation/index repairs.

Ongoing documentation governance is successful when:

- each material fact has one authoritative owner;
- current operational topology comes from System Registry structured truth rather than narrative duplication;
- future sessions consistently use `docs/control/HOW-TO-DOCUMENT-JASON.md`;
- implementation-local documentation is indexed and bounded as supporting material;
- historical proofs remain evidence rather than current-state authority;
- unresolved constitutional/governance conflicts are recorded and deliberately resolved rather than silently normalized;
- documentation remains indexed, portable, versioned, and provider/tool independent; and
- a future contributor can reconstruct Jason's governance, architecture, engineering boundaries, operating method, proof history, and safe next action without access to chat history.
