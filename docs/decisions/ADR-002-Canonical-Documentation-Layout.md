# ADR-002 — Preserve the Canonical Documentation Hierarchy

**Status:** Superseded by ADR-008  
**Date:** 2026-07-31  
**Decision owner:** Jason Architecture Authority  
**Superseded:** 2026-08-11

## Supersession note

This decision correctly rejected duplicate canonical documents and documentation-tool-driven restructuring. It was superseded by ADR-008 after operational experience demonstrated a different architectural problem: human-facing project knowledge had become fragmented across many repository roots, publishing directories, session records, and implementation-local documentation, making safe reconstruction and future-session continuity unnecessarily dependent on knowing historical repository layout.

ADR-008 preserves this ADR's core invariants — one authoritative source, no duplicate editable canonical copies, deterministic publishing, and tool independence — while consolidating governed human-facing documentation under `docs/` as Jason's documentation control plane for institutional-memory and continuity reasons rather than to satisfy MkDocs.

The historical decision is retained below unchanged in substance.

## Context

Project Jason currently contains two documentation structures:

1. A numbered top-level hierarchy containing foundational, governance, architecture, component, standards, decision, roadmap, operations, session, and architecture-journal records.
2. A conventional `docs/` directory used as the MkDocs publishing entry point and for supporting architecture and governance documents.

The current MkDocs configuration sets the repository root as `docs_dir`. This conflicts with current MkDocs validation because the configuration file is located in that same directory and the generated `site/` directory is also placed within it.

Reorganizing all canonical documents beneath `docs/` would allow a conventional MkDocs layout, but it would make the documentation tool dictate Jason's repository architecture. It would also create unnecessary movement, broken references, and avoidable risk to institutional memory.

## Decision

The numbered top-level hierarchy is Jason's canonical documentation source of truth.

The `docs/` directory serves as:

- the publishing entry point;
- the location for publishing-specific supporting content;
- the location for documentation assets where appropriate.

The documentation publishing implementation must adapt to the canonical repository hierarchy.

Canonical documents shall not be duplicated or relocated solely to satisfy the expectations of a documentation generator.

Where the publishing tool cannot directly consume the canonical hierarchy, a deterministic build step may assemble a temporary documentation source tree from the canonical files.

Any such build step must:

- preserve the canonical files unchanged;
- avoid committing generated copies;
- fail when referenced source documents are missing;
- produce deterministic output;
- remain understandable and reversible;
- be validated in continuous integration.

## Consequences

- The numbered hierarchy remains authoritative.
- MkDocs remains an implementation detail rather than an architectural authority.
- Publishing may require a small staging or assembly step.
- Generated documentation trees must be excluded from source control.
- Navigation paths may need to be mapped from canonical source paths to temporary publishing paths.
- Future documentation tools can replace MkDocs without requiring the canonical hierarchy to change.

## Rejected alternatives

### Move all canonical documents into `docs/`

Rejected because it would allow the documentation tool to drive the repository architecture and would create unnecessary document movement and reference churn.

### Keep `docs_dir: .`

Rejected because the configuration is invalid under the current documentation build and includes the repository root as the documentation source.

### Pin an older MkDocs version

Rejected because it would conceal the structural incompatibility rather than correct it and would create unnecessary dependency stagnation.

### Maintain duplicate canonical documents under `docs/`

Rejected because duplicated records would undermine institutional memory, create ambiguity about authority, and risk documentation drift.
