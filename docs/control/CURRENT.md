# Project Jason — Current Resume Point

**Updated:** 2026-08-12  
**Status:** Documentation control-plane consolidation is merged. Continuity-enforcement follow-up is active to prevent future sessions from rediscovering Jason fundamentals or reusable construction patterns.  
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

## Active continuity-enforcement workstream

Branch:

`docs/fundamentals-enforcement-2026-08-12`

Purpose:

Prevent repeated rediscovery of Jason's fundamental architecture and the method used to create reusable component classes.

This follow-up exists because the documentation structure was successfully consolidated but the acceptance criteria did not sufficiently force every future session to load the fundamentals and construction patterns before proposing new work.

### Added

- `docs/control/JASON-FUNDAMENTALS.md` — mandatory reconstruction/startup baseline pointing to the authoritative owners of Jason's fundamental rules.
- `docs/control/EXTENSION-CONSTRUCTION-MAP.md` — one construction map for providers/connectors, capabilities/resources, agents/reasoning components, governance/policy gates, ingress/interfaces, identity/authority, secret integrations, internal services, System Registry entities, evidence/audit, approval/communication actions, and deployment/operational procedures.

### Enforcement being added

- J-404 must define documentation completeness as **reconstructable and extensible**, not merely discoverable.
- `HOW-TO-DOCUMENT-JASON.md` must require future sessions to load the fundamentals and construction map before material implementation/design work.
- `CONTRIBUTING.md`, `docs/index.md`, `mkdocs.yml`, and `tools/catch_me_up.py` must expose the same startup baseline.
- Documentation CI must require the fundamentals/construction records and the no-rediscovery/extension-completeness practices.
- New reusable patterns must update their construction guidance in the same governed workstream.
- A material implementation PR must make an explicit documentation-impact determination; "no documentation impact" cannot be an accidental default.

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

The prior live Teams/System Registry troubleshooting work remains host-sensitive. Resume it only from fresh Git, ingress/orchestration evidence, and System Registry/host verification when an operator is present.

## Next safe actions

1. Finish the continuity-enforcement edits and CI checks on `docs/fundamentals-enforcement-2026-08-12`.
2. Run/observe repository validation and strict MkDocs CI.
3. Refetch `feature/jason-runtime-service` immediately before PR readiness/merge.
4. Merge only after the continuity controls are green and the branch is reconciled with the current base.
5. When host work resumes, use the canonical fundamentals/construction map before returning to the live Teams return-path diagnosis.

## Success condition

This workstream is complete when a future session can begin from `docs/index.md` → `JASON-FUNDAMENTALS.md` → `CURRENT.md` → `EXTENSION-CONSTRUCTION-MAP.md`, locate the authoritative records for a component class, and extend Jason without re-deriving its fundamental architecture from previous chats or reverse-engineering existing code.
