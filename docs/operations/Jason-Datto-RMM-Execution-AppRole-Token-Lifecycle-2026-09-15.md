# Jason Datto RMM Execution AppRole Token Lifecycle — 2026-09-15

## Purpose

This record captures the first harmless provider-proof attempt after successful staging of the separate Datto RMM execution credential, the OpenBao self-revocation failure that stopped the proof before Datto contact, the initially incorrect token-use diagnosis, and the corrected least-privilege repair.

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

## First harmless provider-proof attempt

The guarded harmless proof was pinned to workstream source `84ee903f9d95454276af52531feee5be8f162f58` and CI-validated probe source `0567d42ab1bc167a8a7fd46ec191dadd45c6f724`.

The run passed authoritative-source pinning, isolated checkout verification, CI-code-drift checks, credential-safe probe preflight, live-service baseline, execution-bootstrap checks, and the final source pin.

The live probe then failed while resolving `datto_rmm.execution` from OpenBao. The resolver successfully authenticated through the execution AppRole and reached the execution KV read. Its `finally` path then attempted `auth/token/revoke-self`, which returned HTTP 403. The exception was raised by `OpenBaoSecretResolver._revoke_token`.

The run reported:

- `DATTO_EXECUTION_IDENTITY_PROOF=FAIL`;
- provider mutation requests: 0;
- component execution: NO;
- no permission change should be made yet.

The failure occurred before the probe could perform the Datto OAuth exchange, so this attempt did **not** contact Datto.

## Initial diagnosis and failed correction

The first diagnosis attributed the HTTP 403 to the two-use token budget. A bounded source change temporarily targeted `token_num_uses=3` while preserving the generic resolver's explicit-revocation behavior. Focused CI passed at source head `130b64645d4b7164d7fa5caa2c171e0a9316f8d3` in Actions run `34960333100`.

The guarded live adjustment then changed the dedicated execution AppRole to the three-use target and immediately performed its safety proof. After one successful execution-secret KV read, `auth/token/revoke-self` still returned HTTP 403.

That second observation disproved the use-budget diagnosis. Datto was still not contacted, no component ran, runtime activation remained disabled, and provider writes remained disabled.

## Corrected root cause

The execution AppRole is deliberately configured with `token_no_default_policy=true`. Its dedicated ACL policy originally granted only:

- `read` on `secret/data/connectors/datto-rmm/production/execution`.

It did **not** grant `update` on `auth/token/revoke-self`.

The generic `OpenBaoSecretResolver` performs exactly this limited-token lifecycle for the execution credential:

1. AppRole login creates the short-lived service token;
2. one authenticated KV read resolves the credential;
3. the resolver explicitly calls `auth/token/revoke-self` in its `finally` path.

Because the token carries no default policy, the self-revocation endpoint must be explicitly authorized by the dedicated execution policy. The missing self-revocation capability, not the original two-use budget, caused the HTTP 403.

OpenBao documents that a limited token's use count is decremented on each authenticated request. Therefore the approved two-use budget is sufficient for the intended lifecycle: one KV read plus one self-revocation request. The self-revocation request itself destroys the token.

## Corrected least-privilege repair

The source-controlled execution ACL policy now grants exactly two capabilities:

1. `read` on the isolated Datto execution credential; and
2. `update` on `auth/token/revoke-self`.

No general token-management path is granted. No read-only Datto credential path is added. No wildcard is added.

The guarded repair utility at:

`deploy/openbao/scripts/adjust-datto-rmm-execution-token-uses.py`

has been corrected to:

- accept only the exact legacy policy or the exact corrected policy;
- reject any extra policy authority;
- accept only the exact approved AppRole shape with token-use budget 2 or the transient failed-adjustment state with budget 3;
- install the corrected self-revocation policy when the legacy policy is present;
- restore `token_num_uses=2` if the failed adjustment left it at 3;
- prove one execution-secret read;
- prove successful explicit `revoke-self`;
- prove the revoked token can no longer read the execution secret;
- update only the protected bootstrap metadata describing the corrected lifecycle;
- avoid all Datto provider contact;
- avoid runtime execution activation, provider-write activation, component execution, and service restart.

Focused tests at:

`deploy/openbao/tests/test_adjust_datto_rmm_execution_token_uses.py`

prove the exact two-use target, the bounded 3-to-2 recovery state, exact policy transition, denial of extra authority, live `data.policy` response compatibility, and drift rejection.

`Validate Datto RMM Automation Foundation` passed the corrected repair at source head `4cdaee41a9ab26db7ebc988045954811ecf541a1` in Actions run `34961030873`.

## Current security boundary

Until the corrected guarded repair is run successfully:

- production runtime remains read-only;
- the execution credential remains staged but not runtime-activated;
- the execution AppRole may be in the transient three-use state from the failed adjustment;
- the live execution ACL policy still lacks proven self-revocation capability until the repair succeeds;
- no Datto OAuth authentication has yet been completed through the execution identity;
- no provider mutation has occurred;
- no component or quick job has been executed;
- no service restart is required.

## Next step

Run the CI-validated self-revocation policy repair against live OpenBao. It must restore the exact two-use AppRole budget and prove explicit token revocation before any Datto contact.

Only after that proof passes should the already bounded harmless Datto authentication/negative-permission probe run. The provider proof remains non-mutating and must not execute a component or activate a runtime mutation surface.

If that proof succeeds, record authentication and the negative Global Settings privilege boundary as proven. Device Visibility and API Component Level still require separate positive/negative containment evidence and must not be inferred solely from authentication.
