# ADR-008 — Consolidate Governed Human Documentation Under `docs/`

**Status:** Accepted for implementation on the documentation-standardization branch; governing when merged  
**Date:** 2026-08-11  
**Decision owner:** Jason Architecture Authority  
**Supersedes:** ADR-002 — Preserve the Canonical Documentation Hierarchy

## Context

ADR-002 correctly protected Jason from allowing MkDocs or another publishing tool to dictate repository architecture. It established important invariants: canonical knowledge must have one authoritative source, generated documentation must remain disposable, and duplicate editable canonical copies are prohibited.

Subsequent implementation and operations exposed a different continuity problem.

Jason's governed human-facing knowledge accumulated across many numbered top-level directories, `docs/architecture`, `docs/governance`, operational records, session records, implementation-local README files, generated documentation, and conversation handoffs. The information was present, but a future human or AI session needed prior knowledge of the repository's historical layout to determine where authority lived and how work should resume.

That fragmentation conflicts with Jason's institutional-memory and continuity goals. The problem is not MkDocs. The problem is discoverability and reconstruction of governed project knowledge.

The System Registry work also sharpened the distinction between narrative documentation and operational truth: current production topology must come from structured declared/observed/verified state, while human documentation must explain, govern, and index that state without creating a competing inventory.

## Decision

Jason will consolidate governed **human-facing** project documentation under one repository control plane:

`docs/`

The consolidation is an institutional-memory and governance decision, not a documentation-generator requirement.

The target structure is:

```text
docs/
  index.md
  control/
  foundation/
  governance/
  architecture/
  models/
  components/
  standards/
  decisions/
  roadmaps/
  operations/
  sessions/
  journal/
  milestones/
  archive/
```

### Canonical-source rule

Each material fact continues to have one authoritative owner.

Migration shall move or reconcile canonical sources; it shall not maintain parallel editable copies in old and new locations.

### Structured operational truth

Machine-readable operational sources remain adjacent to implementation where they are executed and validated. In particular, System Registry manifests, lifecycle history, schemas, verification plans, and implementation remain under `implementation/kernel/system_registry/`.

They are indexed and governed from `docs/`, but are not copied into narrative documentation as a second inventory.

### Implementation-local documentation

README files or technical notes that are inseparable from a package, connector, schema, deployment artifact, or test harness may remain beside implementation when adjacency is useful.

Material architecture, authority, governance, or operating rules discovered there must be represented by or indexed from the appropriate governed document under `docs/`.

### Publishing independence

MkDocs remains replaceable. The decision does not require MkDocs, Material, Python, GitHub, or any particular publishing platform.

Once migration is complete, a publishing implementation should consume the canonical `docs/` tree directly when practical. Generated publishing output remains non-authoritative under J-403.

## Documentation control records

The consolidated control plane shall include durable records that future sessions can use without chat history:

- `docs/index.md` — entry point;
- `docs/control/CURRENT.md` — canonical human-readable resume point;
- `docs/control/DOCUMENTATION-REGISTER.md` — authority and migration/source map;
- `docs/control/HOW-TO-DOCUMENT-JASON.md` — repeatable documentation method for future human and AI sessions;
- `docs/control/HANDOFF-TEMPLATE.md` — durable workstream handoff format;
- `docs/control/DOCUMENT-TEMPLATE.md` — common durable-document metadata/structure;
- `docs/standards/J-404-Documentation-Governance-and-Continuity.md` — documentation governance standard.

## Migration requirements

Migration must be governed and reversible in Git history.

For each category:

1. identify the authoritative source and any overlapping or conflicting records;
2. reconcile authority before deleting or retiring conflicting material;
3. move the canonical source into the target `docs/` category;
4. update navigation, links, CI, release gates, and tooling in the same migration sequence;
5. preserve historical/superseded records under `docs/archive/` or another explicitly historical location;
6. do not create a second editable canonical copy;
7. fail validation on missing required documentation-control records;
8. retain secrets outside documentation.

Historical path references may remain when they intentionally describe past repository state, but must not be presented as current locations.

## Consequences

### Positive

- A future contributor can begin at one directory and discover Jason's governance, architecture, operating procedures, proof history, and current resume point.
- Documentation practices become teachable and repeatable through a durable how-to guide rather than conversational convention.
- Legacy duplicate categories can be reconciled instead of accumulating indefinitely.
- Current work and historical proof become distinct.
- Documentation publishing becomes simpler after migration while remaining replaceable.
- The System Registry remains clearly separated from narrative documentation as the source of current operational topology.

### Costs and risks

- Existing repository paths must change.
- Stale links and plain-text path references require audit and correction.
- Some historical records contain identifier or authority conflicts that must be reconciled before migration.
- Large moves can create noisy diffs even when document content is unchanged.
- Concurrent feature branches may continue creating legacy-path documentation until the new standard is merged and adopted.

These risks are managed through Git history, staged migration, strict documentation builds, a migration issue register, and a draft PR rather than an immediate destructive rewrite of the active development branch.

## Relationship to ADR-002

ADR-002 is superseded because its conclusion that the numbered top-level hierarchy should remain the permanent canonical documentation layout no longer best serves Jason's continuity requirements.

Its core rationale is retained:

- no documentation tool defines Jason's authority;
- no duplicate editable canonical sources;
- generated outputs remain disposable;
- publishing remains replaceable;
- migration must protect institutional memory.

ADR-008 changes the canonical physical organization because operating evidence now shows that one discoverable documentation control plane better preserves those same principles.

## Retirement criteria

This decision may be superseded if a future documentation storage model provides stronger continuity, portability, versioning, discoverability, and authority guarantees without making any external publishing/search/AI system the canonical owner.

Any replacement must preserve one authoritative source per material fact, durable session reconstruction, System Registry separation, tool independence, and human-readable portability.
