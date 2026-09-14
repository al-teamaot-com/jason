# Jason Datto RMM Component Execution Workstream — 2026-09-14

## Current status

The governed Datto RMM component-execution workstream has begun on isolated branch `feature/jason-datto-component-execution-20260914` from production-source documentation head `13941dfb97abd3f0ed2268ad1daed37fa61e00ec`.

Production remains unchanged and read-only. No provider write credential has been created or staged, no Datto Security Level / Device Visibility / API Component Level has been changed, and no Datto component has been executed by this workstream.

## Phase 1 source-only foundation

The first source-only milestone now includes:

- canonical read-only capability `automation.component.search`;
- canonical read-only capability `automation.job.read`;
- a Datto automation-read connector using the existing `datto_rmm.readonly` logical credential;
- account component catalog reads through `GET /api/v2/account/components`;
- bounded complete component pagination before canonical filtering;
- exact job status reads through `GET /api/v2/job/{jobUid}`;
- fail-closed durable-identity checks for components and jobs;
- bounded canonical result projection that does not return arbitrary provider fields;
- omission of component variable default values from the released read model;
- provider-neutral Integration Broker resources for automation components and jobs;
- Central Orchestrator runtime routing for only the two read-only automation capabilities;
- explicit absence of `automation.component.execute` from the activated capability/provider/invoker surface.

Focused Datto read-foundation CI passed at source head `5c528972410fdd5a737081043f3db7da6b1ba73a` in GitHub Actions run `34867883313`.

## Security boundary preserved

This phase does not convert the existing Datto read identity into an execution identity. Future component execution remains designed to use a separate least-privilege logical credential such as `datto_rmm.execution` and exact `EXECUTE` authority.

The existing `DattoRmmMutationConnector` remains proposal-only for live mutations. No quick-job provider mutation has been enabled in runtime composition.

## Next source-only milestone

Phase 2 will remain non-production and use fake transports/test identities only. It will add deterministic quick-job request construction behind the existing proposal/approval boundary and prove fail-closed behavior for:

- component allowlist membership;
- component implementation identity/fingerprint;
- target device/client scope;
- component-variable schema validation;
- human-readable reason;
- idempotency;
- exact approval binding;
- audit evidence.

It must be possible to prove the provider request that *would* be sent without sending it to Datto.

## Approval boundary

Explicit owner approval will be required before any later phase that creates or changes a Datto write-capable API identity, changes provider security/component visibility, stages a write-capable OpenBao secret, deploys a runtime execution surface, or runs a live component.
