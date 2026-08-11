# Project Jason — Current Resume Point

**Updated:** 2026-08-11  
**Status:** Documentation standardization in progress  
**Canonical purpose:** Human-readable resume point for current work. Production/runtime facts must still be established from current Git, the System Registry, and fresh host evidence when required.

## Read first

A future session resuming Project Jason should read, in order:

1. `docs/index.md`
2. this file
3. `docs/control/DOCUMENTATION-REGISTER.md`
4. `docs/control/HOW-TO-DOCUMENT-JASON.md`
5. the governing architecture/ADR/runbook/component records for the intended workstream
6. current GitHub state and System Registry/host evidence before asserting live production state

## Current documentation workstream

The active offline documentation-standardization branch is:

`docs/documentation-standardization-2026-08-11`

It was created from the then-current `feature/jason-runtime-service` commit:

`28719135e25639c48b5cce847ff83b6e4825d502`

That base commit is historical branch context, not a claim that the active development branch or production host still uses that commit.

## Last durable documentation progress

The documentation control plane now includes:

- `docs/index.md` — stable documentation entry point without volatile runtime claims;
- `docs/standards/J-404-Documentation-Governance-and-Continuity.md` — documentation governance and continuity standard;
- `docs/control/DOCUMENTATION-REGISTER.md` — authority map and migration register;
- `docs/control/HOW-TO-DOCUMENT-JASON.md` — repeatable authoring/update procedure for future human and AI sessions;
- `docs/control/DOCUMENT-TEMPLATE.md` — durable-document metadata/template;
- `docs/control/HANDOFF-TEMPLATE.md` — durable workstream handoff format;
- this `docs/control/CURRENT.md` resume point.

These records establish `docs/` as the single human-facing documentation control plane while legacy numbered source directories are migrated in governed stages.

## Governing migration rule

Do not create a second editable copy of a legacy canonical document merely to move it under `docs/`.

For each category:

1. identify authority and duplicate/conflicting material;
2. migrate or reconcile the canonical source;
3. update links, MkDocs navigation, CI, release/documentation tooling, and references;
4. preserve historical/superseded material;
5. retire the old location only when no independent editable authority remains.

The detailed category state and retirement conditions are in `docs/control/DOCUMENTATION-REGISTER.md`.

## Next offline documentation tasks

1. Standardize repository entry points so `README.md`, MkDocs, and contributor guidance direct readers to `docs/` rather than duplicating current-state claims.
2. Add documentation-structure validation so new documentation cannot silently re-fragment across legacy roots.
3. Migrate low-conflict categories into the target `docs/` structure first: Foundation, Canonical Models, Standards, ADRs, Roadmaps, Journal, and Milestones.
4. Reconcile existing `docs/architecture/` material with canonical J-series architecture before moving `02-Architecture/`.
5. Reconcile existing `docs/governance/` material with Foundation/Governance authority before moving `01-Governance/`.
6. Migrate component/capability/infrastructure documentation and update implementation-local README indexes.
7. Separate operational procedures from historical proof/session records while migrating `07-Operations/` and `08-Session-Records/`.
8. Update MkDocs to publish directly from the consolidated `docs/` source tree without using a mixed canonical/publishing assembly model.
9. Update release/documentation tooling such as documentation readiness checks to use consolidated paths.
10. Run CI, inspect links/navigation, and retire compatibility roots only after validation is green.

## Work explicitly not performed by this documentation workstream

No production container, OpenClaw bridge, Jason runtime, provider credential, System Registry lifecycle state, authority grant, or host configuration is changed by this offline documentation-standardization work.

This record does not claim the latest production runtime state. If another workstream or chat has advanced runtime development, reconcile current Git/System Registry/host evidence before continuing host-sensitive work.

## Known continuity requirement from the prior host work

Before this offline documentation work began, host-sensitive troubleshooting was being performed through the governed Teams/OpenClaw/Jason path. This documentation branch deliberately does not attempt to resolve or assert the state of that live path while the operator is away from Jason.

A future host session must use fresh ingress/orchestration/System Registry evidence rather than this file to determine current runtime status.

## Definition of success for documentation standardization

The workstream is complete only when:

- all governed human-facing Jason documentation is discoverable and physically organized under `docs/`, except justified implementation-local README files;
- each material fact has one authoritative owner;
- the System Registry remains the source for current operational topology instead of narrative duplication;
- legacy numbered documentation roots are retired or reduced to explicit temporary compatibility stubs;
- MkDocs/CI/tooling operate directly on the consolidated documentation structure;
- future sessions use `docs/control/HOW-TO-DOCUMENT-JASON.md` to maintain the same documentation discipline; and
- a future contributor can reconstruct Jason's governance, architecture, implementation boundaries, operating method, proof history, and safe next action without access to chat history.
