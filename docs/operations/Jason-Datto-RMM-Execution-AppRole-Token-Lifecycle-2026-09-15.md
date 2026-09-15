# Jason Datto RMM Execution AppRole Token Lifecycle — 2026-09-15

## Purpose

This record captures the first harmless provider-proof attempt after successful staging of the separate Datto RMM execution credential, the OpenBao self-revocation failure that stopped the proof before Datto contact, the initially incorrect token-use diagnosis, the corrected least-privilege repair, and the successful live proof.

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

The approved two-use budget is sufficient for the intended lifecycle: one execution-credential read plus one explicit self-revocation request. The self-revocation request destroys the token.

## Corrected least-privilege repair

The source-controlled execution ACL policy now grants exactly two capabilities:

1. `read` on the isolated Datto execution credential; and
2. `update` on `auth/token/revoke-self`.

No general token-management path is granted. No read-only Datto credential path is added. No wildcard is added.

The guarded repair utility at:

`deploy/openbao/scripts/adjust-datto-rmm-execution-token-uses.py`

was corrected to:

- accept only the exact legacy policy or the exact corrected policy;
- reject any extra policy authority;
- accept only the exact approved AppRole shape with token-use budget 2 or the transient failed-adjustment state with budget 3;
- install the corrected self-revocation policy when the legacy policy is present;
- restore `token_num_uses=2` if the failed adjustment left it at 3;
- prove one execution-secret read;
- prove successful explicit `revoke-self`;
- prove the revoked token can no longer read the execution secret;
- update only the protected bootstrap metadata describing the corrected lifecycle;
- avoid all Datto provider contact during the OpenBao repair;
- avoid runtime execution activation, provider-write activation, component execution, and service restart.

Focused tests at:

`deploy/openbao/tests/test_adjust_datto_rmm_execution_token_uses.py`

prove the exact two-use target, the bounded 3-to-2 recovery state, exact policy transition, denial of extra authority, live `data.policy` response compatibility, and drift rejection.

`Validate Datto RMM Automation Foundation` passed the corrected repair at source head `4cdaee41a9ab26db7ebc988045954811ecf541a1` in Actions run `34961030873`.

## Successful live repair and provider proof

The guarded repair-and-proof run was pinned to authoritative source `344fba3386ed2dd68f58195d3e5a92d7d5085ea8` and the CI-validated repair head above.

The live OpenBao repair succeeded and proved:

- the execution ACL now explicitly permits only self-revocation in addition to the isolated execution-secret read;
- the execution AppRole token-use budget is restored to 2;
- one execution KV read succeeds;
- explicit `revoke-self` succeeds;
- post-revocation execution-secret access is denied;
- the temporary administrative token is revoked;
- no Datto provider request occurs during the repair.

After that OpenBao proof passed, the staged execution identity was used for the first harmless Datto provider contact. The provider proof returned:

- OAuth authentication: PASS;
- `GET /api/v2/system/status`: HTTP 200;
- account read requiring Global Settings View: HTTP 403;
- account devices read requiring Global Settings View: HTTP 403;
- account components read requiring Global Settings View: HTTP 403;
- provider mutation requests: 0;
- component execution attempted: NO;
- runtime execution activated: NO;
- access token persisted: NO;
- provider response bodies printed or persisted: NO.

The service-stability post-check passed. OpenBao, MCP, and runtime containers were not recreated or restarted.

The successful provider-proof details are recorded separately in `docs/operations/Jason-Datto-RMM-Execution-Identity-Harmless-Provider-Proof-2026-09-15.md`.

## Current security boundary

- production runtime remains read-only;
- the execution credential remains staged but not runtime-activated;
- the execution ACL contains only execution-secret read plus token self-revocation;
- the execution AppRole is back at the approved two-use token budget;
- Datto OAuth authentication through the execution identity is proven;
- the execution identity is proven not to carry Global Settings View authority;
- no provider mutation has occurred;
- no component or quick job has been executed;
- no service restart is required.

## Remaining Phase 3 containment evidence

Two provider-side controls remain to be independently evidenced:

1. Device Visibility — prove a known in-scope endpoint is visible and a known out-of-scope endpoint is denied, using GET-only provider requests.
2. API Component Level — prove the execution identity is limited to the intended pilot component set using non-mutating authoritative evidence.

Neither control is inferred solely from OAuth success or the negative Global Settings proof.

Separate explicit approval is still required before runtime execution activation or the first live component / quick job.
