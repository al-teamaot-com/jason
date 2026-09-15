# Jason Datto RMM Execution Identity Harmless Provider Proof — 2026-09-15

## Purpose

This record captures the first successful provider contact made with the separately staged Datto RMM execution identity. The proof was deliberately non-mutating and was limited to OAuth authentication plus GET-only permission-boundary checks.

No credential value, OpenBao token, Datto API key, Datto API secret, RoleID, SecretID, provider-native object ID, raw provider response body, or bearer token is recorded here.

## Preconditions

Before this proof:

- Phase 3 provider identity / containment had explicit owner approval;
- a separate Datto execution API identity had been created by the owner;
- `datto_rmm.execution` existed in OpenBao as isolated KV version 1;
- the existing `datto_rmm.readonly` secret remained unchanged;
- the execution AppRole bootstrap material existed and passed protected-file checks;
- runtime execution remained disabled;
- provider-write activation remained disabled;
- no Datto component or quick job had been executed.

A prior harmless proof attempt revealed that the dedicated execution ACL policy lacked explicit `update` authority on `auth/token/revoke-self` while the AppRole intentionally had `token_no_default_policy=true`. A bounded repair added only that self-revocation capability and restored the approved two-use execution token budget.

## Guarded live repair

The successful guarded run was pinned to authoritative workstream source `344fba3386ed2dd68f58195d3e5a92d7d5085ea8` and CI-validated repair source `4cdaee41a9ab26db7ebc988045954811ecf541a1`.

Before any OpenBao change it passed:

- authoritative branch-head verification;
- isolated clone source pinning;
- repository fsck and clean-worktree checks;
- CI-code-drift verification;
- local source compile and credential-safe probe preflight;
- live OpenBao / MCP / runtime service baseline;
- execution bootstrap-material checks;
- final authoritative source pin.

The bounded OpenBao repair then proved:

- execution ACL policy permits `read` only on the isolated execution credential;
- execution ACL policy permits `update` only on `auth/token/revoke-self` for token self-destruction;
- execution AppRole token-use budget is restored to 2;
- one execution KV read succeeds;
- explicit `revoke-self` succeeds;
- post-revocation execution-secret access is denied;
- the temporary administrative token is revoked;
- no Datto provider request occurs during the repair;
- no runtime execution or provider-write surface is activated;
- no component or quick job is executed.

## Harmless Datto provider proof

After the OpenBao lifecycle proof succeeded, the staged `datto_rmm.execution` identity was used for the first provider contact.

The probe performed only:

1. OAuth authentication using the staged execution identity;
2. `GET /api/v2/system/status` as the positive authentication check;
3. GET-only account / account-devices / account-components requests that require Global Settings View, which the execution identity is intentionally not granted.

Observed sanitized results:

- OAuth authentication: PASS;
- system status HTTP status: 200;
- account HTTP status: 403;
- account devices HTTP status: 403;
- account components HTTP status: 403;
- negative Global Settings privilege boundary: PASS;
- provider mutation requests: 0;
- component execution attempted: NO;
- access token persisted: NO;
- provider response bodies printed: NO;
- provider response bodies persisted: NO;
- runtime execution activated: NO.

This proves that the execution identity can authenticate successfully without carrying the broader Global Settings authority used by the read-only account-wide discovery identity.

## Service stability

After the proof, the OpenBao, MCP, and runtime container identities were unchanged and all remained running. No service restart or container recreation occurred.

## What is proven

The following Phase 3 controls are now proven live:

- the separate `datto_rmm.execution` credential is usable;
- its OpenBao AppRole lifecycle is bounded and explicitly self-revoking;
- its short-lived service token uses the approved two-request lifecycle;
- Datto OAuth authentication succeeds;
- the execution identity does not have Global Settings View authority;
- the proof path is non-mutating;
- runtime execution remains disabled;
- no component / quick job has been executed.

## What remains unproven

Two provider-side containment controls remain to be evidenced independently:

1. **Device Visibility** — prove a known in-scope device is visible to the execution identity and a known out-of-scope device is not visible, without mutating either device.
2. **API Component Level** — prove the execution identity is constrained to the intended pilot component set using a non-mutating provider read or other authoritative provider evidence. This must not be inferred solely from successful OAuth authentication or from the negative Global Settings proof.

## Current security boundary

Production remains read-only. `automation.component.execute` is not activated in runtime composition, the live Datto mutation executor remains disabled, and no provider write has been performed.

Separate explicit approval remains required before deploying a runtime execution surface or running the first live component / quick job.
