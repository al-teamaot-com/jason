# Jason Datto RMM Execution Credential Staging — 2026-09-15

## Purpose

This record captures the approved Phase 3 staging of the separate Datto RMM execution identity into OpenBao, including the fail-closed staging attempts, read-only diagnostic evidence, recovery-parser correction, current verified state, and next guarded recovery step.

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

## Root cause of the recovery failure

The first recovery utility assumed that `GET /v1/sys/policies/acl/:name` returned the policy document under `data.rules`.

The OpenBao ACL-policy read response used by this deployment returns the policy document in the top-level `policy` field. The recovery therefore failed closed before any credential write because the expected field was unavailable.

This was a source parsing defect in the recovery utility, not evidence of policy loss or policy drift.

## Recovery parser correction and CI proof

The recovery parser was corrected in source so that:

- the actual top-level OpenBao `policy` field is accepted;
- the previously assumed nested `data.rules` form is retained only as a compatibility fallback;
- if both representations are present they must normalize to the same policy text;
- missing policy text fails closed;
- conflicting policy representations fail closed;
- the retrieved policy must still exactly match the approved source before recovery can proceed.

Focused regression coverage was added at `deploy/openbao/tests/test_recover_datto_rmm_execution_staging.py`, including actual top-level response shape, compatibility fallback, missing policy, conflicting policy representations, exact-policy acceptance, and policy-drift rejection.

The `Validate Datto RMM Automation Foundation` workflow was extended to compile the recovery utility and run the focused recovery tests. GitHub Actions run `34958605522` completed successfully at source head `d97c6566dd837115f0d547b4d64a1a506af05d6a`.

No production/OpenBao state changed as a result of the source correction or CI run.

## Current verified state

As of the latest completed production evidence:

- production runtime remains read-only;
- no Datto component has been executed;
- no Datto provider authentication has yet been attempted with the execution identity;
- the dedicated OpenBao execution policy was proven present;
- the dedicated OpenBao execution AppRole was proven present with the bounded token settings recorded above;
- the execution KV credential record was last proven absent;
- the existing Datto read-only secret was last proven at version 1 and must not be modified by this workstream;
- the execution bootstrap credential directory was last proven absent;
- no runtime execution surface has been activated;
- no general provider-write capability has been enabled;
- no service restart has been required by the staging attempts.

The corrected recovery must re-prove these preconditions before writing anything; prior evidence is not treated as permission to assume the state remains unchanged.

## Next step

Run the corrected guarded recovery from the current authoritative workstream branch. The recovery must first re-prove the expected partial state and exact source pin, then use `options.cas=0` only if the execution KV record is still absent. It must preserve the read-only credential, keep all services running without restart, and leave runtime/provider execution disabled.

After OpenBao staging completes, the next Phase 3 milestone is harmless Datto authentication and provider-containment proof. That milestone still must not execute a component or activate a runtime mutation surface.

## Related records

- Workstream: `docs/operations/Jason-Datto-RMM-Component-Execution-Workstream-2026-09-14.md`
- Draft PR: #184
- Capability objective: issue #183
