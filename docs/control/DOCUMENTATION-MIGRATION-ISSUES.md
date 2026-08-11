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

### MIG-DOC-003 — Historical Platform Integrity “Article VII” conflicts with current Constitution numbering

**State:** Open — authority conflict contained, formal disposition still required.

`docs/governance/ARTICLE_VII_PLATFORM_INTEGRITY.md` labels itself an approved constitutional Article VII, while the current authoritative `docs/foundation/J-002-Constitution.md` defines Article VII as **Knowledge as an Asset**.

The conflict is currently contained by `docs/governance/README.md`:

- J-002 is higher authority;
- the Platform Integrity document must not be treated as current Constitution Article VII;
- non-conflicting requirements may be used only as supporting governance context;
- unique durable requirements should be reconciled into the appropriate canonical Constitution, architecture, standard, or governance owner before the historical record is archived or retired.

Remaining work requires deliberate constitutional/governance review rather than an offline path-only cleanup.

### MIG-DOC-005 — Operations and historical proof classification

**State:** Open — physical consolidation complete; semantic classification remains.

The former `07-Operations/` tree is now under `docs/operations/`, but it contains a mixture of:

- repeatable runbooks/procedures;
- deployment records;
- live pilot proof records;
- generated current-state documentation;
- bounded operational evidence summaries.

Target classification:

- repeatable runbooks/procedures -> remain in `docs/operations/`;
- bounded historical proof/reconciliation evidence -> `docs/sessions/`;
- generated current operational-state representation -> remain clearly marked generated/derived from System Registry structured truth;
- durable architecture/decision content -> reference or update the governing architecture/ADR rather than treating an operations record as higher authority.

This cleanup should preserve historical references and evidence identity; it must not rewrite a proof record into a current runbook.

### MIG-DOC-007 — Inbound-reference and plain-text path audit

**State:** Open until final consolidated-tree CI/path audit is green.

All historical numbered human-documentation roots have now been physically retired. Strict MkDocs validation catches Markdown link breakage, but plain-text references to old paths may remain intentionally or accidentally.

Required work:

- use CI/MkDocs to repair broken Markdown links;
- audit current operational/runbook/tooling references to retired paths;
- preserve old path text when it intentionally describes historical repository state;
- update old path text when it is intended to direct a current operator;
- do not recreate retired roots merely to satisfy stale references.

### MIG-DOC-009 — Implementation-local documentation index

**State:** Open — structural consolidation complete.

Implementation-local README files may remain beside code, connectors, deployment packages, and schemas when adjacency is useful. A final index/audit is needed to ensure no material architecture, governance, authority, or operating rule exists only in an unindexed implementation README.

The preferred outcome is not copying every README into `docs/`; it is making material implementation documentation discoverable and ensuring governed rules have canonical human-facing owners.

## Resolved / controlled issues

### MIG-DOC-001 — Duplicate ADR-004 identifier

**State:** Resolved structurally.

Historical order established that Datto RMM Managed-Device Authority was accepted first as ADR-004. Teams proactive messaging was created later using the same identifier.

Resolution:

- Datto RMM Managed-Device Authority retains `ADR-004`;
- Teams proactive messaging is corrected to `ADR-007`;
- ADR-007 contains an explicit identifier-correction note stating that architectural meaning was not changed;
- ADR-005 and ADR-006 remain unchanged;
- all ADRs are consolidated under `docs/decisions/`.

### MIG-DOC-002 — Architecture authority overlap

**State:** Controlled/resolved for migration.

J-100 through J-103 were moved into `docs/architecture/` and `docs/architecture/README.md` now defines their canonical subject ownership.

Earlier blueprint/catalog/core-services/deployment/foundation-build records remain as supporting foundational references and cannot silently override the Constitution, J-series architecture, approved ADRs, component specifications, or System Registry state.

### MIG-DOC-004 — Duplicate roadmap roots

**State:** Resolved.

The active capability register is now `docs/roadmaps/Jason-Capability-Register.md`.

The older `07-Roadmap/Jason-Roadmap.md` was preserved as `docs/archive/roadmaps/Jason-Roadmap-Historical.md` with explicit Historical/Superseded classification.

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
- the validator rejects recreation of retired numbered documentation roots;
- `tools/documentation_readiness.py` uses `docs/milestones/`.

### MIG-DOC-010 — Historical documentation-layout ADR conflict

**State:** Resolved through explicit supersession.

ADR-002 required the numbered top-level documentation hierarchy to remain canonical. Operational continuity evidence later demonstrated that repository fragmentation itself created reconstruction risk.

ADR-008 — Documentation Control Plane Consolidation — explicitly supersedes ADR-002 while retaining ADR-002's durable invariants:

- one authoritative source per material fact;
- no duplicate editable canonical copies;
- generated outputs remain disposable;
- documentation tools remain replaceable;
- institutional memory must be preserved during migration.
