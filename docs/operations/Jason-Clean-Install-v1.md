# Jason v1 Clean Install

Issue #749 defines the deterministic clean-install path.

The current implementation is intentionally non-production. It supports only development and candidate environments and refuses the live filesystem root.

## Current foundation

The clean-install planner:

- validates the supported Ubuntu 24.04 x86-64 host contract;
- validates MSP configuration and MSP policy against the v1 schemas;
- validates required Python and container-runtime prerequisites;
- computes canonical configuration and policy revisions;
- produces a deterministic install plan;
- defines canonical Jason release, state, log, and runtime directories;
- records required Docker networks without creating them implicitly;
- keeps secret enrollment as a separate governed process;
- may initialize the canonical filesystem layout under an explicit non-production target root.

It does not yet install application images, systemd units, databases, provider credentials, or start Jason services.

## Safety

The bootstrap implementation refuses Production and refuses the live filesystem root.

Production installation will later consume the J-CHANGE-003 exact-plan Owner-approved promotion boundary rather than adding a separate bootstrap bypass.

## Candidate runtime staging

The candidate bootstrap now supports a second deterministic phase:

- verify an immutable release archive by SHA-256;
- reject absolute paths, path traversal, links, and device members in release archives;
- atomically stage the release under opt/jason/releases/<source-sha>;
- atomically select opt/jason/current inside the candidate root;
- initialize core authority, client-boundary, orchestration-event, and approval-continuation SQLite schemas through their actual Jason persistence implementations;
- create parent state locations for runtime-owned stores without fabricating their schemas;
- classify external databases separately;
- stage only systemd units explicitly classified as portable;
- fail closed on operator-home paths in a supposedly portable unit;
- block readiness when a staged service references release code that is absent;
- generate a bootstrap runtime manifest and candidate bootstrap result.

This phase still does not create Docker networks, enable/start systemd units, enroll provider secrets, or start containers on the current host.

A candidate that passes this phase is reported as ready_for_runtime_activation, not Jason READY.
