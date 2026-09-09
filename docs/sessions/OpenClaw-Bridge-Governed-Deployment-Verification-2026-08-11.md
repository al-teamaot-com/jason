# OpenClaw Bridge Governed Deployment Verification — 2026-08-11

## Purpose

Record the governed production deployment and fresh verification of the approved OpenClaw Jason Teams Bridge replacement on the Jason production-pilot host.

This record is operational evidence. It does not broaden identity, provider, capability, tenant, approval, or secret authority.

## Authority

The authenticated principal `person-al` explicitly granted GA for the bounded production deployment. The deployment remained subject to J-002 Article XIX, J-103, J-100, the Central Orchestrator authority boundary, and the existing OpenClaw/Jason transport controls.

## Approved target

- Repository application foundation: `25b9543daca239b0bbf62c3d32bd0f2d2e06afdf`
- Governed deployment-state branch before deployment: `5e7aedf61728afea8313d3e56f26dfa4741559ea`
- Approved bridge SHA-256: `40e6084d45418d259d74971776cea65677c56a898e8057900fa2f78b896a95e4`
- Previous production bridge SHA-256: `414bbe912b231bba85a007ff10c0d9b1fd9c01ce5d0907e48746f32e45da474b`
- Whole-turn request timeout: `150000` ms
- Conversation-access hook permission remained enabled.

The System Registry declaration was changed before production mutation and the bridge lifecycle was moved from `verified` through `suspended` to `configured`, explicitly invalidating the prior digest verification until fresh observation completed.

## Pre-change evidence

The physical host was verified immediately before the governed bridge deployment:

`/home/al/Jason-Evidence/System-Registry/pre-ga-deployment-20260811T165756Z.json`

The report completed successfully with the then-current production bridge still matching its prior declaration.

## Runtime synchronization

Because the current pilot runtime packages the System Registry files inside the application image, `jason-runtime` was rebuilt after the governed declaration changed so the running query surface would use the same authoritative declared state.

The rebuilt runtime became healthy and reported:

- bridge lifecycle: `configured`
- declared bridge SHA-256: `40e6084d45418d259d74971776cea65677c56a898e8057900fa2f78b896a95e4`

This packaging dependency is an implementation limitation to be removed in a later architecture improvement; it does not change the System Registry authority model.

## Rollback evidence

Before mutation, rollback state was preserved:

- Runtime rollback image: `jason-runtime:rollback-pre-bridge-registry-20260811T171240Z`
- OpenClaw rollback directory: `/home/al/Jason-Evidence/Rollback/OpenClaw/20260811T171240Z`

No secret contents were printed or copied into repository evidence.

## Production mutation

The bounded deployment performed only the approved operations:

1. copied the approved bridge files into the persistent OpenClaw Jason bridge directory;
2. verified the persistent `index.mjs` digest matched the declared target;
3. changed only `plugins.entries.jason-bridge.config.requestTimeoutMs` from `30000` to `150000`;
4. verified the rest of the OpenClaw configuration was unchanged;
5. restarted only the OpenClaw gateway service; and
6. preserved the already-enabled governed conversation-access hook permission.

After restart, `openclaw-openclaw-gateway-1` returned healthy and the running bridge digest was exactly:

`40e6084d45418d259d74971776cea65677c56a898e8057900fa2f78b896a95e4`

`jason-runtime` also remained healthy.

## Fresh post-deployment verification

The physical System Registry verifier was executed after the gateway returned healthy.

Evidence:

`/home/al/Jason-Evidence/System-Registry/post-openclaw-bridge-20260811T171348Z.json`

Result:

- verifier exit code: `0`
- approved bridge digest observed successfully
- declared state was not changed by the verifier
- remediation was not attempted by the verifier
- physical production verification passed

This evidence satisfies the registered `docker-file-sha256-v1` verification method for `component.openclaw-jason-bridge` and supports the governed lifecycle transition from `configured` to `verified`.

## Safe stop on repeated deployment invocation

A subsequent accidental re-invocation of the deployment block rebuilt the already-current runtime image but stopped before any OpenClaw mutation because the pre-deployment guard expected the former bridge digest and observed the already-deployed target digest instead.

The guard therefore failed closed as designed. No second bridge copy, timeout change, or OpenClaw restart occurred in that invocation.

## Governance result

The replacement bridge artifact is now physically deployed and freshly verified against its governed declaration. The System Registry may represent `component.openclaw-jason-bridge` as `verified` once this evidence is appended through the governed lifecycle event trail.

This verification does not by itself prove the Teams-to-Datto conversational path. That separate end-to-end proof must still traverse authenticated Teams transport, Jason identity resolution, the Central Orchestrator, authority and policy gates, provider-neutral endpoint capability resolution, Datto discovery, unique durable identity resolution, exact device read when required, evidence interpretation, and the governed Teams response path.
