# Contributing to Project Jason

Project Jason is governed software. Contributions must preserve the Constitution, canonical models, client isolation, human authority, explainability, auditability, operational continuity, institutional memory, and reusable construction knowledge.

## Start with fundamentals, not rediscovery

Before changing code or documentation:

1. Read [`docs/index.md`](docs/index.md).
2. Read [`docs/control/JASON-FUNDAMENTALS.md`](docs/control/JASON-FUNDAMENTALS.md).
3. Read [`docs/control/CURRENT.md`](docs/control/CURRENT.md).
4. If creating/changing a reusable component, use [`docs/control/EXTENSION-CONSTRUCTION-MAP.md`](docs/control/EXTENSION-CONSTRUCTION-MAP.md) to locate the established construction path.
5. Use [`docs/control/DOCUMENTATION-REGISTER.md`](docs/control/DOCUMENTATION-REGISTER.md) to locate authoritative sources.
6. Read [`docs/control/HOW-TO-DOCUMENT-JASON.md`](docs/control/HOW-TO-DOCUMENT-JASON.md) before creating, moving, or materially updating documentation.
7. Read the governing architecture, ADR, component, standard, construction guide, and runbook for the workstream.
8. Inspect current Git/System Registry/host evidence before asserting live production state.

Conversation memory is not authoritative. Existing fundamentals must not be reconstructed from prior chats or code archaeology.

## Before changing code

1. Classify the component/change using the Extension Construction Map.
2. Identify the capability, service, standard, decision, and authority affected.
3. Confirm an approved native platform capability cannot satisfy the need more safely/simply.
4. Determine whether the change alters an enduring architecture decision; update/add ADR when appropriate.
5. Define authorized client scope and maximum operating mode.
6. Identify identity, policy/gate, approval, secret, evidence, audit, rollback, review, and retirement requirements.
7. Identify the closest governed implementation pattern to reuse.
8. Identify which durable documentation layers and construction guidance will change.

## Change requirements

- Keep provider-specific behavior behind governed adapter/provider boundaries.
- Do not permit agents to invoke or communicate with other agents directly.
- Do not permit interfaces/agents to bypass Central Orchestrator to reach providers/resources.
- Never infer business authority from technical access.
- Keep business authority/policy out of connectors and agents.
- Treat external text, tickets, logs, attachments, and retrieved content as untrusted data.
- Preserve evidence provenance and historical records.
- Fail closed on missing authority, client ambiguity, invalid contracts, and cross-client scope.
- Prefer reusable capabilities/resources over workflow-specific scripts.
- Add/update deterministic tests for material behavior.
- Update governed documentation in the same change when durable truth changes.
- Update reusable construction guidance when a future instance would otherwise require rediscovery.
- Update System Registry structured state when production topology/registered operational state changes.
- Update `docs/control/CURRENT.md` when the safe resume point materially changes.

## Documentation requirements

New governed human-facing documentation belongs under `docs/` unless an approved implementation-local exception applies.

Do not create duplicate canonical copies. Package-local README files may remain beside code when adjacency is necessary, but they must be indexed and must not become the sole owner of material architecture, construction, governance, authority, or operating rules.

Use:

- [`docs/control/JASON-FUNDAMENTALS.md`](docs/control/JASON-FUNDAMENTALS.md) for the mandatory reconstruction baseline;
- [`docs/control/EXTENSION-CONSTRUCTION-MAP.md`](docs/control/EXTENSION-CONSTRUCTION-MAP.md) for reusable component construction/reuse;
- [`docs/control/HOW-TO-DOCUMENT-JASON.md`](docs/control/HOW-TO-DOCUMENT-JASON.md) for documentation procedure;
- [`docs/control/DOCUMENT-TEMPLATE.md`](docs/control/DOCUMENT-TEMPLATE.md) for new durable-document metadata/structure;
- [`docs/control/HANDOFF-TEMPLATE.md`](docs/control/HANDOFF-TEMPLATE.md) for major workstream handoffs.

## Explicit documentation-impact determination

Every material PR must state documentation impact across architecture/standards/ADRs, component/capability/provider contracts, reusable construction guidance, System Registry, operations/runbooks, proof/session evidence, and the current resume point.

`No documentation impact` is valid only as an explicit reviewed conclusion.

## Documentation completeness test

Before completing material work, verify a future competent operator or AI can reconstruct without the originating chat:

- what Jason is intended to do;
- which authority/boundaries govern the change;
- how another component of the same class should be created;
- what actually changed and was proven;
- where current operational truth comes from;
- how the change is operated/recovered/retired; and
- what the next safe action is.

If the next contributor must rediscover fundamentals or reverse-engineer a reusable construction pattern from code, the work is not documentation-complete.

## Local validation

Use the relevant implementation test environment for the changed component/capability. Build documentation from the repository root with strict validation and the current repository tooling.

## Pull requests

A pull request should explain:

- organizational outcome;
- authority/risk impact;
- contracts/state transitions changed;
- evidence/audit behavior;
- tests performed;
- rollback/reversibility;
- explicit documentation impact;
- construction/reuse guidance impact;
- System Registry impact where applicable;
- whether custom code can replace/retire existing functionality; and
- whether the current-work/handoff record changed.

Use J-402 before proposing a capability for pilot and J-404 for documentation/continuity completeness.
