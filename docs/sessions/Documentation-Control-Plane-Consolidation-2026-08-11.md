# Project Jason Documentation Control-Plane Consolidation — 2026-08-11

**Status:** Consolidation/reconciliation substantially complete; final path audit and merge-readiness validation pending  
**Classification:** Historical implementation/reconciliation evidence  
**Workstream:** Offline documentation standardization  
**Branch:** `docs/documentation-standardization-2026-08-11`  
**Draft PR:** `#161 — Standardize Project Jason documentation control plane`  
**Authority:** Jason continuity/institutional-memory principles, J-403, J-404, ADR-008, and approved Platform Integrity reconciliation  
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

Root `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` remain only as conventional repository entry/control files and direct durable project knowledge into `docs/`.

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
- `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md`

`HOW-TO-DOCUMENT-JASON.md` is the canonical repeatable documentation procedure for future sessions.

## Architecture/decision reconciliations

### Documentation layout

ADR-008 — Documentation Control Plane Consolidation — explicitly supersedes ADR-002 while preserving one authoritative source, no duplicate editable canonical copies, disposable generated output, publishing-tool independence, and institutional-memory preservation.

### Duplicate project ADR-004

Git history established that Datto RMM Managed-Device Authority occupied ADR-004 before the later Teams proactive-messaging decision reused that identifier.

Resolution:

- Datto RMM Managed-Device Authority retains ADR-004;
- Teams proactive messaging is corrected to ADR-007;
- ADR-007 records that only the identifier changed;
- ADR-005 and ADR-006 remain unchanged.

### Platform vs engineering architecture

J-100 through J-103 are consolidated under `docs/architecture/` as canonical owners for their named platform-level subjects.

The historical top-level engineering `architecture/` tree is now `docs/engineering/`. Its JIS/provider/capability/execution-policy/resolution records are explicitly subordinate implementation-engineering architecture. Its historical engineering `ADR-000x` namespace remains distinct from project ADRs under `docs/decisions/`.

### Platform Integrity “Article VII”

A historical record labeled itself `Article VII - Platform Integrity` and `Approved constitutional article`, while the authoritative J-002 Constitution defines Article VII as **Knowledge as an Asset**.

The operator approved the deliberate disposition on 2026-08-11.

Resolution:

- the current J-002 Constitution and Article VII remain unchanged;
- the historical source text is preserved at `docs/archive/governance/ARTICLE_VII_PLATFORM_INTEGRITY-Historical.md` and explicitly marked Historical/Superseded as governing authority;
- its durable requirements were extracted into `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` beneath the Constitution;
- J-405 preserves approved-platform-contract, central-orchestration, prohibited-bypass, workload-identity/secrets, provider/policy-separation, cross-client-isolation, integrate-before-innovate, exception-governance, and production-readiness controls;
- `docs/governance/README.md` and the Documentation Register now state the resolved authority relationship;
- MIG-DOC-003 is closed; and
- documentation CI now fails if the old free-standing Article VII reappears as current governance authority or the J-405/archive reconciliation is lost.

The reconciliation preserves institutional memory without creating a second constitutional Article VII or silently deleting the earlier requirements.

## Roadmap/current-work reconciliation

- active capability register -> `docs/roadmaps/Jason-Capability-Register.md`;
- machine-readable roadmap status -> `docs/roadmaps/Jason-Roadmap-Status.json`;
- governed backlog/future ideas -> `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md`;
- older narrative roadmap -> `docs/archive/roadmaps/Jason-Roadmap-Historical.md` as Historical/Superseded;
- canonical resume point -> `docs/control/CURRENT.md`;
- former session CURRENT -> `docs/sessions/Legacy-CURRENT-2026-08-11.md` as historical context.

## Operations/proof classification

`docs/operations/README.md` now defines the operational documentation authority boundary.

Repeatable procedures remain operational; dated point-in-time proof belongs in sessions. The CAP-007 live pilot proof was moved to sessions without altering evidence identity. The IT Glue/Datto live convergence file remains operational because its primary content is a reusable observe-only runbook despite its filename.

## System Registry continuity rule preserved

System Registry structured truth remains under `implementation/kernel/system_registry/`; it was not moved into narrative documentation.

`tools/system_registry_docs.py` generates/checks `docs/operations/System-Registry-Current-Operational-State.md`.

Append-only lifecycle events were not rewritten for repository path migration. The generated human view may resolve historical session-record paths to their current `docs/sessions/` locations while preserving the original event unchanged.

No System Registry entity lifecycle was promoted, demoted, or otherwise changed by this documentation workstream.

## Implementation-local documentation rule

Material README files may remain beside implementation/deployment packages when adjacency is useful.

They are indexed through `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`.

The documentation validator inventories README files beneath `implementation/` and `infrastructure/` and requires indexed discoverability. These README files remain supporting implementation documentation and cannot become hidden higher architecture/governance/current-state authority.

## Tooling changes

- MkDocs uses `docs_dir: docs` directly.
- Historical mixed-source `tools/assemble_docs.py` is retired.
- `tools/documentation_readiness.py` uses `docs/milestones/`.
- `tools/catch_me_up.py` uses consolidated CURRENT, roadmap, operations, milestone, and session paths.
- `tools/system_registry_docs.py` uses the consolidated operational-state output path.
- documentation-sensitive CI/workflows use consolidated paths.
- `tools/validate_documentation_control.py` rejects retired roots, validates required control records, ADR reconciliation, MkDocs source, continuity paths, implementation-local README indexing, and the J-405/archived-Article-VII reconciliation.

## Remaining work

Before PR #161 may leave draft status:

1. complete the final current-use/plain-text path audit tracked by MIG-DOC-007 while preserving intentionally historical path text;
2. confirm strict MkDocs and broader CI remain green after the J-405 reconciliation;
3. refetch and reconcile the latest `feature/jason-runtime-service` branch immediately before merge/retargeting; and
4. perform final PR review and remove draft status only after those checks pass.

No unresolved constitutional/governance disposition remains in this documentation workstream.

## Production/host boundary

This workstream did **not**:

- restart or rebuild Jason runtime;
- modify OpenClaw or its bridge;
- alter production provider credentials;
- change OpenBao configuration;
- add/remove authority grants;
- change System Registry declared state or lifecycle;
- remediate live Teams behavior; or
- make a host deployment.

Any future statement about live production state must come from fresh Git/System Registry/host evidence rather than this historical documentation record.
