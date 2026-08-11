# Project Jason Documentation Migration Issues

**Status:** Active migration issue register  
**Owner:** Jason Architecture Authority  
**Purpose:** Preserve known documentation conflicts, ambiguities, and reference risks so migration work does not silently discard institutional history or create duplicate authority.

## Rules

- Do not resolve an authority conflict by deleting the inconvenient document.
- Do not renumber governed identifiers without checking inbound references and history.
- Do not maintain two editable canonical copies after a migration.
- Do not treat a publishing document as canonical merely because it already lives under `docs/`.
- Record a reconciliation decision before retiring conflicting material.

## Open issues

### MIG-DOC-001 — Duplicate ADR-004 identifier

**State:** Open — migration blocked pending reconciliation.

`05-ADR/` currently contains both:

- `ADR-004-Datto-RMM-Managed-Device-Authority.md`
- `ADR-004-Teams-Proactive-Messaging.md`

Both records describe material accepted decisions and must be preserved. They cannot both remain canonical under the same ADR identifier.

Required work:

1. audit inbound references to both records;
2. determine which record retains ADR-004 based on historical issuance/accepted references;
3. assign the other the next appropriate unique ADR identifier without colliding with ADR-005 or ADR-006;
4. update title, filename, inbound references, navigation, and any durable session/proof references;
5. record the renumbering as a documentation-governance correction, not an architectural decision change;
6. migrate the reconciled ADR set to `docs/decisions/`.

No ADR content should be substantively changed merely to solve the numbering collision.

### MIG-DOC-002 — Architecture authority overlap

**State:** Open — reconciliation required before moving `02-Architecture/`.

Two architecture locations exist:

- `02-Architecture/` containing J-series canonical architecture records such as J-100 through J-103;
- `docs/architecture/` containing blueprint/catalog/deployment/core-services/foundation-build documents.

Required work:

- classify each `docs/architecture/` record as canonical, supporting, historical, superseded, or merge candidate;
- ensure no blueprint document silently overrides approved J-series architecture;
- preserve useful historical design context;
- consolidate approved canonical architecture under `docs/architecture/`.

### MIG-DOC-003 — Governance authority overlap

**State:** Open — reconciliation required before moving `01-Governance/`.

Governance-related material exists in:

- `docs/foundation/` after Foundation migration;
- legacy `01-Governance/`;
- existing `docs/governance/`.

Required work:

- establish the relationship between constitutional/Foundation authority, decision architecture, and `ARTICLE_VII_PLATFORM_INTEGRITY.md`;
- prevent duplicated constitutional requirements from becoming competing editable authority;
- consolidate approved governance material under `docs/governance/` while preserving Foundation as higher authority.

### MIG-DOC-004 — Duplicate roadmap roots

**State:** Open — reconciliation required before roadmap migration.

Both `06-Roadmaps/` and `07-Roadmap/` exist.

Required work:

- inventory both roots;
- classify current vs historical roadmaps;
- eliminate duplicate roadmap authority;
- consolidate active governed future-work records under `docs/roadmaps/`;
- archive superseded plans rather than deleting history.

### MIG-DOC-005 — Operations and proof-record mixing

**State:** Open.

`07-Operations/` contains operational procedures, deployment records, generated current-state documentation, and bounded proof records.

Target classification:

- repeatable runbooks/procedures -> `docs/operations/`;
- historical live proof/reconciliation evidence -> `docs/sessions/`;
- generated current operational-state representation -> generated from System Registry and clearly marked derived;
- durable architecture/decision content discovered in operations -> move or reference the governing architecture/ADR rather than leaving operations as authority.

### MIG-DOC-006 — Legacy CURRENT checkpoint

**State:** Open — canonical replacement established.

`docs/control/CURRENT.md` is now the canonical resume point for documentation/current-work continuity.

Legacy `08-Session-Records/CURRENT.md` contains valuable historical CAP-007/Teams/runtime context but must no longer appear to be the active resume record after session migration.

Required work:

- preserve it as a historical session/checkpoint record under `docs/sessions/` or `docs/archive/`;
- mark it Historical/Superseded by `docs/control/CURRENT.md`;
- update inbound references that intend the current resume point.

### MIG-DOC-007 — Inbound-reference audit for migrated roots

**State:** Open until CI and repository path audit are clean.

The following low-conflict roots have begun moving into the consolidated tree:

- Foundation -> `docs/foundation/`
- Canonical Models -> `docs/models/`
- Standards -> `docs/standards/`
- Architecture Journal -> `docs/journal/`
- Milestones -> `docs/milestones/`

Required work:

- use CI/MkDocs and repository path auditing to identify stale links/references;
- update references to canonical new paths;
- retain old path text only when intentionally describing historical repository state;
- do not re-create legacy canonical copies just to satisfy stale references.

### MIG-DOC-008 — Documentation tooling transition

**State:** In progress.

MkDocs currently uses a generated `.build/docs` workspace assembled from both consolidated and transitional legacy roots.

End state:

- canonical human documentation lives directly under `docs/`;
- MkDocs publishes from the consolidated structure without mixed canonical/publishing semantics;
- `tools/assemble_docs.py` is retired or reduced to a clearly justified generated-artifact role;
- release/documentation readiness tooling uses consolidated paths;
- CI prevents future documentation fragmentation.

## Resolved issues

None yet. Move an issue here only after the durable reconciliation is committed and references/tooling have been validated.
