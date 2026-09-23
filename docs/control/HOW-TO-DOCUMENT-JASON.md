# How to Document Project Jason

**Status:** Active documentation practice guide  
**Owner:** Jason Architecture Authority  
**Governing standard:** `docs/standards/J-404-Documentation-Governance-and-Continuity.md`  
**Purpose:** Give future human and AI work sessions one repeatable method for documenting Jason without creating duplicate authority, losing operational context, rediscovering fundamentals, or depending on chat history.

## The rule to remember

Document durable truth once, in the place that owns that truth, and link to it everywhere else.

Do not use chat history as the final record. Do not reconstruct fundamentals from memory or code archaeology when a governed source already owns them. Do not create a new document merely because you cannot remember where the existing one is.

## 1. Mandatory startup before material Jason work

Before proposing architecture, adding a connector/provider, capability/resource, agent, gate, ingress/interface, identity/authority component, secret integration, internal service, System Registry entity, or reusable operational mechanism:

1. Read `docs/control/JASON-FUNDAMENTALS.md`.
2. Read `docs/control/CURRENT.md`.
3. Read `docs/control/EXTENSION-CONSTRUCTION-MAP.md` for the relevant component class.
4. Use `docs/control/DOCUMENTATION-REGISTER.md` to find the authoritative owner.
5. Read the governing architecture, standard, ADR, component/capability/provider contract, runbook, and construction guidance.
6. Inspect an existing analogous implementation and its tests only after the governing rules are understood.
7. Inspect current Git and System Registry/host evidence before asserting current production state.

The purpose of looking at an existing implementation is reuse, not reverse-engineering Jason's fundamentals.

## 2. Decide whether documentation is required

Create or update durable documentation when a change affects something a future operator, developer, reviewer, auditor, or AI system would need to reconstruct or extend safely.

Usually document:

- a constitutional/governance rule;
- an architectural boundary or durable decision;
- a new/changed capability, provider, connector, component, interface, gate, agent, dependency, identity binding, or credential integration;
- a new reusable construction pattern;
- an operational/recovery procedure;
- a production deployment or topology change;
- an authority/approval/security model change;
- a material failure and its durable lesson;
- a new source of operational truth;
- verification/live proof establishing lifecycle state;
- a change to how Jason is built, deployed, tested, recovered, resumed, or extended;
- a checkpoint costly to reconstruct from code/Git history alone.

Transient debugging detail does not need durable documentation unless it explains a durable failure mode, decision, or recovery procedure.

## 3. Find the authoritative owner before writing

Ask: **What kind of truth is this?**

| Truth | Where it belongs |
|---|---|
| Mission / constitutional rule | `docs/foundation/` or `docs/governance/` |
| Enduring architecture / boundary | `docs/architecture/` |
| Provider-neutral organizational concept | `docs/models/` |
| Kernel/component/capability/infrastructure contract | `docs/components/` |
| Reusable implementation engineering / construction guidance | `docs/engineering/` |
| Engineering/documentation/platform-integrity rule | `docs/standards/` |
| Deliberate architectural decision | `docs/decisions/` |
| Planned future work | `docs/roadmaps/` |
| Operate/deploy/recover/verify | `docs/operations/` |
| Bounded session/proof | `docs/sessions/` |
| Observation/lesson not yet approved architecture | `docs/journal/` |
| Completed governed milestone | `docs/milestones/` |
| Superseded/historical record | `docs/archive/` |
| Current resume point | `docs/control/CURRENT.md` |
| Fundamentals/reconstruction baseline | `docs/control/JASON-FUNDAMENTALS.md` |
| Extension construction discovery | `docs/control/EXTENSION-CONSTRUCTION-MAP.md` |
| Documentation map/process | `docs/control/` |
| Current production topology/lifecycle | `implementation/kernel/system_registry/` structured truth |
| Code-specific setup tightly coupled to package | README beside implementation, indexed by `IMPLEMENTATION-DOCUMENTATION-INDEX.md` |

## 4. Search before creating

Before creating a durable document:

1. Search the Documentation Register.
2. Search `docs/` by subject, identifier, capability/provider/component name, and related terms.
3. Check the Extension Construction Map for existing reusable guidance.
4. Search the Implementation Documentation Index when package-adjacent guidance may already exist.
5. Check ADRs/architecture records.
6. Check System Registry for operational topology/lifecycle.

If a document already owns the fact, update it. If multiple documents appear to own it, stop creating new authority and reconcile the conflict.

## 5. Separate intended state, actual state, and proof

Never collapse:

- **Intended state:** architecture, specification, policy, runbook, declared System Registry state.
- **Observed state:** what a bounded verifier saw.
- **Verified state:** observed evidence satisfied the declared requirement.
- **Historical proof:** evidence of a bounded event/result.
- **Current work:** safe resume point.

Narrative documentation must not become a second operational inventory.

## 6. Preserve reusable construction knowledge

When a workstream creates or materially changes a reusable Jason pattern, document enough that the next instance can be created without rediscovering fundamentals.

At minimum capture or link to:

- component class and purpose;
- governing architecture/standards/ADRs;
- allowed and prohibited direct dependencies;
- contract/schema and capability/resource names;
- identity/authority/policy/approval behavior;
- secrets/data handling;
- audit/evidence/correlation behavior;
- provider/resource resolution boundaries;
- deterministic tests/conformance expectations;
- System Registry registration/lifecycle where applicable;
- deployment/verification/rollback/retirement; and
- closest governed implementation exemplar.

Update `docs/control/EXTENSION-CONSTRUCTION-MAP.md` when the construction path changes or a new component class/pattern appears.

If a future session would need code archaeology to determine how to create the next component of the same class, the workstream is not documentation-complete.

## 7. Use the minimum durable document set

For a material implementation change, usually update only the layers whose durable truth changed:

- governing architecture/component/standard/ADR;
- reusable construction guidance;
- runbook;
- System Registry structured state;
- proof/session record;
- `CURRENT.md`.

Not every commit needs every document.

## 8. Use standard metadata

For new durable documents, use `docs/control/DOCUMENT-TEMPLATE.md` and applicable metadata: identifier/title, version, status, owner/steward, authority, scope, canonical source, supersession, review interval, evidence, and security/data-handling constraints.

Do not claim Approved/Verified/Active/Production unless the governing process/evidence supports it.

## 9. Write for reconstruction and extension

Assume the reader has the repository and referenced evidence but no chat history.

A durable record should answer the relevant subset of:

- What is this for?
- What authority constrains it?
- What is intended?
- What changed / did not change?
- What dependencies exist?
- What may not be bypassed?
- What evidence proves it?
- How is it tested/verified?
- How is it reversed/retired?
- How would I create another one safely?
- What must happen next?

Avoid “as discussed,” “as we know,” “from earlier,” or “the previous chat” unless replaced with durable references.

## 10. Link instead of duplicating

Reference authoritative volatile sources rather than copying current hashes, lifecycle counts, runtime versions, or topology into multiple narrative documents.

Duplicate volatile values only as timestamped historical evidence.

## 11. Operational documentation rules

Runbooks must distinguish prerequisites, authority/approval, observation, mutation, verification, rollback/recovery, evidence retention, secrets that must never be displayed, and stop conditions.

Runbooks must not silently repair drift where remediation belongs through Central Orchestrator/governance.

One-time debugging commands do not become architectural dependencies merely because they worked once.

## 12. System Registry documentation rules

Use System Registry for current production components, capabilities, providers, dependencies, identity bindings, governance gates, credential references, deployments, declared state, verification methods, and lifecycle.

Narrative docs explain/reference these facts; they do not maintain parallel current state.

Never put secret values in System Registry or documentation.

## 13. Session and proof records

Create a durable proof/session record when a session establishes something difficult to reconstruct from commits alone.

Include purpose, principal/operator where relevant, authority, version/branch/deployment identity, exact result, failures/classification, changes made/not made, evidence references, security notes, and next action.

Failed proofs are durable institutional memory when they materially change understanding or prevent repetition.

## 14. Current-work record

`docs/control/CURRENT.md` is the resume point, not a diary.

It should contain active workstream, last durable success, unresolved blockers/risks, next safe step, host-sensitive work, and authoritative sources to read first.

When a branch/PR/workstream closes, `CURRENT.md` must not continue directing future sessions to it as active work.

## 15. Handoffs

Use `docs/control/HANDOFF-TEMPLATE.md` for major handoffs. A valid handoff must allow another human/AI session to continue safely without hidden reasoning/chat context.

Never state runtime facts as current without current authoritative source/fresh evidence.

## 16. Decisions and ADRs

Use ADRs for durable choices where alternatives/tradeoffs matter. Capture context, decision, alternatives, consequences, authority implications, migration/rollback, status/supersession.

Do not bury architectural decisions only in code comments, chats, or runbooks.

## 17. Security rules

Never document secret values: passwords, API keys, private keys, OAuth tokens, OpenBao tokens, RoleIDs/SecretIDs, unseal material, or raw credential-bearing environment values.

Use logical secret names, governed credential references, non-secret IDs, paths-by-reference, and evidence digests.

## 18. Documentation-impact determination

Every material implementation workstream/PR must explicitly determine documentation impact across:

- architecture/standard/ADR;
- component/capability/provider contract;
- reusable construction guidance;
- System Registry;
- operations/runbooks;
- proof/session evidence;
- current resume point.

"No documentation impact" must be an explicit reviewed conclusion, not the default caused by forgetting documentation.

## 19. Retiring documentation

Do not delete institutional memory merely because it is old. Mark Superseded/Historical, identify replacement, archive where appropriate, update links/navigation, preserve decision/proof history, and remove it from places implying current authority.

## 20. Documentation change checklist

Before completing a material workstream:

- [ ] Did intended behavior/authority change? Update governing architecture/component/standard/ADR.
- [ ] Did a reusable construction pattern change or get discovered? Update owning construction guide and `EXTENSION-CONSTRUCTION-MAP.md`.
- [ ] Could a future session create another component of this type without code archaeology/chat history?
- [ ] Did production topology change? Update/verify System Registry through governance.
- [ ] Did operator procedure change? Update runbook.
- [ ] Was something materially proven/reconciled? Add/update proof/session record.
- [ ] Did safe resume point change? Update `CURRENT.md`.
- [ ] Is there more than one editable source for the same fact? Reconcile it.
- [ ] Are new governed docs indexed?
- [ ] Are implementation-local READMEs represented in `IMPLEMENTATION-DOCUMENTATION-INDEX.md`?
- [ ] Are statuses supported by evidence/approval?
- [ ] Are links valid?
- [ ] Are secrets absent?
- [ ] Is the documentation-impact determination explicit?
- [ ] Can a future session continue and extend Jason without this chat?

## 21. Future-session startup procedure

A future Jason session begins documentation context in this order:

1. `docs/index.md`
2. `docs/control/JASON-FUNDAMENTALS.md`
3. `docs/control/CURRENT.md`
4. `docs/control/EXTENSION-CONSTRUCTION-MAP.md` for material implementation/extension work
5. `docs/control/DOCUMENTATION-REGISTER.md`
6. this guide before documentation changes
7. `docs/control/IMPLEMENTATION-DOCUMENTATION-INDEX.md` when package-local guidance matters
8. governing architecture/ADR/component/standard/runbook/engineering records
9. current Git and System Registry/host evidence before current-runtime claims

If conversational memory conflicts with durable documentation or observed evidence, governed durable sources win.

## 22. Governing test

Before considering documentation finished, ask:

> If every chat about this work disappeared tonight, could a competent future operator or AI reconstruct what Jason is supposed to do, the governing boundaries, what was proven, the next safe action, and how to create the next component of the same class without rediscovering fundamentals?

If the answer is no, the work is not documentation-complete.
