# Contributing to Project Jason

Project Jason is governed software. Contributions must preserve the Constitution, canonical models, client isolation, human authority, explainability, auditability, operational continuity, and institutional memory.

## Start with documentation context

Before changing code or documentation:

1. Read [`docs/index.md`](docs/index.md).
2. Read [`docs/control/CURRENT.md`](docs/control/CURRENT.md).
3. Use [`docs/control/DOCUMENTATION-REGISTER.md`](docs/control/DOCUMENTATION-REGISTER.md) to locate the authoritative source for the subject.
4. Read [`docs/control/HOW-TO-DOCUMENT-JASON.md`](docs/control/HOW-TO-DOCUMENT-JASON.md) before creating, moving, or materially updating documentation.
5. Read the governing architecture, ADR, component, standard, or runbook for the workstream.
6. Inspect current Git/System Registry/host evidence before asserting live production state.

Conversation memory is not an authoritative source.

## Before changing code

1. Identify the capability, service, standard, or decision affected.
2. Confirm that an approved native platform capability cannot satisfy the need more safely or simply.
3. Determine whether the change alters an enduring architectural decision. If it does, add or update an ADR.
4. Define the authorized client scope and maximum operating mode.
5. Identify evidence, audit, rollback, review, and retirement requirements.
6. Identify which durable documentation layers will change.

## Change requirements

- Keep provider-specific behavior behind adapter/provider boundaries.
- Do not permit agents to invoke or communicate with other agents directly.
- Never infer business authority from technical access.
- Treat external text, ticket descriptions, logs, attachments, and retrieved content as untrusted data.
- Preserve evidence provenance and historical records.
- Fail closed on missing authority, client ambiguity, invalid contracts, and cross-client scope.
- Prefer reusable capabilities/resources over workflow-specific scripts.
- Add or update deterministic tests for material behavior.
- Update governed documentation in the same change when durable truth changes.
- Update System Registry structured state when production topology or registered operational state changes.
- Update `docs/control/CURRENT.md` when the safe resume point materially changes.

## Documentation requirements

New governed human-facing documentation belongs under `docs/` unless the Documentation Register identifies a legacy canonical source that has not yet been migrated.

Do not create a duplicate canonical copy simply to move content into the new structure.

Implementation-local README files may remain beside code when adjacency is necessary, but they must not become the only place a material architecture, governance, authority, or operating rule exists.

Use:

- [`docs/control/HOW-TO-DOCUMENT-JASON.md`](docs/control/HOW-TO-DOCUMENT-JASON.md) for documentation procedure;
- [`docs/control/DOCUMENT-TEMPLATE.md`](docs/control/DOCUMENT-TEMPLATE.md) for new durable-document metadata/structure;
- [`docs/control/HANDOFF-TEMPLATE.md`](docs/control/HANDOFF-TEMPLATE.md) for major workstream handoffs.

## Documentation completeness test

Before completing material work, verify that a future competent operator or AI session could reconstruct:

- what Jason is intended to do;
- which authority governs the change;
- what actually changed;
- what was actually proven;
- where current operational truth comes from;
- how the change is operated/recovered; and
- what the next safe action is,

without access to the originating chat.

## Local validation

Use the relevant implementation test environment for the changed component/capability.

Build the documentation site from the repository root using the repository's documentation environment and strict validation. During documentation consolidation, follow the commands and path expectations in the active documentation tooling rather than assuming historical directory structure.

## Pull requests

A pull request should explain:

- the organizational outcome;
- the authority and risk impact;
- contracts or state transitions changed;
- evidence and audit behavior;
- tests performed;
- rollback or reversibility;
- documentation and ADR impact;
- System Registry impact where applicable;
- whether custom code can replace or retire existing functionality; and
- whether the current-work/handoff record changed.

Use J-402 — Capability Definition of Done before proposing a capability for pilot, and apply the documentation-completeness rules defined by J-404.
