# J-404 — Documentation Governance and Continuity

**Version:** 0.4  
**Status:** Active  
**Owner:** Jason Architecture Authority  
**Applies to:** Project Jason documentation, operational records, architecture records, implementation records, evidence references, generated documentation, session continuity, and reusable extension/construction knowledge

## Purpose

Jason must be reconstructable, operable, **and extensible** without relying on the memory of a person, AI system, chat session, or development session. This standard defines how Jason documentation is organized, authored, updated, retired, and used so project knowledge remains durable, discoverable, internally consistent, reviewable, and reusable.

The goal is not merely to publish readable documentation. The goal is to preserve institutional memory and operating/construction knowledge as governed project assets.

## 1. Single documentation control plane

The repository `docs/` directory is Jason's single human-facing documentation control plane.

A contributor, operator, auditor, or future AI system beginning with `docs/index.md` must be able to discover:

- why Jason exists;
- which constitutional and governance rules apply;
- Jason's non-negotiable architectural fundamentals;
- the current architecture and canonical models;
- detailed implementation-engineering architecture;
- how to create another component of each reusable Jason component class without rediscovering fundamentals;
- component and capability contracts;
- approved standards and ADRs;
- current operational topology and verification sources;
- operating procedures and runbooks;
- current work and resume instructions;
- durable session and proof records;
- material implementation-local documentation through a governed index;
- milestone and roadmap state; and
- which records are historical or superseded.

New governed human-facing documentation shall be created under `docs/` unless an approved implementation-local exception applies.

The canonical structure is:

```text
docs/
  index.md
  control/
  foundation/
  governance/
  architecture/
  engineering/
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

Repository-root `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` may remain conventional entry/control files, but they must direct durable project knowledge into the `docs/` control plane rather than becoming parallel documentation authorities.

## 2. One fact, one authoritative owner

A material fact shall have one authoritative source.

Other documents may reference or summarize that fact, but they must not create a competing source of truth.

Examples:

- constitutional rules are owned by the Constitution and approved governance records;
- enduring platform architecture is owned by canonical architecture records and project ADRs;
- implementation-engineering architecture is owned by engineering records subordinate to platform architecture;
- current production topology and lifecycle state are owned by the System Registry and its governed lifecycle history;
- deployment procedures are owned by operational runbooks;
- implementation behavior is owned by versioned code, schemas, and tests;
- reusable construction knowledge is owned by the appropriate engineering/construction guide and indexed from `docs/control/EXTENSION-CONSTRUCTION-MAP.md`;
- proof that an event occurred is owned by durable evidence/session records;
- current work sequencing is owned by the canonical current-work record.

When a summary would duplicate volatile facts such as container hashes, runtime versions, lifecycle counts, or deployed state, prefer a reference to the authoritative source rather than copying the values.

## 3. Authority hierarchy

When documentation appears to conflict, interpret sources in this order unless a more specific governing record explicitly defines otherwise:

1. Jason Constitution and approved constitutional amendments.
2. Approved governance rules and project architecture decision records.
3. Approved canonical architecture, canonical models, and engineering standards.
4. System Registry declared state, append-only lifecycle history, and observed verification evidence for operational topology.
5. Component, capability, provider, infrastructure, construction, and implementation-engineering specifications.
6. Operational runbooks and deployment records.
7. Durable proof and session records.
8. Current-work and handoff records.
9. Generated documentation and published representations.
10. Conversation history, informal notes, or model memory.

Lower-order material must never silently override higher-order authority.

## 4. Fundamentals baseline

Jason shall maintain `docs/control/JASON-FUNDAMENTALS.md` as a mandatory reconstruction/startup index.

The fundamentals baseline does not create new authority. It points future sessions to the authoritative owners of Jason's mission, governance, orchestration, identity/authority, capabilities/resources, providers/connectors, policy/gates, evidence, secrets, System Registry, documentation, platform integrity, and integrate-before-innovate rules.

A material workstream shall load that baseline before proposing architecture or creating/changing an extensible component.

Fundamentals shall not be reconstructed from chat memory or reverse-engineered from whichever code path is most convenient.

## 5. Extension/construction continuity

Jason shall maintain `docs/control/EXTENSION-CONSTRUCTION-MAP.md` as the discovery map for reusable component construction knowledge.

At minimum it shall classify and point to construction guidance for:

- providers/connectors;
- capabilities/resources;
- agents/reasoning components;
- governance/policy/approval gates;
- ingress/interfaces;
- identity/authority components;
- secret/credential integrations;
- internal/runtime services;
- System Registry entities/verification methods;
- evidence/audit components; and
- deployment/operational procedures.

A reusable component pattern is not documentation-complete if a future competent contributor must rediscover its fundamental boundaries or reverse-engineer how to create the next instance from code alone.

If implementation work reveals a missing reusable prerequisite or undocumented construction pattern, that condition is a documentation defect. The owning construction guidance and construction map shall be updated before the workstream closes.

## 6. Operational truth is not manually reconstructed

Current production topology shall not be maintained by repeatedly copying host observations into narrative documents.

The System Registry remains the authoritative machine-readable source for registered production components, capabilities, providers, dependencies, identity bindings, governance gates, credential references, deployments, declared state, observed state, verification methods, and effective lifecycle.

Human-readable operational-state documentation should be generated from, or directly reference, that structured truth.

Documentation may explain the meaning of operational state, but it must not become an independent operational inventory.

## 7. Current-work continuity

Jason shall maintain one canonical human-readable resume point at:

`docs/control/CURRENT.md`

That record shall describe:

- the active workstream;
- the last completed durable milestone or bounded step;
- unresolved blockers or risks;
- the next safe work items;
- required evidence sources to inspect before continuing; and
- any host-sensitive work that must not be inferred while the operator is away from the Jason host.

`CURRENT.md` shall not duplicate large quantities of volatile production state. It shall reference System Registry state, runbooks, proof records, branches, PRs, or evidence locations instead.

When a workstream materially changes, `CURRENT.md` must be updated in the same governed change or immediately following durable proof.

A stale `CURRENT.md` that directs a future session to an already-completed branch/PR/workstream is a documentation-control defect.

## 8. Required durable-document metadata

New durable governance, architecture, standard, component, runbook, decision, milestone, proof, or construction records should identify, where applicable:

- document identifier and title;
- status;
- version;
- owner or steward;
- authority or governing references;
- scope;
- canonical source designation;
- supersedes / superseded-by relationship;
- last reviewed date or review interval;
- evidence references; and
- security or data-handling constraints.

A document must not claim to be current or verified merely because it exists in the repository.

## 9. Session and proof records

Conversation history is not institutional memory.

A development or operations session that produces a durable decision, implementation change, deployment, verification, exception, reconciliation, or important failed proof shall produce or update a durable repository record when the information would be needed to reconstruct what happened later.

Session/proof records shall preserve:

- purpose;
- authority;
- exact bounded result;
- what was and was not changed;
- evidence references;
- failure classifications when relevant;
- follow-up requirements; and
- links to the canonical architecture, runbook, component, capability, or construction guidance affected.

Secrets and prohibited credential material shall never be copied into these records.

## 10. Handoff standard

A handoff must be reproducible without access to the originating chat.

Use `docs/control/HANDOFF-TEMPLATE.md` for major workstream handoffs.

A handoff should distinguish:

- repository state;
- documented intended state;
- observed/verified runtime state;
- unresolved uncertainty;
- safe next action; and
- work that requires the physical Jason host.

Inference must be labeled as inference. Missing evidence must be labeled as missing rather than filled from memory.

## 11. Documentation migration and path changes

The historical documentation roots have been consolidated beneath `docs/`. The authoritative historical mapping is retained in `docs/control/DOCUMENTATION-REGISTER.md`.

Future documentation path changes must preserve one editable canonical owner, links/navigation/tooling, material history, and CI enforcement. Historical append-only evidence must not be rewritten merely because paths move.

## 12. Implementation-local documentation

README files that are inseparable from code, schemas, deployment packages, connector packages, or test harnesses may remain adjacent to implementation.

Such README files are implementation documentation, not the project documentation control plane. Material operational, construction, architectural, authority, security, or governance rules discovered there must also be represented by, or linked from, the appropriate governed document under `docs/`.

Every `README.md` beneath `implementation/` or `infrastructure/` shall be represented in `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md`. CI shall enforce index coverage.

Detailed engineering architecture that is broadly reusable across implementations belongs under `docs/engineering/`.

## 13. Generated documentation

Generated documentation remains derived and disposable under J-403.

MkDocs consumes the canonical `docs/` tree directly. Generated `site/`, `.build/`, reports, indexes, diagrams, and similar outputs remain non-authoritative and must not be hand-edited as sources of truth.

## 14. Staleness and drift

A document is stale when it claims a current condition that no longer matches its authoritative source.

When staleness is found:

- do not silently reinterpret the document;
- identify the authoritative source;
- correct or retire the stale claim;
- preserve evidence of material reconciliations where operational consequences exist; and
- prefer removing duplicated volatile facts over repeatedly updating copies.

Documentation drift is an operational defect when it can cause an operator or system to take an incorrect action.

A completed PR/workstream that leaves the canonical resume point, fundamentals index, or construction map materially stale is not documentation-complete.

## 15. Security and privacy

Documentation must never contain secret values, private keys, passwords, API keys, OAuth bearer tokens, OpenBao tokens, RoleIDs, SecretIDs, unseal material, or other prohibited credential material.

Credential references may identify logical secret names, governed providers, secret paths by reference, or retrieval mechanisms when required for operations, provided those references do not disclose secret values.

Sensitive client data should be minimized and referenced by governed evidence when possible.

## 16. Explicit documentation-impact determination

Every material implementation workstream or pull request shall make an explicit documentation-impact determination.

The determination shall consider at minimum:

- governing architecture/standard/ADR impact;
- component/capability/provider contract impact;
- construction/reuse guidance impact;
- System Registry impact;
- runbook/operational impact;
- evidence/session-record impact; and
- current resume-point impact.

"No documentation impact" is permitted only as an explicit reviewed conclusion. It must not be the accidental default caused by forgetting documentation.

## 17. Definition of documentation complete

A material change is not documentation-complete until:

- its authoritative governing/architecture/component/runbook record is updated where required;
- its reusable construction guidance is updated when the way future instances are built or constrained changed;
- `docs/control/EXTENSION-CONSTRUCTION-MAP.md` still points to a sufficient construction path for the affected component class;
- its operational-state implications are reflected in the System Registry when applicable;
- its durable proof or decision record exists when needed;
- `docs/control/CURRENT.md` is updated if the resume point changed;
- navigation/indexes locate the authoritative material;
- implementation-local documentation is indexed when material;
- superseded or conflicting documentation is retired, redirected, or explicitly classified; and
- a future competent human or AI can create the next component of the same class without rediscovering Jason's fundamentals from chat history or code archaeology.

## 18. Governing rule

Project knowledge shall not depend on remembering where a fact was discussed or how a previous implementation happened to be assembled.

Jason documentation shall be discoverable from one control plane, each material fact shall have one authoritative owner, current operational truth shall come from structured evidence rather than conversational memory, reusable component construction shall be documented and indexed, and every future session shall be able to reconstruct both the safe continuation path and the established method for extending Jason without re-deriving fundamental architecture.
