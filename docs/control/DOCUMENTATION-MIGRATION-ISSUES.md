# Project Jason Documentation Migration Issues

**Status:** Active documentation reconciliation register  
**Owner:** Jason Architecture Authority  
**Purpose:** Preserve remaining documentation conflicts, ambiguities, and cleanup work so consolidation does not silently discard institutional history or create competing authority.

## Rules

- Do not resolve an authority conflict by deleting the inconvenient document.
- Do not renumber governed identifiers without preserving history and rationale.
- Do not maintain two editable canonical copies.
- Do not treat a file as authoritative merely because it is under `docs/`.
- Record material reconciliation before retiring conflicting authority.

## Open issues

### MIG-DOC-007 — Inbound-reference and plain-text path audit

**State:** Open — strict MkDocs/CI is green and known current-use path drift is repaired; final consolidated-tree plain-text audit remains.

All historical numbered human-documentation roots and the former top-level engineering `architecture/` tree have now been physically retired. Strict MkDocs validation catches Markdown link breakage, but plain-text references to old paths may remain intentionally or accidentally.

Completed during the current audit:

- strict MkDocs navigation was repaired and `Validate Jason` returned green;
- current operator references in the reusable IT Glue/Datto convergence runbook now point to `docs/operations/` and `docs/sessions/`;
- the migrated CAP-007 live-pilot proof now points to the current Teams proof under `docs/sessions/`;
- the session-record index now points to `docs/control/CURRENT.md` rather than implying a local session `CURRENT.md`.

Remaining work:

- continue auditing current operational/runbook/tooling references to retired paths;
- preserve old path text when it intentionally describes historical repository state;
- update old path text when it is intended to direct a current operator;
- do not recreate retired roots merely to satisfy stale references.

## Resolved / controlled issues

### MIG-DOC-001 — Duplicate ADR-004 identifier

**State:** Resolved structurally.

Historical order established that Datto RMM Managed-Device Authority was accepted first as ADR-004. Teams proactive messaging was created later using the same identifier.

Resolution:

- Datto RMM Managed-Device Authority retains `ADR-004`;
- Teams proactive messaging is corrected to `ADR-007`;
- ADR-007 contains an explicit identifier-correction note stating that architectural meaning was not changed;
- ADR-005 and ADR-006 remain unchanged;
- all project ADRs are consolidated under `docs/decisions/`.

### MIG-DOC-002 — Architecture authority overlap

**State:** Controlled/resolved for migration.

J-100 through J-103 were moved into `docs/architecture/` and `docs/architecture/README.md` now defines their canonical subject ownership.

Earlier blueprint/catalog/core-services/deployment/foundation-build records remain as supporting foundational references and cannot silently override the Constitution, J-series architecture, approved ADRs, component specifications, or System Registry state.

### MIG-DOC-003 — Historical Platform Integrity “Article VII” conflict

**State:** Resolved through deliberate governance disposition on 2026-08-11.

The historical `ARTICLE_VII_PLATFORM_INTEGRITY.md` labeled itself an approved constitutional Article VII, while the authoritative `docs/foundation/J-002-Constitution.md` defines Article VII as **Knowledge as an Asset**.

Resolution:

- the current J-002 Constitution and its Article VII remain unchanged;
- the historical Platform Integrity record was preserved as `docs/archive/governance/ARTICLE_VII_PLATFORM_INTEGRITY-Historical.md` with its original text retained as institutional evidence;
- its former constitutional label is explicitly historical and has no current constitutional authority;
- durable platform-integrity and boundary-enforcement requirements were extracted into `docs/standards/J-405-Platform-Integrity-and-Boundary-Enforcement.md` beneath the Constitution;
- J-405 preserves central orchestration, approved platform-contract, secrets, policy-separation, provider-boundary, client-isolation, integrate-before-innovate, exception, and production-readiness requirements at the correct standards layer;
- the reconciliation does not renumber, amend, or create a second Article VII.

### MIG-DOC-004 — Duplicate roadmap roots

**State:** Resolved.

The active capability register is now `docs/roadmaps/Jason-Capability-Register.md`.

Machine-readable roadmap status is now `docs/roadmaps/Jason-Roadmap-Status.json`.

The older narrative `07-Roadmap/Jason-Roadmap.md` was preserved as `docs/archive/roadmaps/Jason-Roadmap-Historical.md` with explicit Historical/Superseded classification.

### MIG-DOC-005 — Operations and historical proof classification

**State:** Resolved/controlled — semantic classification completed.

Resolution:

- `docs/operations/README.md` now defines the authority and classification boundary for operational documentation;
- repeatable runbooks, checklists, deployment/recovery procedures, deployment records, and the generated System Registry human view remain under `docs/operations/` with explicit authority boundaries;
- `OPS-ITGLUE-DATTO-LIVE-CONVERGENCE-PROOF.md` remains in operations because its primary content is a reusable observe-only proof/runbook with prerequisites, bounded discovery, positive and negative cases, evidence handling, and success criteria despite its historical filename;
- `CAP-007-Live-Pilot-Proof-2026-08-11.md` moved to `docs/sessions/` because its primary purpose is preserving point-in-time pilot and Teams integration evidence;
- the CAP-007 move preserved the proof's date, evidence identifiers, hashes, conclusions, and governance limitation while correcting only the current repository path to its related Teams proof;
- future point-in-time host proofs, pilot evidence, and reconciliation records belong in `docs/sessions/`; reusable procedures remain in `docs/operations/`;
- no documentation-classification change alters the authority or factual meaning of historical evidence.

### MIG-DOC-006 — Legacy CURRENT checkpoint

**State:** Resolved structurally.

`docs/control/CURRENT.md` is the only canonical current resume point.

The former session checkpoint is preserved as:

`docs/sessions/Legacy-CURRENT-2026-08-11.md`

It is historical context, not current runtime authority.

### MIG-DOC-008 — Documentation tooling transition

**State:** Resolved structurally.

- all governed human-facing documentation roots are now under `docs/`;
- MkDocs uses `docs_dir: docs` directly;
- `tools/assemble_docs.py` has been retired;
- documentation CI validates the control plane and builds directly from `docs/`;
- the validator rejects recreation of retired numbered documentation roots and the former top-level engineering `architecture/` tree;
- `tools/documentation_readiness.py` uses `docs/milestones/`.

### MIG-DOC-009 — Implementation-local documentation index

**State:** Resolved/controlled.

Implementation-local README files may remain beside code, connectors, deployment packages, and schemas when adjacency is useful, but they are supporting implementation documentation rather than hidden governance or architecture authority.

Resolution:

- `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` is the single discovery/control index for package-adjacent README files;
- the index names the governed human-facing owner or related records for each implementation-local document;
- `docs/index.md`, MkDocs navigation, the Documentation Register, and the documentation authoring guide expose the index;
- `tools/validate_documentation_control.py` inventories every `README.md` beneath `implementation/` and `infrastructure/` and fails if its repository-relative path is missing from the index;
- index presence proves discoverability only and does not grant governance, architecture, security, or current-state authority to a README.

Future implementation README additions must update the index in the same governed change.

### MIG-DOC-010 — Historical documentation-layout ADR conflict

**State:** Resolved through explicit supersession.

ADR-002 required the numbered top-level documentation hierarchy to remain canonical. Operational continuity evidence later demonstrated that repository fragmentation itself created reconstruction risk.

ADR-008 — Documentation Control Plane Consolidation — explicitly supersedes ADR-002 while retaining ADR-002's durable invariants:

- one authoritative source per material fact;
- no duplicate editable canonical copies;
- generated outputs remain disposable;
- documentation tools remain replaceable;
- institutional memory must be preserved during migration.

### MIG-DOC-011 — Separate top-level engineering architecture tree

**State:** Resolved structurally and by authority classification.

The historical repository-root `architecture/` tree contained JIS engineering guidance, provider engineering references, detailed capability/execution-policy/resolution design, and an engineering `ADR-000x` namespace.

Resolution:

- the complete engineering tree moved to `docs/engineering/`;
- `docs/engineering/README.md` defines it as detailed implementation-engineering architecture subordinate to the Constitution, project ADRs, and canonical J-series platform architecture;
- the historical engineering `ADR-000x` namespace is explicitly distinct from project ADRs under `docs/decisions/`;
- the old top-level `architecture/` tree is retired and CI rejects its re-creation.

### MIG-DOC-012 — Root governed TODO/backlog

**State:** Resolved structurally.

The repository-root `TODO.md` contained governed future work and therefore belonged in the documentation control plane rather than at repository root.

Resolution:

- moved to `docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md`;
- root `TODO.md` retired;
- documentation CI rejects re-creation of root `TODO.md`;
- MkDocs/navigation exposes the governed backlog from the roadmap section.

### MIG-DOC-013 — Conventional root README/CONTRIBUTING/SECURITY boundary

**State:** Controlled.

`README.md`, `CONTRIBUTING.md`, and `SECURITY.md` remain at repository root because they are conventional repository entry/control files used by GitHub and contributors.

They are not parallel durable documentation authorities:

- README directs readers to `docs/index.md`;
- CONTRIBUTING requires the governed documentation process and `HOW-TO-DOCUMENT-JASON.md`;
- SECURITY handles reporting/security invariants while directing durable architecture/current-state questions to governed documentation and System Registry evidence.
