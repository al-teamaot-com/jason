# Jason Datto RMM Execution AppRole Token Lifecycle — 2026-09-15

## Purpose

This record captures the first harmless provider-proof attempt after successful staging of the separate Datto RMM execution credential, the OpenBao token-lifecycle failure that stopped the proof before Datto contact, and the bounded correction selected for the execution AppRole.

No credential value, OpenBao token, Datto API key, Datto API secret, RoleID, SecretID, provider-native object ID, or raw provider response is recorded here.

## Preconditions

Before this attempt, Phase 3 OpenBao execution-credential staging had completed successfully:

- `datto_rmm.execution` existed as isolated KV version 1;
- the dedicated execution ACL policy and AppRole were present;
- the existing `datto_rmm.readonly` secret remained unchanged;
- protected execution bootstrap material existed and passed post-checks;
- runtime execution and general provider writes remained disabled;
- no Datto component or quick job had been executed.

The execution AppRole had been configured with a five-minute service-token TTL, no default policy, only the dedicated execution policy, and `token_num_uses=2`.

## Harmless provider-proof attempt

The guarded harmless proof was pinned to workstream source `84ee903f9d95454276af52531feee5be8f162f58` and CI-validated probe source `0567d42ab1bc167a8a7fd46ec191dadd45c6f724`.

The run passed authoritative-source pinning, isolated checkout verification, CI-code-drift checks, credential-safe probe preflight, live-service baseline, execution-bootstrap checks, and the final source pin.

The live probe then failed while resolving `datto_rmm.execution` from OpenBao. The resolver successfully authenticated through the execution AppRole and reached the execution KV read. Its `finally` path then attempted `auth/token/revoke-self`, which returned HTTP 403. The exception was raised by `OpenBaoSecretResolver._revoke_token`.

The run reported:

- `DATTO_EXECUTION_IDENTITY_PROOF=FAIL`;
- provider mutation requests: 0;
- component execution: NO;
- no permission change should be made yet.

The failure occurred before the probe could perform the Datto OAuth exchange, so this attempt did **not** contact Datto.

## Root cause

The execution AppRole's two-use token budget is insufficient for the existing secret-resolver lifecycle.

For this path, the limited-use OpenBao token must support:

1. one authenticated KV read of the execution credential; and
2. an explicit `revoke-self` request performed by the generic resolver.

With `token_num_uses=2`, the observed OpenBao behavior consumes the limited-use token before the explicit revoke-self operation can complete, causing the revoke request to return HTTP 403. Treating revoke failure as harmless inside the generic resolver would weaken an existing security invariant and was rejected as the correction.

## Selected correction

The bounded correction is to change only the dedicated Datto execution AppRole token-use budget from 2 to 3 while preserving all other containment properties.

The intended lifecycle becomes:

1. execution KV read;
2. explicit `revoke-self`;
3. the token is proven unusable after explicit revocation, leaving the nominal third-use allowance unavailable in practice.

This keeps the generic resolver's explicit-revocation requirement intact. It does not broaden the ACL policy, provider permissions, provider identity, Device Visibility, API Component Level, runtime execution surface, or provider-write activation.

A guarded adjustment utility was added at:

`deploy/openbao/scripts/adjust-datto-rmm-execution-token-uses.py`

Its contract is fail-closed:

- it accepts only the exact previously approved AppRole shape with token use budget 2 or the exact target shape with budget 3;
- it rejects policy, TTL, token-type, SecretID, or other authority drift;
- it changes only the token-use budget when the predecessor state is present;
- it proves one execution-secret read followed by successful explicit revoke-self;
- it proves the revoked token can no longer read the execution secret;
- it updates only the protected bootstrap metadata describing the use budget;
- it does not contact Datto;
- it does not activate runtime execution or provider writes;
- it does not execute a component or quick job.

Focused tests were added at:

`deploy/openbao/tests/test_adjust_datto_rmm_execution_token_uses.py`

The `Validate Datto RMM Automation Foundation` workflow completed successfully at source head `130b64645d4b7164d7fa5caa2c171e0a9316f8d3` in Actions run `34960333100`.

## Current security boundary

Until the guarded adjustment is run successfully:

- production remains read-only;
- the execution credential remains staged but not runtime-activated;
- no Datto authentication has yet been proven through the execution identity;
- no Datto provider request from the execution identity has completed;
- no provider mutation has occurred;
- no component or quick job has been executed;
- no service restart is required.

## Next step

Run the CI-validated AppRole token-use adjustment against live OpenBao, prove explicit revocation, and then rerun the already bounded harmless Datto authentication/negative-permission probe. The provider proof remains GET-only after OAuth and must not execute a component or activate a runtime mutation surface.

If that proof succeeds, record authentication and the negative Global Settings privilege boundary as proven. Device Visibility and API Component Level still require separate positive/negative containment evidence and must not be inferred solely from authentication.
