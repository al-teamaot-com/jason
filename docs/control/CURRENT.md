# Project Jason — Current Resume Point

**Updated:** 2026-08-12  
**Status:** Fundamentals/extension continuity enforcement is merged and complete. The next actual workstream is host-sensitive Teams/OpenClaw/System Registry return-path diagnosis and must resume only from fresh repository, System Registry, ingress/orchestration, and host evidence.  
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

PR #162 — **Enforce Jason fundamentals and extension continuity** — was merged into `feature/jason-runtime-service` on 2026-08-12 at merge commit:

`c6ec6004b7b4d54e6f15dee4fb6138cf21d2eb6d`

Immediately before merge, the actual PR head `757732e0dbd812bb3bef1dd8d97a9f0a2096d533` was revalidated against the unchanged target base `39add8b61a94f604fd8e4b66c7e893d104f26775`:

- `Validate Jason` run 2184: **success**.
- `Validate OpenClaw Operations` run 96: **success**.
- PR #162: **mergeable**.

The merge established:

- `docs/control/JASON-FUNDAMENTALS.md` as the mandatory reconstruction/startup baseline;
- `docs/control/EXTENSION-CONSTRUCTION-MAP.md` as the reusable component-class construction map;
- J-404 documentation completeness as reconstructable **and extensible**;
- explicit documentation-impact determination for material implementation work;
- required construction-guidance updates when a reusable pattern changes;
- startup/handoff/CatchMeUp references to the fundamentals and construction map; and
- CI enforcement so these controls cannot silently disappear.

Refetch Git before relying on any stored SHA for a future write or deployment decision.

## Continuity rule now in force

A Jason workstream is not complete if a future competent human or AI must rediscover from code archaeology or conversation history:

- the component's governing boundaries;
- how it is created;
- how it obtains authority;
- how policy/gates apply;
- how it reaches providers/resources;
- how secrets/evidence/audit work;
- how it is registered, tested, deployed, verified, rolled back, deprecated, or retired; or
- which existing governed pattern should be reused.

When a missing prerequisite has to be rediscovered, that is a documentation defect. The durable construction guidance must be corrected before the affected workstream closes.

## Current workstream

The next unresolved operational work is the live Teams/OpenClaw/System Registry return path.

Known durable context from the prior workstream:

- the runtime-side canonical resource-evidence defect was corrected and physically verified;
- the first live Teams System Registry query still produced no visible Teams reply;
- repository/deployed OpenClaw bridge state previously required evidence-first reconciliation before any deployment change; and
- the remaining diagnosis is host-sensitive and must not be advanced from documentation or conversational memory alone.

Do not infer current runtime status from this record. Re-establish it from current Git, System Registry state, ingress/orchestration evidence, OpenClaw logs, and bounded host verification when an operator is present.

## Production/runtime boundary

The documentation continuity workstream changed no production container, OpenClaw bridge, Jason runtime, provider credential, System Registry lifecycle state, authority grant, or host configuration.

No runtime rebuild or restart is required merely because PR #162 merged.

## Next safe actions

When an operator is back at the Jason host:

1. Confirm the working tree/branch and fast-forward `feature/jason-runtime-service` from origin before doing host-sensitive work.
2. Load `docs/index.md`, `docs/control/JASON-FUNDAMENTALS.md`, this file, and the relevant construction/governance records instead of reconstructing Jason fundamentals from chat history.
3. Re-establish current System Registry/runtime/OpenClaw/Teams evidence.
4. Resume the Teams return-path diagnosis from the first unsupported boundary; do not rebuild, restart, redeploy, or reconcile bridge drift without evidence and normal governance.

Until an operator is at the Jason host, no production command is required for this documentation workstream.

## Success condition

The continuity workstream is complete. Ongoing success means future work can start from the canonical fundamentals and construction map, reuse existing component patterns, and continue from evidence-supported operational state without rediscovering how Jason was built.
