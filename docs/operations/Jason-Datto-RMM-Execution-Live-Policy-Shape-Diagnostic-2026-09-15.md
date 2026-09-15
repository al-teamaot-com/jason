# Jason Datto RMM Execution Live OpenBao Policy Shape Diagnostic — 2026-09-15

## Purpose

This record captures the read-only live OpenBao diagnostic performed after the corrected Datto execution recovery parser still stopped fail-closed. The diagnostic was designed to identify the exact ACL-policy read response structure without printing policy contents, credentials, tokens, provider identifiers, or secret values.

## Preconditions and safety boundary

The diagnostic was pinned to workstream source `8ce06edebcfcf9e47194d2099b3657901e2c278f` and verified that source as the authoritative remote head before inspection.

The diagnostic made no OpenBao configuration or secret change, made no Datto provider request, made no runtime change, executed no component, and displayed no secret value. The temporary OpenBao administrative token was explicitly revoked.

## Proven live response shape

`GET /v1/sys/policies/acl/jason-datto-rmm-execution` returned HTTP 200. The live JSON response contained standard response envelope fields and a `data` mapping with these keys:

- `allow_slashes_in_identity_templates`
- `allow_wildcards_in_identity_templates`
- `cas_required`
- `modified`
- `name`
- `policy`
- `version`

The approved execution ACL policy text appeared exactly once at:

`$.data.policy`

The diagnostic compared strings only by normalized exact equality against the approved source policy. It did not print the policy body. `POLICY_EXACT_MATCH_COUNT=1` and `POLICY_EXACT_MATCH_PATH=$.data.policy` were proven.

This explains why both earlier recovery parsers stopped safely: the first expected `data.rules`; the second accepted top-level `policy` plus `data.rules`; neither accepted the actually observed `data.policy` field.

## Other state re-proven

The same read-only diagnostic re-proved:

- execution secret read returned HTTP 404;
- Datto read-only secret read returned HTTP 200;
- Datto read-only secret version remains 1;
- execution bootstrap directory remains absent;
- OpenBao configuration change: NO;
- OpenBao secret change: NO;
- Datto provider contact: NO;
- runtime change: NO;
- component execution: NO.

## Source correction

A narrow live-shape recovery wrapper was added at:

`deploy/openbao/scripts/recover-datto-rmm-execution-staging-live-shape.py`

It reuses the already-reviewed recovery transaction and replaces only the ACL-policy extraction function. The parser accepts:

- live observed `data.policy`;
- previously modeled top-level `policy`;
- compatibility `data.rules`.

If more than one representation is present, every representation must normalize to identical policy text or recovery fails closed.

Regression coverage was added at:

`deploy/openbao/tests/test_recover_datto_rmm_execution_live_shape.py`

Coverage includes the exact live `data.policy` shape, the earlier two shapes, identical multi-representation responses, missing policy text, conflicting representations, and proof that the base recovery policy-verification flow uses the corrected parser.

The focused `Validate Datto RMM Automation Foundation` workflow passed at source head `6becc09bf960eb9d0a1807cedc7dc466c214a0fc` in GitHub Actions run `34959276477`.

## Current boundary

OpenBao execution-secret staging has not yet completed. The next recovery attempt must re-prove the authoritative source pin, execution secret absence, read-only secret stability, bootstrap absence, service stability, and exact policy/AppRole containment before collecting or writing the separate Datto execution credential.

No Datto provider authentication, component execution, runtime execution activation, or general provider-write activation is authorized by this evidence record.

Related records:

- `docs/operations/Jason-Datto-RMM-Execution-Credential-Staging-2026-09-15.md`
- `docs/operations/Jason-Datto-RMM-Component-Execution-Workstream-2026-09-14.md`
- Draft PR #184
- Issue #183
