# Jason Datto RMM Execution Credential Staging — 2026-09-15

## Purpose

This record captures the approved Phase 3 staging of the separate Datto RMM execution identity into OpenBao, including the fail-closed staging attempts, read-only diagnostic evidence, recovery-parser corrections, current verified state, and next guarded recovery step.

No provider credential value, OpenBao token, Linux password, Datto API key, Datto API secret, RoleID, SecretID, provider-native object ID, or host secret path value is recorded here.

## Authorization and intended boundary

Phase 3 provider identity / containment work was explicitly approved by the owner.

The intended execution identity remains separate from the existing `datto_rmm.readonly` identity. The future logical credential is `datto_rmm.execution`. Runtime execution is not activated by this staging work, provider writes are not enabled generally, and the first live component execution still requires a separate explicit approval.

The owner reported that the separate Datto execution identity was created in Datto RMM with the intended provider-side containment. Jason has not yet independently authenticated that identity or verified its Datto-side device/component visibility boundaries.

## Initial OpenBao staging attempt

The initial provisioning run was pinned to source `a5260a3d94fb2a2a47a676dc61d178425e95dbf3` and passed source, isolated-clone, compile, policy-file, live-service, OpenBao-health, and final-source-pin checks.

The run authenticated to OpenBao, collected the new Datto execution API key and API secret through hidden interactive prompts, and then stopped on creation of `secret/data/connectors/datto-rmm/production/execution` with HTTP 400.

The provisioning flow had already created the dedicated `jason-datto-rmm-execution` ACL policy and AppRole before the KV write failed. The administrative token was explicitly revoked. The run reported:

- OpenBao staging failed;
- partial state was possible;
- no Datto provider contact occurred;
- no runtime activation occurred;
- no provider-write activation occurred;
- no service restart was requested.

No secret value was printed.

## Read-only incident diagnostic

A subsequent read-only diagnostic performed no mutation and proved the partial state:

- OpenBao was running;
- administrative login succeeded and the temporary administrative token was revoked;
- the `secret/` KV v2 engine reports `cas_required=true`;
- the dedicated execution ACL policy exists;
- the dedicated execution AppRole exists;
- the AppRole is bound to the execution policy only;
- the AppRole has no default policy;
- token TTL is 300 seconds;
- token maximum TTL is 300 seconds;
- token use count is 2;
- the execution KV record does not exist;
- the existing Datto read-only secret exists and remains version 1;
- the execution bootstrap directory does not exist;
- no Datto provider contact, OpenBao mutation, or runtime mutation occurred during the diagnostic.

This established the root cause of the first failure: the KV v2 mount requires check-and-set, while the initial provisioning write omitted a CAS option. A new-record write must use `options.cas=0` under the observed mount configuration.

## First recovery implementation and fail-closed parser stop

A fail-closed recovery utility was added at `deploy/openbao/scripts/recover-datto-rmm-execution-staging.py`. Its design requires the proven partial state, validates the existing policy and AppRole before proceeding, requires `cas_required=true`, uses `options.cas=0` for a new execution KV record, verifies read-only secret version stability, verifies AppRole secret isolation, and creates bootstrap material atomically. It does not contact Datto or activate runtime execution.

The first recovery attempt was pinned to source `8d26e6a5b75f936b0c2f41341258954da1097d3b`. Source pinning, isolated-clone validation, recovery-script compilation, source-contract validation, live-service baseline, bootstrap absence, and the final source pin all passed.

The recovery then stopped immediately after OpenBao administrative authentication with:

`ERROR: Existing Datto execution policy rules were unavailable.`

The temporary administrative token was revoked. The recovery did not prompt for or consume the Datto execution API key or secret on this attempt, did not contact Datto, did not activate runtime execution, did not activate provider writes, and did not restart MCP, runtime, or OpenBao.

## First parser correction and CI proof

The first recovery parser assumed `data.rules`. It was corrected to accept top-level `policy` plus `data.rules` as a compatibility fallback, while still requiring exact normalized policy equality and failing closed on conflicting representations.

Focused tests were added and `Validate Datto RMM Automation Foundation` passed in GitHub Actions run `34958605522` at source head `d97c6566dd837115f0d547b4d64a1a506af05d6a`.

## Second recovery attempt and live-shape discovery

A guarded recovery using the first corrected parser was pinned to authoritative workstream head `8ce06edebcfcf9e47194d2099b3657901e2c278f`. Source pinning, isolated checkout, validated-ancestry checks, compile/smoke checks, service baseline, bootstrap absence, and final source pin all passed.

It again stopped immediately after OpenBao administrative authentication with the same fail-closed message:

`ERROR: Existing Datto execution policy rules were unavailable.`

The temporary administrative token was revoked. The run did not reach the Datto execution API-key/API-secret prompts, did not contact Datto, did not write the execution secret, did not activate runtime execution or provider writes, did not execute a component, and did not restart MCP, runtime, or OpenBao.

A subsequent read-only live-response diagnostic was then performed. It printed only response structure, scalar types, string lengths, and exact normalized policy-match location; it did not print policy contents or any secret value.

The diagnostic proved that the live OpenBao ACL-policy response stores the approved policy at:

`$.data.policy`

The response's `data` mapping contained `allow_slashes_in_identity_templates`, `allow_wildcards_in_identity_templates`, `cas_required`, `modified`, `name`, `policy`, and `version`. Exactly one string matched the approved policy: `POLICY_EXACT_MATCH_PATH=$.data.policy`.

The same diagnostic re-proved:

- execution secret HTTP status 404;
- read-only secret HTTP status 200;
- read-only secret version 1;
- execution bootstrap directory absent;
- no OpenBao configuration or secret change;
- no Datto provider contact;
- no runtime change;
- no component execution;
- temporary administrative token revoked.

The detailed evidence is recorded in `docs/operations/Jason-Datto-RMM-Execution-Live-Policy-Shape-Diagnostic-2026-09-15.md`.

## Live-shape recovery correction and CI proof

A narrow wrapper was added at `deploy/openbao/scripts/recover-datto-rmm-execution-staging-live-shape.py`. It reuses the already-reviewed recovery transaction and replaces only the policy extraction function so that the following response representations are accepted:

- observed live `data.policy`;
- previously modeled top-level `policy`;
- compatibility `data.rules`.

If multiple representations are present they must all normalize to exactly the same policy text or recovery fails closed.

Regression coverage was added at `deploy/openbao/tests/test_recover_datto_rmm_execution_live_shape.py`, including the exact observed live shape and conflicting/missing-policy failure cases.

The focused `Validate Datto RMM Automation Foundation` workflow passed at source head `6becc09bf960eb9d0a1807cedc7dc466c214a0fc` in GitHub Actions run `34959276477`.

## Current verified state

As of the latest completed live evidence:

- production runtime remains read-only;
- no Datto component has been executed;
- no Datto provider authentication has yet been attempted with the execution identity;
- the dedicated OpenBao execution policy is present and its live policy text exactly matches approved source;
- the dedicated OpenBao execution AppRole was previously proven present with the bounded token settings recorded above;
- the execution KV credential record is absent (HTTP 404);
- the existing Datto read-only secret remains version 1;
- the execution bootstrap credential directory is absent;
- no runtime execution surface has been activated;
- no general provider-write capability has been enabled;
- no service restart has been required by the staging attempts.

## Next step

Run the guarded recovery through `recover-datto-rmm-execution-staging-live-shape.py`, pinned to the current authoritative workstream head and validated code head. The recovery must re-prove source/service/bootstrap preconditions before collecting the Datto execution API key and secret. It may create the execution KV record only with `options.cas=0` while the record remains absent, must preserve the read-only credential at version 1, must verify AppRole isolation, and must keep runtime/provider execution disabled.

After OpenBao staging completes, the next Phase 3 milestone is harmless Datto authentication and provider-containment proof. That milestone still must not execute a component or activate a runtime mutation surface.

## Related records

- Workstream: `docs/operations/Jason-Datto-RMM-Component-Execution-Workstream-2026-09-14.md`
- Live policy shape evidence: `docs/operations/Jason-Datto-RMM-Execution-Live-Policy-Shape-Diagnostic-2026-09-15.md`
- Draft PR: #184
- Capability objective: issue #183
