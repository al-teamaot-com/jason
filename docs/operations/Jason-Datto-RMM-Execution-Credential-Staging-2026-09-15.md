# Jason Datto RMM Execution Credential Staging — 2026-09-15

## Purpose

This record captures the approved Phase 3 staging of the separate Datto RMM execution identity into OpenBao, including both fail-closed staging attempts, the read-only diagnostic evidence, the current verified state, and the next source correction required before staging can continue.

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

## First recovery implementation

A fail-closed recovery utility was added at `deploy/openbao/scripts/recover-datto-rmm-execution-staging.py` and source-controlled on the isolated workstream branch. Its design requires the proven partial state, validates the existing policy and AppRole before proceeding, requires `cas_required=true`, uses `options.cas=0` for a new execution KV record, verifies read-only secret version stability, verifies AppRole secret isolation, and creates bootstrap material atomically. It does not contact Datto or activate runtime execution.

The recovery attempt was pinned to source `8d26e6a5b75f936b0c2f41341258954da1097d3b`. Source pinning, isolated-clone validation, recovery-script compilation, source-contract validation, live-service baseline, bootstrap absence, and the final source pin all passed.

The recovery then stopped immediately after OpenBao administrative authentication with:

`ERROR: Existing Datto execution policy rules were unavailable.`

The temporary administrative token was revoked. The recovery did not prompt for or consume the Datto execution API key or secret on this attempt, did not contact Datto, did not activate runtime execution, did not activate provider writes, and did not restart MCP, runtime, or OpenBao.

## Root cause of the recovery failure

The recovery utility's policy-verification parser assumed that `GET /v1/sys/policies/acl/:name` returned the policy document under `data.rules`.

OpenBao's ACL policy API returns the policy document in the top-level `policy` field for this endpoint. The recovery therefore failed closed before any credential write because the expected field was unavailable.

This is a source parsing defect in the recovery utility, not evidence of policy loss or policy drift. The previously proven state remains authoritative until another read-only diagnostic or a corrected recovery run proves otherwise.

## Current verified state

As of the latest completed evidence:

- production runtime remains read-only;
- no Datto component has been executed;
- no Datto provider authentication has yet been attempted with the execution identity;
- the dedicated OpenBao execution policy exists;
- the dedicated OpenBao execution AppRole exists with the previously proven bounded token settings;
- the execution KV credential record remains unproven as created and must be treated as absent until revalidated;
- the existing Datto read-only secret remains at its previously proven version 1 and must not be modified by this workstream;
- no execution bootstrap credential directory had been created at the last successful diagnostic;
- no runtime execution surface has been activated;
- no general provider-write capability has been enabled;
- no service restart has been required by the staging attempts.

Because the second recovery failed before the KV-write stage, it is consistent with the earlier diagnostic state. We do not infer mutation from consistency alone; the next corrected recovery must re-prove all relevant preconditions before writing anything.

## Next step

Correct the recovery utility to parse the actual OpenBao ACL-policy read response while preserving fail-closed exact-policy comparison. Add focused tests for both the actual response shape and malformed/ambiguous policy responses. Then re-run source CI and perform another guarded recovery only after verifying the authoritative branch pin and the still-expected partial state.

After OpenBao staging completes, the next Phase 3 milestone is harmless Datto authentication and provider-containment proof. That milestone still must not execute a component or activate a runtime mutation surface.

## Related records

- Workstream: `docs/operations/Jason-Datto-RMM-Component-Execution-Workstream-2026-09-14.md`
- Draft PR: #184
- Capability objective: issue #183
