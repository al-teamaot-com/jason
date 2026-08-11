# How to Document Project Jason

**Status:** Active documentation practice guide  
**Owner:** Jason Architecture Authority  
**Governing standard:** `docs/standards/J-404-Documentation-Governance-and-Continuity.md`  
**Purpose:** Give future human and AI work sessions one repeatable method for documenting Jason without creating duplicate authority, losing operational context, or depending on chat history.

## The rule to remember

Document the durable truth once, in the place that owns that truth, and link to it everywhere else.

Do not use chat history as the final record. Do not copy volatile runtime facts into multiple documents. Do not create a new document merely because you cannot remember where the existing one is.

Before writing, consult:

1. `docs/index.md` — documentation entry point.
2. `docs/control/DOCUMENTATION-REGISTER.md` — source/authority map and migration status.
3. This guide — how to classify and write the change.
4. The governing architecture, standard, ADR, runbook, or System Registry record for the subject.

## 1. Decide whether documentation is required

Create or update durable documentation when a change affects something a future operator, developer, reviewer, auditor, or AI system would need to reconstruct safely.

Usually document:

- a constitutional or governance rule;
- an architectural boundary or durable design decision;
- a new or changed capability, provider, component, interface, dependency, or identity binding;
- an operational procedure or recovery procedure;
- a production deployment or topology change;
- an authority/approval/security model change;
- a material failure and its durable lesson;
- a new source of operational truth;
- a verification or live proof that establishes a lifecycle state;
- a change to how Jason is built, deployed, tested, recovered, or resumed;
- a workstream checkpoint that would be costly to reconstruct from code and Git history alone.

Do not create durable documentation for transient debugging detail unless the detail explains a durable failure mode, decision, or recovery procedure.

## 2. Find the authoritative owner before writing

Ask: **What kind of truth is this?**

| Truth | Where it belongs |
|---|---|
| Why Jason exists / non-negotiable rule | `docs/foundation/` or `docs/governance/` |
| Enduring architecture / boundary | `docs/architecture/` |
| Provider-neutral organizational concept | `docs/models/` |
| Kernel/component/capability/infrastructure contract | `docs/components/` |
| Engineering or documentation rule | `docs/standards/` |
| Deliberate architectural decision with alternatives/tradeoffs | `docs/decisions/` |
| Planned future work | `docs/roadmaps/` |
| How to operate/deploy/recover/verify | `docs/operations/` |
| What happened in a bounded session or proof | `docs/sessions/` |
| Observation/lesson not yet approved architecture | `docs/journal/` |
| Completed governed milestone | `docs/milestones/` |
| Superseded/historical record | `docs/archive/` |
| Current resume point | `docs/control/CURRENT.md` |
| Documentation map/process | `docs/control/` |
| Current production topology/lifecycle | System Registry structured sources under `implementation/kernel/system_registry/` |
| Code-specific setup tightly coupled to a package | README beside the implementation, linked from `docs/` when material |

During migration, the Documentation Register may say that the current canonical file still lives in a numbered legacy directory. If so, update that canonical source instead of creating a second editable copy.

## 3. Search before creating

Before creating a new durable document:

1. Search the Documentation Register.
2. Search `docs/` for the subject, identifier, capability name, provider name, and related terms.
3. Search legacy numbered documentation roots while migration is in progress.
4. Check ADRs and architecture records for an existing governing decision.
5. Check the System Registry when the question is operational topology or lifecycle.

If a document already owns the fact, update it.

If multiple documents appear to own the same fact, stop creating new authority and classify the condition as a documentation conflict for reconciliation.

## 4. Separate intended state, actual state, and proof

Never collapse these concepts:

- **Intended state:** architecture, specification, policy, runbook, declared System Registry state.
- **Observed state:** what a bounded verifier actually saw.
- **Verified state:** observed evidence satisfied the declared requirement.
- **Historical proof:** evidence that a particular event/result occurred at a point in time.
- **Current work:** where the team should resume next.

Example:

- `J-103-System-Registry.md` explains how the System Registry must work.
- `production-registry.json` declares operational topology.
- the verifier report records observed state.
- lifecycle events record governed transitions.
- a session/proof record explains what was proven and why.
- `CURRENT.md` says what to do next.

Do not copy all six into one giant status document.

## 5. Use the minimum durable document set

For a normal material implementation change, the expected documentation set is usually:

- update the governing architecture/component/standard if intended behavior changed;
- update the runbook if an operator procedure changed;
- update System Registry structured state if production topology changed;
- add a proof/session record if new lifecycle, deployment, or live behavior was proven;
- update `docs/control/CURRENT.md` if the safe resume point changed.

Not every code commit needs five documents. Only update the layers whose durable truth changed.

## 6. Use standard metadata

For new durable documents, use the nearest template in `docs/control/DOCUMENT-TEMPLATE.md` and include applicable metadata near the top:

- Identifier / title
- Version
- Status
- Owner / steward
- Authority / governing references
- Scope
- Canonical source designation
- Supersedes / Superseded by
- Review date or review interval
- Evidence references
- Security / data-handling constraints

Do not claim `Approved`, `Verified`, `Active`, `Production`, or equivalent unless the governing process/evidence supports that status.

## 7. Naming conventions

Prefer stable identifiers for governed documents.

Examples:

- `J-###` — foundation, architecture, models, standards as defined by existing numbering conventions.
- `ADR-###` — architecture decision records.
- `JKD-###` — Kernel service/component documents.
- `CAP-###` — capability documents.
- `INF-###` — infrastructure/platform documents.
- `M-###` — milestone records.

Proof/session documents may use a descriptive name plus ISO date when the date is part of the evidence identity.

Do not renumber an existing governed identifier merely to make directories look tidy.

## 8. Write for reconstruction, not for the current conversation

Assume the reader has:

- the repository;
- the document;
- referenced evidence;
- no access to this chat;
- no memory of why the change was made.

A durable record should answer the relevant subset of:

- What problem or outcome is this about?
- What authority permits or constrains it?
- What is the intended behavior?
- What changed?
- What did not change?
- What dependencies exist?
- What evidence proves the claim?
- What could fail?
- How is it verified?
- How is it reversed or retired?
- What must happen next?

Do not use phrases such as “as discussed,” “as we know,” “from earlier,” or “the previous chat” without replacing them with durable references.

## 9. Link instead of duplicating

Good:

> Current production topology is defined by the System Registry. See the production registry and generated operational-state view.

Bad:

> The runtime currently has these 22 entities, these four hashes, these three lifecycle counts, these seven dependencies...

The second form becomes stale the moment production changes.

Duplicate a volatile value only when it is historical evidence for a bounded event, and label the timestamp/context clearly.

## 10. Operational documentation rules

Runbooks must distinguish:

- prerequisites;
- authority/approval requirements;
- safe observation steps;
- mutation steps;
- verification;
- rollback/recovery;
- evidence to retain;
- secrets that must never be displayed;
- stop conditions.

A runbook must not silently repair drift if Jason governance requires remediation through Central Orchestrator or an approval gate.

Use command examples only when they are part of an approved operational procedure. Do not turn a one-time debugging command into an architectural dependency.

## 11. System Registry documentation rules

Use the System Registry for current production components, capabilities, providers, dependencies, identity bindings, governance gates, credential references, deployments, declared state, verification methods, and lifecycle.

Narrative documents may explain or reference these facts, but should not maintain a parallel inventory.

Never put secret values in the System Registry or documentation.

When a production fact changes:

1. follow the governed change process;
2. update structured declared state when applicable;
3. verify observed state;
4. preserve lifecycle/evidence history;
5. regenerate human-readable operational documentation if applicable;
6. update the resume point if the workstream changed.

## 12. Session and proof records

Create a durable session/proof record when a session establishes something that would otherwise be hard to reconstruct from commits alone.

Include:

- date/time or bounded period;
- purpose;
- principal/operator where relevant;
- governing authority;
- system/version/branch or deployment identity where relevant;
- exact result;
- failures encountered and classification;
- changes made;
- changes explicitly not made;
- evidence paths/digests/references;
- security handling notes;
- next action.

A failed proof can be valuable institutional memory. Record it when the failure changes understanding or prevents future repetition.

## 13. Current-work record

`docs/control/CURRENT.md` is the resume point, not a historical diary.

Keep it concise enough to trust and maintain.

It should contain:

- active workstream;
- current governing branch/PR references if relevant;
- last durable success;
- unresolved blockers;
- next safe step;
- host-sensitive work deferred until an operator is present;
- authoritative documents/evidence to read first.

Move old detail into session/proof records instead of endlessly appending to `CURRENT.md`.

## 14. Handoffs

Use `docs/control/HANDOFF-TEMPLATE.md` for a major workstream handoff.

A valid handoff must allow another human or AI session to continue safely without relying on hidden reasoning or chat context.

Never state a runtime fact as current unless it comes from a current authoritative source or fresh evidence. If the host cannot be inspected, label that limitation.

## 15. Decisions and ADRs

Use an ADR when the choice is durable and alternatives matter.

An ADR should capture:

- context/problem;
- decision;
- alternatives considered;
- consequences/tradeoffs;
- authority implications;
- migration/rollback impact;
- status and supersession.

Do not use an ADR for every implementation detail.

Do not bury an architecture decision only inside code comments, chat, or a runbook.

## 16. Architecture journal

Use the architecture journal for observations and candidate lessons that are not yet approved architecture.

A journal entry must not read like a governing rule unless it has been promoted through the appropriate decision/governance process.

When promoted, link the journal entry to the canonical architecture/ADR and mark its status accordingly.

## 17. Security rules

Never document secret values, including:

- passwords;
- API keys;
- private keys;
- OAuth access/refresh tokens;
- OpenBao tokens;
- RoleIDs or SecretIDs;
- unseal material;
- raw credential-bearing environment values;
- client secrets.

Use logical secret names, governed credential references, non-secret IDs, paths-by-reference, and evidence digests where appropriate.

If a command could print a secret, the runbook must either avoid the command or sanitize the output by design.

## 18. Style rules

Use clear, literal language.

Prefer:

- named components and capability identifiers;
- explicit MUST / SHALL for governing requirements;
- explicit MAY / SHOULD for discretionary guidance;
- tables for mappings/status when they improve scanning;
- diagrams for stable architecture relationships;
- links to authoritative sources;
- bounded examples labeled as examples.

Avoid:

- conversational filler;
- unexplained acronyms;
- vague words such as “this,” “that,” or “the system” when a component can be named;
- marketing language in technical/governance records;
- undocumented assumptions;
- future promises stated as present capability;
- copying model-generated prose without checking it against authority and implementation.

## 19. Diagrams

Diagrams are supporting representations unless explicitly designated otherwise.

A diagram must:

- identify the canonical architecture record it illustrates;
- avoid becoming the only place a material rule exists;
- use stable component/capability names;
- be updated when its governing structure changes or marked historical.

Generated diagrams should be reproducible from versioned source where practical.

## 20. References and evidence

Prefer repository-relative links for documentation relationships.

For external evidence that cannot be committed:

- record a safe path/reference;
- record a digest when integrity comparison matters;
- describe what the evidence proves;
- do not imply that an unavailable artifact was reviewed if it was not.

Do not paste large binary evidence into Git merely to make it “documented.”

## 21. Updating an existing document

Before editing:

1. Confirm it is still canonical for the subject.
2. Check whether a higher-authority record changed.
3. Check whether the document contains volatile facts that should instead become references.
4. Preserve historical meaning where needed.
5. Update status/version/review metadata when materially appropriate.
6. Update linked documents only if their durable truth changed.

If the old statement was materially wrong in production, consider a reconciliation/session record rather than silently rewriting history.

## 22. Retiring documentation

Do not delete institutional memory simply because it is old.

When replacing a durable record:

- mark it Superseded or Historical;
- name the replacement;
- move it to `docs/archive/` when appropriate;
- update inbound links/navigation;
- preserve decision/proof history;
- remove it from places that imply current authority.

Compatibility stubs must identify their retirement condition.

## 23. Documentation change checklist

Before completing a material workstream, answer:

- [ ] Did intended behavior change? Update architecture/component/standard/ADR.
- [ ] Did production topology change? Update/verify System Registry through governance.
- [ ] Did the operator procedure change? Update runbook.
- [ ] Was something materially proven or reconciled? Add/update proof/session record.
- [ ] Did the safe resume point change? Update `docs/control/CURRENT.md`.
- [ ] Is there now more than one editable source for the same fact? Reconcile it.
- [ ] Are new documents indexed from `docs/`?
- [ ] Are statuses supported by evidence/approval?
- [ ] Are links valid?
- [ ] Are secrets absent?
- [ ] Can a future session continue without this chat?

## 24. Future-session startup procedure

A future Jason work session should begin documentation context in this order:

1. Read `docs/index.md`.
2. Read `docs/control/CURRENT.md`.
3. Read `docs/control/DOCUMENTATION-REGISTER.md` if locating authority or migrating docs.
4. Read this guide before adding or reorganizing documentation.
5. Read the governing architecture/ADR/runbook/component records for the workstream.
6. Inspect current Git and System Registry/host evidence before making claims about current runtime state.

If conversation memory conflicts with durable documentation or observed evidence, durable governed sources win.

## 25. Governing test

Before considering documentation finished, ask:

> If every chat about this work disappeared tonight, could a competent future operator or AI reconstruct what Jason is supposed to do, how the relevant part is currently governed, what was actually proven, and what the next safe action is?

If the answer is no, the work is not documentation-complete.