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

## Candidate activation boundary

Runtime activation is a separate phase from filesystem bootstrap.

The candidate activation contract requires a validated candidate-host identity with:
- schema version 1.0;
- environment = candidate;
- a non-empty instance ID;
- explicit bootstrap authorization.

The activation plan contains only:
- creation of required Docker networks when absent;
- enablement of systemd units previously classified and staged as portable.

The executor is allowed to run only when the target is the candidate host root. It does not start services and does not enroll provider secrets. Production identity is rejected.

This keeps the current development host from being used as an accidental activation target while allowing the same released tooling to operate on a future dedicated Jason-B candidate host.

## Deployment Manifest integration

The candidate bootstrap now produces the authoritative Deployment Manifest as part of the same deterministic build.

The manifest derives identity from what was actually staged and initialized:

- platform version from the staged release implementation/pyproject.toml;
- source SHA and release artifact SHA-256 from the verified immutable release;
- deployment revision from canonical deployment content, not the temporary target-root path;
- MSP configuration and MSP policy revisions from canonical validated JSON;
- playbook revision from the canonical released playbook registry;
- SQLite schema identities from hashes of the actual initialized sqlite_master schema definitions;
- provider enablement from MSP configuration;
- capability-bundle revision from canonical configured bundle selection;
- runtime identity from the observed supported host.

The resulting manifest is written to var/lib/jason/deployment-manifest.json inside the candidate root and can be read by the #750 runtime Deployment Manifest provider.

Changing only the temporary filesystem location does not change the logical deployment identity.

## Governed secret readiness

Candidate bootstrap now derives required logical secret references from enabled MSP providers.

The bootstrap writes var/lib/jason/secret-requirements.json containing only:
- provider IDs;
- logical secret-reference identifiers;
- requirement state;
- an explicit assertion that no secret values are present.

References that resemble filesystem paths or inline key/value secrets are rejected.

A separate secret-presence attestation may list which logical references are available. The readiness check compares identifiers only; it never reads, returns, or logs the secret values themselves.

Provider startup remains blocked from being treated as fully ready until every required logical reference is attested available.


## Candidate READY contract

A staged candidate is not Jason READY.

The candidate READY controller requires a single evidence set to prove all of the following:

- the candidate bootstrap reached ready_for_runtime_activation;
- the runtime Deployment Manifest identity matches the staged manifest;
- every required logical secret reference is attested present without exposing values;
- every required Docker network exists;
- every required portable systemd unit is enabled;
- runtime health is healthy and reports the same Deployment Manifest identity;
- OpenClaw/JKD-001 operational-health evidence is healthy and fresh;
- governed provider-health canaries are healthy and fresh for every enabled provider.

Any missing, stale, degraded, unavailable, or identity-mismatched check yields BLOCKED.

The candidate-status command collects these secret-safe signals and evaluates them together. When the command is run against the actual host root, an explicit authorized candidate-host identity is required. A Production identity cannot unlock candidate READY evaluation.

This controller is read-only except for the optional candidate-ready result file. It does not enroll secrets, start services, contact providers directly, or grant operational authority.

## Blank-host candidate installation

The clean-install implementation now distinguishes an ordinary live filesystem root from an explicitly authorized candidate host.

Temporary/non-live target roots continue to require no special host identity.

Target root / is accepted only when every mutating bootstrap layer receives the same validated Candidate Host Identity. The candidate identity cannot represent Production and must explicitly authorize bootstrap.

The read-only candidate_host_preflight command should run before the first host-mode install. A blank host is blocked when prior Jason deployment markers or installed Jason units are detected.

This enables the same deterministic bootstrap code used in non-production filesystem tests to become the installer for the eventual dedicated Jason-B Ubuntu host without adding a generic bypass flag.
