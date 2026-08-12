# Project Jason — Current Resume Point

**Updated:** 2026-08-12  
**Status:** Continuity-enforcement follow-up is implemented on PR #162 and is ready for review. Before merge, recheck the current PR head, base branch, mergeability, and CI; do not rely on a stored validation snapshot.  
**Canonical purpose:** Human-readable resume point for current work. Production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

A future session resuming Project Jason should read, in order:

1. `docs/index.md`
2. `docs/control/JASON-FUNDAMENTALS.md`
3. this file
4. `docs/control/EXTENSION-CONSTRUCTION-MAP.md` when creating/changing a Jason component or reusable pattern
5. `docs/control/DOCUMENTATION-REGISTER.md`
6. `docs/control/HOW-TO-DOCUMENT-JASON.md`
7. the governing architecture/ADR/component/standard/runbook/engineering records for the workstream
8. current GitHub state and System Registry/host evidence before asserting live production state

Conversation memory is context only. It is not authority and must not be used to reconstruct fundamentals that already have durable owners.

## Last durable success

PR #161 — **Standardize Project Jason documentation control plane** — was merged into `feature/jason-runtime-service` on 2026-08-12.

The target branch was observed at GitHub-verified merge commit:

`39add8b61a94f604fd8e4b66c7e893d104f26775`

That merge established `docs/` as Jason's single human-facing documentation control plane, J-404 documentation governance, J-405 platform-integrity/boundary enforcement, documentation path/control validation, operations/evidence classification, and the canonical current-work mechanism.

Refetch Git before relying on this SHA for any future write or deployment decision.

## Continuity defect discovered after the merge

Immediately after the documentation-control merge, the canonical `CURRENT.md` still described PR #161 as an active draft/future merge. That was stale and could have sent a future session backward into already-completed work.

The broader documentation was discoverable, but the acceptance criteria also did not strongly require future sessions to load Jason's fundamentals and existing construction patterns before proposing new implementation work.

This is being treated as a documentation-control defect, not as a request to remember better next time.

## Active continuity-enforcement workstream

Branch:

`docs/fundamentals-enforcement-2026-08-12`

Pull request:

`#162 — Enforce Jason fundamentals and extension continuity`

PR state at the last documented check: **ready for review and mergeable**.

Purpose:

Prevent repeated rediscovery of Jason's fundamental architecture and the method used to create reusable component classes.

### Added

- `docs/control/JASON-FUNDAMENTALS.md` — mandatory reconstruction/startup baseline pointing to authoritative owners of Jason's fundamental rules.
- `docs/control/EXTENSION-CONSTRUCTION-MAP.md` — construction map for providers/connectors, capabilities/resources, agents/reasoning components, governance/policy gates, ingress/interfaces, identity/authority, secret integrations, internal services, System Registry entities, evidence/audit, approval/communication actions, and deployment/operational procedures.

### Enforcement implemented

- J-404 defines documentation completeness as **reconstructable and extensible**, not merely discoverable.
- `HOW-TO-DOCUMENT-JASON.md` requires future sessions to load fundamentals and the construction map before material design/implementation work.
- `CONTRIBUTING.md`, `docs/index.md`, MkDocs navigation, handoff templates, CatchMeUp, and documentation CI expose/enforce the same startup baseline.
- New reusable patterns must update their construction guidance in the same governed workstream.
- A material implementation PR must make an explicit documentation-impact determination; `no documentation impact` cannot be an accidental default.
- Documentation CI requires the fundamentals baseline, extension construction map, no-rediscovery controls, component-class coverage, CURRENT continuity signals, and CatchMeUp startup references.

## Validation evidence

Two validation cycles completed successfully before this final stable-state wording was written:

- `Validate Jason` run 2176: **success**.
- `Validate OpenClaw Operations` run 92: **success**.
- `Validate Jason` run 2180: **success**.
- `Validate OpenClaw Operations` run 94: **success**.

PR #162 was then observed ready for review and mergeable against `feature/jason-runtime-service`, with the base still at `39add8b61a94f604fd8e4b66c7e893d104f26775`.

Because this final CURRENT wording itself creates a new documentation-only head, merge decisions must always use fresh GitHub CI/base/head state rather than treating the run numbers above as perpetual authority.

## Governing continuity rule

A Jason workstream is not complete if a future competent human or AI must rediscover from code archaeology or conversation history:

- the component's governing boundaries;
- how it is created;
- how it obtains authority;
- how policy/gates apply;
- how it reaches providers/resources;
- how secrets/evidence/audit work;
- how it is registered, tested, deployed, verified, rolled back, deprecated, or retired; or
- which existing governed pattern should be reused.

When a missing prerequisite has to be rediscovered, that is a documentation defect and the durable construction guidance must be corrected before the workstream closes.

## Production/runtime boundary

This documentation workstream does **not** claim or modify current production runtime state.

No production container, OpenClaw bridge, Jason runtime, provider credential, System Registry lifecycle state, authority grant, or host configuration is changed by this workstream.

The prior live Teams/System Registry troubleshooting remains host-sensitive. Resume it only from fresh Git, ingress/orchestration evidence, and System Registry/host verification when an operator is present.

## Next safe actions

1. Before merging PR #162, refetch its current head, `feature/jason-runtime-service`, mergeability, and CI status.
2. Merge only on current green/reconciled evidence and an explicit merge decision.
3. After merge, advance `CURRENT.md` to the next actual workstream rather than leaving PR #162 described as active.
4. When host work resumes, load canonical fundamentals/construction guidance before returning to live Teams return-path diagnosis.

## Success condition

This workstream is complete when a future session can begin from `docs/index.md` → `JASON-FUNDAMENTALS.md` → `CURRENT.md` → `EXTENSION-CONSTRUCTION-MAP.md`, locate authoritative records for a component class, and extend Jason without re-deriving its fundamental architecture from previous chats or reverse-engineering existing code.
