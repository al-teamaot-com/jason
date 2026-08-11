# J-404 — Documentation Governance and Continuity

**Version:** 0.2  
**Status:** Proposed — effective when merged into the authoritative development branch  
**Owner:** Jason Architecture Authority  
**Applies to:** Project Jason documentation, operational records, architecture records, implementation records, evidence references, generated documentation, and session continuity

## Purpose

Jason must be reconstructable and operable without relying on the memory of a person, AI system, chat session, or development session. This standard defines how Jason documentation is organized, authored, updated, retired, and used so project knowledge remains durable, discoverable, internally consistent, and reviewable.

The goal is not merely to publish readable documentation. The goal is to preserve institutional memory and operating knowledge as governed project assets.

## 1. Single documentation control plane

The repository `docs/` directory is Jason's single human-facing documentation control plane.

A contributor, operator, auditor, or future AI system beginning with `docs/index.md` must be able to discover:

- why Jason exists;
- which constitutional and governance rules apply;
- the current architecture and canonical models;
- detailed implementation-engineering architecture;
- component and capability contracts;
- approved standards and ADRs;
- current operational topology and verification sources;
- operating procedures and runbooks;
- current work and resume instructions;
- durable session and proof records;
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
- proof that an event occurred is owned by durable evidence/session records;
- current work sequencing is owned by the canonical current-work record.

When a summary would duplicate volatile facts such as container hashes, runtime versions, lifecycle counts, or deployed state, prefer a reference to the authoritative source rather than copying the values.

## 3. Authority hierarchy

When documentation appears to conflict, interpret sources in this order unless a more specific governing record explicitly defines otherwise:

1. Jason Constitution and approved constitutional amendments.
2. Approved governance rules and project architecture decision records.
3. Approved canonical architecture, canonical models, and engineering standards.
4. System Registry declared state, append-only lifecycle history, and observed verification evidence for operational topology.
5. Component, capability, provider, infrastructure, and implementation-engineering specifications.
6. Operational runbooks and deployment records.
7. Durable proof and session records.
8. Current-work and handoff records.
9. Generated documentation and published representations.
10. Conversation history, informal notes, or model memory.

Lower-order material must never silently override higher-order authority.

## 4. Operational truth is not manually reconstructed

Current production topology shall not be maintained by repeatedly copying host observations into narrative documents.

The System Registry remains the authoritative machine-readable source for registered production components, capabilities, providers, dependencies, identity bindings, governance gates, credential references, deployments, declared state, observed state, verification methods, and effective lifecycle.

Human-readable operational-state documentation should be generated from, or directly reference, that structured truth.

Documentation may explain the meaning of operational state, but it must not become an independent operational inventory.

## 5. Current-work continuity

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

## 6. Required durable-document metadata

New durable governance, architecture, standard, component, runbook, decision, milestone, or proof records should identify, where applicable:

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

## 7. Session and proof records

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
- links to the canonical architecture, runbook, component, or capability affected.

Secrets and prohibited credential material shall never be copied into these records.

## 8. Handoff standard

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

## 9. Documentation migration and path changes

The numbered historical documentation roots and the former top-level engineering `architecture/` tree have been consolidated beneath `docs/` on the documentation-standardization branch. The authoritative historical mapping is retained in `docs/control/DOCUMENTATION-REGISTER.md`.

Future documentation path changes must follow these rules:

1. Identify the current authoritative source and all material inbound references.
2. Preserve Git history where practical.
3. Update internal links, MkDocs navigation, CI checks, tooling, release gates, and operator-facing path references in the same governed change sequence.
4. Leave a redirect/stub only when required for compatibility and document its retirement criterion.
5. Never maintain two editable canonical copies.
6. Archive superseded records rather than deleting institutional history unless retention is prohibited.
7. Record material path/authority changes in the Documentation Register or a governed decision record.
8. CI shall reject re-creation of retired human-documentation roots unless an approved decision explicitly reintroduces one.

Path consolidation does not justify rewriting historical evidence. When an append-only evidence record contains a historical repository path, generated current documentation may resolve that reference to the new canonical location while preserving the original event unchanged.

## 10. Implementation-local documentation

README files that are inseparable from code, schemas, deployment packages, connector packages, or test harnesses may remain adjacent to implementation.

Such README files are implementation documentation, not the project documentation control plane. Material operational or architectural rules discovered there must also be represented by, or linked from, the appropriate governed document under `docs/`.

Implementation-local documentation must not quietly introduce architecture, authority, or governance rules that are absent from canonical documentation.

Detailed engineering architecture that is broadly reusable across implementations belongs under `docs/engineering/`, not in a scattered top-level architecture tree.

## 11. Generated documentation

Generated documentation remains derived and disposable under J-403.

MkDocs consumes the canonical `docs/` tree directly. Generated `site/`, `.build/`, reports, indexes, diagrams, and similar outputs remain non-authoritative and must not be hand-edited as sources of truth.

If a future publishing system requires staging or transformation, the staging output must remain deterministic, disposable, and subordinate to `docs/`.

## 12. Staleness and drift

A document is stale when it claims a current condition that no longer matches its authoritative source.

When staleness is found:

- do not silently reinterpret the document;
- identify the authoritative source;
- correct or retire the stale claim;
- preserve evidence of material reconciliations where operational consequences exist; and
- prefer removing duplicated volatile facts over repeatedly updating copies.

Documentation drift is an operational defect when it can cause an operator or system to take an incorrect action.

## 13. Security and privacy

Documentation must never contain secret values, private keys, passwords, API keys, OAuth bearer tokens, OpenBao tokens, RoleIDs, SecretIDs, unseal material, or other prohibited credential material.

Credential references may identify logical secret names, governed providers, secret paths by reference, or retrieval mechanisms when required for operations, provided those references do not disclose secret values.

Sensitive client data should be minimized and referenced by governed evidence when possible.

## 14. Definition of documentation complete

A material change is not documentation-complete until:

- its authoritative governing/architecture/component/runbook record is updated where required;
- its operational-state implications are reflected in the System Registry when applicable;
- its durable proof or decision record exists when needed;
- `docs/control/CURRENT.md` is updated if the resume point changed;
- navigation/indexes locate the authoritative material;
- implementation-local documentation is indexed when material; and
- superseded or conflicting documentation is retired, redirected, or explicitly classified.

## 15. Governing rule

Project knowledge shall not depend on remembering where a fact was discussed.

Jason documentation shall be discoverable from one control plane, each material fact shall have one authoritative owner, current operational truth shall come from structured evidence rather than conversational memory, and every future session shall be able to reconstruct the safe continuation path from durable records.
