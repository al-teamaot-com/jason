# Jason Datto RMM Component Execution Workstream — 2026-09-14

## Current status

The governed Datto RMM component-execution workstream is active on isolated branch `feature/jason-datto-component-execution-20260914`, based on the accepted production documentation head `13941dfb97abd3f0ed2268ad1daed37fa61e00ec`.

Production runtime remains read-only. No execution capability has been activated in production and no Datto component has been executed by this workstream.

Phase 3 received explicit owner approval. The owner reports that the separate Datto execution API identity has been created with the intended provider-side containment. Jason has not yet independently authenticated that identity or verified its provider-side visibility/component restrictions.

The first OpenBao staging attempt stopped safely because the `secret/` KV v2 engine requires check-and-set for writes and the initial provisioning request omitted the required CAS option. The attempt created the dedicated `jason-datto-rmm-execution` OpenBao policy and AppRole before the KV write failed. A subsequent read-only diagnostic proved:

- `secret/` KV v2 `cas_required=true`;
- the execution policy exists;
- the execution AppRole exists;
- the execution AppRole is bound only to the execution policy, has no default policy, 300-second token TTL/max TTL, and two token uses;
- `secret/data/connectors/datto-rmm/production/execution` does not exist;
- the existing Datto read-only secret remains at version 1;
- no execution bootstrap credential directory exists;
- no Datto provider call, runtime activation, write activation, MCP restart, runtime restart, or OpenBao restart occurred.

A fail-closed recovery utility, `deploy/openbao/scripts/recover-datto-rmm-execution-staging.py`, was added specifically for this proven partial state. It verifies the existing policy and AppRole against approved source, requires the observed CAS configuration, writes the execution secret with `options.cas=0`, verifies version-1 isolation and AppRole access boundaries, confirms the read-only secret version remains unchanged, and creates bootstrap material through a temporary root-only directory followed by atomic rename. It still does not contact Datto or activate runtime execution.

The first recovery run was pinned to source `8d26e6a5b75f936b0c2f41341258954da1097d3b`. Its source pin, isolated clone, compile/source-contract checks, live-service baseline, bootstrap-absence check, and final source pin all passed. It then stopped fail-closed immediately after OpenBao administrative authentication with `ERROR: Existing Datto execution policy rules were unavailable.` The temporary administrative token was revoked. The recovery did not reach the Datto execution API-key/API-secret prompts, did not contact Datto, did not activate runtime execution, did not activate provider writes, and did not restart MCP, runtime, or OpenBao.

The failure was traced to a response-shape defect in the recovery utility: it expected the policy document under `data.rules`, while the OpenBao ACL-policy read response used by this deployment returns it in the top-level `policy` field. The parser has now been corrected while preserving fail-closed exact-policy verification. Focused tests cover the actual response shape, compatibility fallback, missing policy text, conflicting representations, exact-policy acceptance, and policy drift. The corrected recovery and its tests passed the `Validate Datto RMM Automation Foundation` workflow in GitHub Actions run `34958605522` at source head `d97c6566dd837115f0d547b4d64a1a506af05d6a`.

The dedicated staging/recovery record is maintained at `docs/operations/Jason-Datto-RMM-Execution-Credential-Staging-2026-09-15.md`.

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

Neither phase converts the existing Datto read identity into an execution identity. Component execution is being built around a separate least-privilege logical credential, `datto_rmm.execution`, and exact `EXECUTE` authority.

The existing `DattoRmmMutationConnector` is still proposal-only for live mutations. No quick-job provider mutation has been enabled in runtime composition, and no arbitrary PowerShell/shell/batch/script-text execution interface has been introduced.

## Phase 3 — provider identity / containment — active

The intended Phase 3 controls are:

1. Use a separate Datto RMM API identity for Jason execution rather than broadening `datto_rmm.readonly`.
2. Apply only the minimum Security Level required for the quick-job operation.
3. Restrict Device Visibility to the intended pilot scope.
4. Assign an API Component Level containing only explicitly approved pilot component(s).
5. Store the resulting execution credential separately as `datto_rmm.execution` under OpenBao rather than reusing the read credential.
6. Prove authentication and harmless read-only access/containment before any quick-job execution.
7. Keep the runtime write/execution surface disabled until a later explicit production-activation approval.

The provider identity has been created by the owner. OpenBao staging is not yet complete: the original attempt stopped on the CAS-required KV write, and the first recovery stopped on the ACL-policy response parser mismatch before any credential write. The parser defect is corrected and CI-proven. The next guarded recovery must re-prove the expected partial state before continuing; the prior execution KV absence, read-only secret version, and bootstrap-directory absence are evidence, not assumptions.

## Approval boundary

Phase 3 provider identity/containment work is explicitly owner-approved.

Separate explicit approval will still be required before deploying a runtime execution surface or running the first live component/quick job. The first live pilot remains intended to be one explicitly approved low-risk diagnostic/read-only component on one noncritical test endpoint with per-run approval and governed post-job verification.
