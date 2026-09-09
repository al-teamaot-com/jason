# Jason

Jason is TeamAOT's governed operational platform and professional decision-support architecture.

Its mission is to help TeamAOT deliver dependable, secure, compliant, efficient, and consistent service to its clients while preserving human authority, architectural discipline, explainability, auditability, organizational attention, and institutional memory.

## Documentation

**Start with [`docs/index.md`](docs/index.md).**

The `docs/` tree is Jason's single human-facing documentation control plane. It explains where authoritative project knowledge lives, how documentation must be maintained, how to resume work safely, and how legacy documentation is being consolidated.

Important entry points:

- [`docs/control/CURRENT.md`](docs/control/CURRENT.md) — current human-readable resume point;
- [`docs/control/DOCUMENTATION-REGISTER.md`](docs/control/DOCUMENTATION-REGISTER.md) — authority/source map and migration register;
- [`docs/control/HOW-TO-DOCUMENT-JASON.md`](docs/control/HOW-TO-DOCUMENT-JASON.md) — required documentation practice for future human and AI sessions;
- [`docs/standards/J-404-Documentation-Governance-and-Continuity.md`](docs/standards/J-404-Documentation-Governance-and-Continuity.md) — documentation continuity/governance standard.

Do not rely on conversation history, a prior AI session, or remembered deployment details as authoritative project state.

## Operational truth

Current production topology and lifecycle state are governed through the System Registry under `implementation/kernel/system_registry/` and its verification/lifecycle evidence. Narrative documentation may explain or render that state, but must not maintain a competing operational inventory.

## Implementation

Executable code, schemas, tests, connectors, runtime composition, and implementation-local READMEs remain under `implementation/` and infrastructure directories where adjacency is useful.

Implementation-local documentation does not replace governed project documentation. Any material architecture, authority, operating rule, or durable procedure must be represented by or indexed from `docs/`.

## Governing boundaries

- Human and organizational authority remain explicit; technical access does not create business authority.
- Agents and connectors never coordinate directly with one another.
- All governed coordination and consequential execution pass through the Central Orchestrator.
- Capability/resource-driven orchestration is preferred over bespoke workflow scripts.
- Providers never self-select authority.
- Evidence comes before assertion.
- Missing authority, invalid contracts, ambiguous scope, or unsupported resolution fail closed.
- Secret values never belong in documentation, generated outputs, audit evidence, or chat handoffs.

## Documentation migration

Older numbered documentation roots are being migrated into `docs/` in governed stages. During migration, [`docs/control/DOCUMENTATION-REGISTER.md`](docs/control/DOCUMENTATION-REGISTER.md) identifies which source is currently authoritative and the retirement condition for legacy locations.

Do not create duplicate editable canonical copies while migration is in progress.

## Generated documentation

Generated `.build/` and `site/` outputs are disposable and must never become sources of authority. Publishing/search systems are consumers of Jason documentation, not owners of it.
