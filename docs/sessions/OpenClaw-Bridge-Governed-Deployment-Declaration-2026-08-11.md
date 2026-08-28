# OpenClaw Bridge Governed Deployment Declaration — 2026-08-11

## Purpose

Record the authorized declared-state change for the OpenClaw Jason Teams Bridge before the production bridge artifact and whole-turn timeout configuration are changed.

This record is part of the Article XIX / J-103 System Registry change trail. It records the authenticated principal, prior state, approved target, reason, authority, and required post-change verification. It contains no secret material.

## Authenticated change principal and authority

- Principal: `person-al`
- Environment: `production-pilot`
- Authority: explicit GA approval for the bounded Jason production deployment batch on 2026-08-11
- Governing references: `J-002 Article XIX`, `J-103`, `J-100`

The authorized batch includes the already completed Jason Runtime rebuild/recreate, deployment of the approved OpenClaw Jason bridge artifact, reconciliation of the explicit OpenClaw whole-turn timeout override, restart of only the affected OpenClaw gateway service, post-change System Registry verification, and governed Teams end-to-end proof.

## Approved source boundary

The production application source was pinned and verified at:

`25b9543daca239b0bbf62c3d32bd0f2d2e06afdf`

The approved target bridge file is:

`infrastructure/openclaw-jason-bridge/index.mjs`

Target SHA-256:

`40e6084d45418d259d74971776cea65677c56a898e8057900fa2f78b896a95e4`

The target source uses a 150000 ms default whole-turn request budget, a 170000 ms configuration ceiling, and a 180000 ms OpenClaw hook guard. Signed-envelope freshness remains a separate short-lived authentication boundary.

## Pre-change observed state

A bounded read-only target capture on the Jason production-pilot host established:

- currently registered bridge SHA-256: `414bbe912b231bba85a007ff10c0d9b1fd9c01ce5d0907e48746f32e45da474b`
- currently deployed bridge SHA-256: `414bbe912b231bba85a007ff10c0d9b1fd9c01ce5d0907e48746f32e45da474b`
- approved target bridge SHA-256: `40e6084d45418d259d74971776cea65677c56a898e8057900fa2f78b896a95e4`
- explicit deployed `requestTimeoutMs` override: `30000`
- desired governed whole-turn override: `150000`
- OpenClaw compose service: `openclaw-gateway`
- current Jason Runtime image after the authorized runtime deployment: `sha256:529c880b3cd1cc2c4a1f07c6c5375adea9312303e216fe0cbd1748c5b3e93fbd`

The pre-change System Registry verification exited `0` and confirmed that production still satisfied the prior declaration before this declared-state change.

Host evidence references:

- `file:///home/al/Jason-Evidence/System-Registry/pre-ga-deployment-20260811T165756Z.json`
- `file:///home/al/Jason-Evidence/System-Registry/system-registry-verification-20260811T165519Z-post-evidence-fix.json`

## Declared-state change

The authoritative declared SHA-256 for `component.openclaw-jason-bridge` is changed from:

`414bbe912b231bba85a007ff10c0d9b1fd9c01ce5d0907e48746f32e45da474b`

to:

`40e6084d45418d259d74971776cea65677c56a898e8057900fa2f78b896a95e4`

The entity source version advances from `2026-08-11.2` to `2026-08-11.3`.

Because the prior `verified` lifecycle evidence applies to the prior digest, it must not remain effective after the declaration changes. The append-only lifecycle trail therefore moves the bridge through `verified -> suspended -> configured` before production mutation. No new `verified` state is permitted until a fresh post-deployment host observation satisfies the new declaration.

## Production mutation boundary

After this declaration is synchronized and validated, the authorized production change is limited to:

1. preserve rollback copies of the current persistent Jason bridge files and OpenClaw configuration;
2. replace the persistent Jason bridge implementation files with the approved repository versions whose `index.mjs` digest is the target digest above;
3. change only `plugins.entries.jason-bridge.config.requestTimeoutMs` from `30000` to `150000`;
4. restart only the `openclaw-gateway` compose service;
5. verify OpenClaw health, bridge loading, deployed bridge SHA-256, and timeout value;
6. rerun the bounded System Registry host verifier;
7. promote the bridge back to `verified` only through a later governed lifecycle event that references the fresh verification evidence.

No credential value, identity binding, Datto configuration, Microsoft configuration, capability authority, provider authorization, or unrelated OpenClaw setting is authorized to change.

## Rollback rule

If the OpenClaw gateway does not return healthy, the bridge fails to load, the deployed SHA-256 differs from the declared target, or the post-change System Registry verifier does not pass, stop the end-to-end test and restore the preserved bridge/configuration backup. Do not improvise additional production changes under this approval.

## Required proof after deployment

After successful physical verification, perform the governed Teams proofs in this order:

1. `Find the System Registry entity named Jason Runtime Service and tell me its resource ID.`
2. `who was on AOT-50282 last?`

The endpoint proof is complete only if correlated evidence shows Teams authenticated transport, Jason identity binding, Central Orchestrator execution, governed Datto discovery, unique durable endpoint identity resolution, exact Datto device read, evidence verification, and a governed Teams response.