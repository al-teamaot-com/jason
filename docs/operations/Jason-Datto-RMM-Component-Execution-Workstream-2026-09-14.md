# Jason Datto RMM Component Execution Workstream — 2026-09-14

## Current status

The governed Datto RMM component-execution workstream is active on isolated branch `feature/jason-datto-component-execution-20260914`, based on the accepted production documentation head `13941dfb97abd3f0ed2268ad1daed37fa61e00ec`.

Production remains unchanged and read-only. No provider write credential has been created or staged, no Datto Security Level / Device Visibility / API Component Level has been changed, no execution capability has been activated in production, and no Datto component has been executed by this workstream.

Draft PR #184 tracks this isolated workstream. Issue #183 tracks the capability objective.

## Phase 1 — read-only automation foundation — complete in source/tests

The first source-only milestone includes:

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

## Phase 2 — governed proposal / exact-request foundation — complete in source/tests

Phase 2 remains non-production and does not contain a live Datto mutation executor. It adds deterministic source-only construction of the exact future quick-job request behind the existing proposal/approval boundary.

Implemented controls include:

- durable component allowlist entries with canonical component identity, human-readable name, provider implementation identity, allowed endpoint classes, variable policy, optional provider metadata fingerprint, approval policy, and active/suspended/retired state;
- component-variable policies with supported bounded types (`string`, `boolean`, `date`, `selection`), required variables, maximum lengths, and selection allowlists;
- exact component/provider identity matching;
- optional provider metadata-fingerprint pinning to fail closed on implementation drift;
- exact target device-class restriction;
- rejection of arbitrary or unknown variables, including arbitrary command/script fields that are not part of the allowlist contract;
- deterministic Datto quick-job request construction for `PUT /api/v2/device/{deviceUid}/quickjob`;
- deterministic provider-request digest binding without releasing the raw provider request as user-facing proposal data;
- human-readable reason included in the mutation-plan digest so approval cannot be reused after the purpose changes;
- explicit governed client scope required for component proposals;
- generic mutation controls retained for execute mode: idempotency key plus exact, expiring approval bound to capability/principal/organization/client/argument digest;
- proposal audit evidence retained;
- live execution still terminates at the intentional fail-closed boundary: `Datto RMM live mutation executor is not configured.`

Tests prove that a valid exact approval can reach only that disabled live-execution boundary, and that changing the reason or component variables after approval invalidates the approval digest.

The focused `Validate Datto RMM Automation Foundation` workflow passed at source head `e4afc7afd1c465bee16891e356d59d902ecd3a84` in GitHub Actions run `34868375772`. That workflow compiles the Datto read/proposal boundary and runs the Datto authentication, existing endpoint/site read, automation read, automation manifest, component proposal, provider-adapter, capability-routing, resource-catalog, and runtime-composition tests plus the existing credential-safe/no-network Datto preflight.

## Security boundary preserved

Neither phase converts the existing Datto read identity into an execution identity. Future component execution remains designed to use a separate least-privilege logical credential such as `datto_rmm.execution` and exact `EXECUTE` authority.

The existing `DattoRmmMutationConnector` is still proposal-only for live mutations. No quick-job provider mutation has been enabled in runtime composition, no write-capable credential is present in the new source path, and no arbitrary PowerShell/shell/batch/script-text execution interface has been introduced.

## Next milestone — Phase 3 provider identity / containment

The next meaningful phase is no longer source-only. It would create or configure the provider-side identity and containment needed for a controlled execution pilot. The intended work is:

1. Create or designate a separate Datto RMM API identity for Jason execution rather than broadening `datto_rmm.readonly`.
2. Apply the minimum Security Level required for the quick-job operation.
3. Restrict Device Visibility to the intended pilot scope.
4. Assign an API Component Level containing only explicitly approved pilot component(s).
5. Store the resulting execution credential separately as `datto_rmm.execution` under OpenBao rather than reusing the read credential.
6. Prove authentication and harmless read-only access/containment before any quick-job execution.
7. Keep the runtime write/execution surface disabled until a later explicit production-activation approval.

## Approval boundary

Phase 3 is consequential because it creates or changes provider security/access and stages a write-capable credential. It requires explicit owner approval before work begins.

Separate explicit approval will also be required later before deploying a runtime execution surface or running the first live component/quick job. The first live pilot remains intended to be one explicitly approved low-risk diagnostic/read-only component on one noncritical test endpoint with per-run approval and governed post-job verification.
