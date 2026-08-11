# Project Jason — Current Resume Point

**Updated:** 2026-08-11  
**Status:** Documentation consolidation and reconciliation complete; documentation-control validation and strict MkDocs are green; final broader CI and PR/base readiness review remain  
**Canonical purpose:** Human-readable resume point for current work. Production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

A future session resuming Project Jason should read, in order:

1. `docs/index.md`
2. this file
3. `docs/control/DOCUMENTATION-REGISTER.md`
4. `docs/control/HOW-TO-DOCUMENT-JASON.md`
5. `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` when implementation-local guidance is relevant
6. `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md` when documentation authority or historical paths matter
7. `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` when platform boundary or bypass rules matter
8. `docs/operations/README.md` for the procedure/deployment/generated-state/evidence boundary
9. the governing architecture/ADR/runbook/component/engineering records for the intended workstream
10. current GitHub state and System Registry/host evidence before asserting live production state

## Current documentation workstream

The active documentation-standardization branch is:

`docs/documentation-standardization-2026-08-11`

Draft PR:

`#161 — Standardize Project Jason documentation control plane`

The base branch most recently observed is `feature/jason-runtime-service` at commit `28719135e25639c48b5cce847ff83b6e4825d502`. This SHA is a last-observed Git fact only; refetch the base immediately before final PR readiness or merge decisions.

## Durable result

The documentation-control-plane work now establishes:

- `docs/` as the single human-facing documentation control plane;
- `docs/control/HOW-TO-DOCUMENT-JASON.md` as the repeatable documentation method for future human and AI sessions;
- `docs/control/DOCUMENTATION-REGISTER.md` as the ownership/classification and historical-migration register;
- `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` as the governed discovery boundary for implementation- and infrastructure-local README files;
- `docs/control/DOCUMENTATION-MIGRATION-ISSUES.md` as the durable reconciliation register, with no currently open migration issue;
- `docs/control/CURRENT.md` as the only canonical current resume point;
- canonical Foundation, Governance, Architecture, Models, Components, Standards, Decisions, Roadmaps, Operations, Sessions, Journal, and Milestones beneath `docs/`;
- the former top-level engineering `architecture/` tree under `docs/engineering/`, explicitly subordinate to the Constitution, project ADRs, and canonical J-series platform architecture;
- the former numbered documentation roots retired and rejected by documentation validation;
- direct MkDocs publication from `docs_dir: docs` without the retired mixed-source assembly staging tree;
- current-use tooling/workflow/operations path auditing for retired documentation roots;
- implementation-local README coverage enforced by CI;
- `docs/operations/README.md` as the authority/classification boundary for repeatable operational material, deployment records, generated current-state representation, and historical proof evidence;
- point-in-time CAP-007 live-pilot evidence preserved under `docs/sessions/` without changing what the proof established;
- the historical Platform Integrity “Article VII” conflict deliberately reconciled without changing the current Constitution; and
- J-405 plus CI enforcement protecting the platform-integrity/boundary requirements at the correct standards layer.

Repository-root `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` remain conventional entry/control files only and direct durable project knowledge into `docs/` rather than maintaining parallel current-state narratives.

## Important reconciliations completed

### Documentation layout decision

ADR-008 — Documentation Control Plane Consolidation — explicitly supersedes ADR-002 while preserving one authoritative source, no duplicate editable canonical copies, disposable generated output, publishing-tool independence, and institutional-memory preservation.

### Duplicate ADR-004

Datto RMM Managed-Device Authority retains ADR-004. Teams proactive messaging is corrected to ADR-007, with the identifier correction recorded as non-semantic.

### Architecture and engineering boundary

`docs/architecture/README.md` defines J-100 through J-103 as canonical platform-architecture owners for their named subjects. `docs/engineering/README.md` defines the detailed engineering tree as subordinate implementation engineering. JIS, engineering-ADR, and provider landing pages preserve that authority boundary and make the tree navigable.

### Platform Integrity constitutional conflict

The historical Platform Integrity record formerly labeled itself an approved constitutional Article VII, while the authoritative J-002 Constitution defines Article VII as **Knowledge as an Asset**.

The deliberate governance disposition is complete:

- J-002 and its Article VII remain unchanged;
- the original Platform Integrity text is preserved at `docs/archive/governance/ARTICLE_VII_PLATFORM_INTEGRITY-Historical.md` as historical/superseded evidence;
- `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` owns the durable platform-integrity requirements beneath the Constitution;
- J-405 preserves central orchestration, approved platform contracts, prohibited bypasses, secrets/workload-identity boundaries, policy/provider separation, client isolation, integrate-before-innovate, governed exceptions, and production-readiness enforcement; and
- documentation CI fails if the historical file reappears as current governance authority or if the J-405/archive reconciliation disappears.

MIG-DOC-003 is resolved.

### Operations and historical proof classification

`docs/operations/README.md` defines the rule:

- reusable procedures/runbooks/checklists remain in `docs/operations/`;
- deployment/bootstrap records may remain operational records but are not substitutes for observed runtime state;
- `System-Registry-Current-Operational-State.md` is a generated human view derived from System Registry structured truth;
- point-in-time host proofs, pilot evidence, and reconciliation evidence belong in `docs/sessions/`; and
- classification changes do not rewrite what historical evidence established.

MIG-DOC-005 is resolved/controlled.

### Current-use path audit

The final current-use audit is complete and enforced by `tools/validate_documentation_control.py` across `tools/`, `.github/workflows/`, and `docs/operations/`.

Stale current operator/tool paths were repaired to `docs/control/`, `docs/operations/`, and `docs/sessions/`. The audit also removed the obsolete documentation-assembly instruction from the INF-001 checklist.

One narrow historical compatibility mapping remains intentionally allowed in `tools/system_registry_docs.py`: append-only lifecycle events retain historical `08-Session-Records/...` evidence references and the generator maps them to current `docs/sessions/...` paths without rewriting immutable event history. The validator permits only that exact file/prefix case rather than excluding the file.

The strengthened documentation-control validator and strict MkDocs build both pass. MIG-DOC-007 is resolved.

### System Registry generated documentation

`tools/system_registry_docs.py` generates/checks `docs/operations/System-Registry-Current-Operational-State.md`. Append-only lifecycle events are not rewritten merely because documentation paths move; human rendering may resolve historical evidence references to their migrated `docs/sessions/` path.

## Remaining work

1. Allow the final broader `Validate Jason` and targeted PR workflows to finish after the closeout-record updates.
2. Refetch `feature/jason-runtime-service` and PR #161 immediately before changing PR readiness state.
3. Confirm the PR synthetic merge remains clean against the latest base and all required CI is green.
4. If those checks remain clean, PR #161 is ready to leave draft for final review. No unresolved documentation migration or constitutional disposition remains.

## Work explicitly not performed by this documentation workstream

No production container, OpenClaw bridge, Jason runtime, provider credential, System Registry lifecycle state, authority grant, or host configuration is changed by this documentation-standardization work.

This record does not claim the latest production runtime state. If another workstream has advanced runtime development, reconcile current Git/System Registry/host evidence before continuing host-sensitive work.

## Host-sensitive continuation

Live Teams/OpenClaw/Jason work is outside the authority of this documentation cleanup. A future host session must use fresh ingress/orchestration/System Registry evidence rather than this document or conversational memory to determine current runtime state.

## Documentation success condition

The documentation control plane is structurally and semantically complete when the final PR validation remains green against the current base.

Ongoing documentation governance is successful when:

- each material fact has one authoritative owner;
- current operational topology comes from System Registry structured truth rather than narrative duplication;
- future sessions consistently use `docs/control/HOW-TO-DOCUMENT-JASON.md`;
- implementation-local documentation is indexed and bounded as supporting material;
- historical proofs remain evidence rather than current-state authority;
- constitutional/governance conflicts are deliberately reconciled rather than silently normalized;
- current-use references cannot drift back to retired documentation roots unnoticed;
- documentation remains indexed, portable, versioned, and provider/tool independent; and
- a future contributor can reconstruct Jason's governance, architecture, engineering boundaries, operating method, proof history, and safe next action without access to chat history.
