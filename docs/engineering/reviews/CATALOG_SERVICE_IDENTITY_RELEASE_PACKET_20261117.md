# Autotask catalog service-identity release packet (engineering only)

**Production status: NOT DEPLOYED. This document is NOT release approval.**

## Exact reviewed correction

- Merged change: PR #2515, merged main revision
  `8ca93c958498c50d1b858f7e8c138c98ddaa2ede`.
- Four catalog operations only: `service.service.create`,
  `service.service.update`, `service.service.bundle.create`,
  `service.service.bundle.update`.
- The catalog write credential remains the existing `autotask.write` OpenBao
  AppRole path, distinct from the read credential. The deployment setting
  `JASON_AUTOTASK_CATALOG_AUTH_MODE=jason_managed` selects the credential's
  API execution identity rather than provider-native human impersonation.
- The human caller remains authenticated, authorized, exact-action approved,
  and auditable. Invalid deployment configuration fails closed; other
  procurement operations and ticket processing preserve their old behavior.

## Tested isolated runtime artifact

- Source baseline / currently running production:
  `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
- Catalog-only source snapshot:
  `f4969faab5d509e8aa06db7445ef84e1cac46d16`.
- Exactly 4 changed files versus the production source: connector,
  service-account tests, exact-plan test, and review memo.
- Candidate runtime image tag:
  `jason-runtime:catalog-service-identity-isolated-f4969faab5d5`.
- Candidate image ID:
  `sha256:85613d33e5bcdcf77c956b1f8a2bb72841a40ffb42c275bd385ff2dc5837a394`.
- Original live runtime image ID:
  `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`.
- Original live MCP image ID:
  `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`.
- Full live source/runtime/MCP alignment and healthy runtime were observed.
  Production freeze stayed active and unchanged.

## Verification without provider mutation

- 63/63 focused catalog / procurement / mutation / exact-plan tests passed,
  including all 4 operations, omitted impersonation header, caller audit,
  missing/invalid mode denial, per-account permission checks, approval-plan
  invalidation and wrong-ID readback denial.
- Four GitHub workflows passed on the merged catalog PR branch.
- Isolated Docker build PASS; non-network, read-only, non-root container
  import and `jason_managed` mode verification PASS.
- The native `deploy_live_container.py --preflight` returned PASS with the
  exact isolated image, `--harden`, and only one added environment setting.
  It reported 40 original mounts and one secondary network, no new binds.
- Live governed provider reads, *not writes*, completed for an existing
  service record and service-bundle search. No test record was created.
- Canonical `provider_secret.py status autotask_write --check-only` passed
  without network contact or secret values; this does not verify the actual
  credential username/provider account permissions.

## Current release-blocker evidence

The installed native release process requires a protected-main/reviewed
ancestor and an independently approved exact release. The source snapshot
`f4969faab...` is **not an ancestor of protected main** even though its four
changed file contents agree with the merged correction; the reviewed
protected-ancestor policy rejects candidates whose newer history touches
candidate files or release controls. The newer main commits touch all four
catalog paths and `tools/manual_release_scope.py`,
`config/production-desired-state.json`, and
`config/release-manager-policy.json`. The resulting broad main release also
includes numerous unrelated PMv4 and other changes. Do not promote a broad
main build as a narrow catalog fix; do not relabel this Docker image with a
false source SHA or bypass the native Release Manager.

The Owner admin grant path is separately unavailable: the installed MCP has
`JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES=person-al` and the current
regular Entra Owner's grant-admin call returns
`AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED`. The proposed global-Owner allowlist maintenance is **DRAFT/HOLD**: expanding
that shared list also broadens Datto component, procurement, autonomy and
other Owner functions. See DRAFT PR #2519 (held and unmerged).
It has not been run and is not authorized as a catalog-only change. Either
separately approve the disclosed broader Owner authority or use a separately
governed, strictly catalog-scoped privileged grant administration path; then
issue only four explicit, approval-required grants via native Jason authority.

## Completion gates and rollback

1. Resolve requester grant administration **without accidental broad Owner
   privilege expansion**. The proposed global allowlist helper is on HOLD,
   and any broader-scope option needs separate exact Owner review. A
   catalog-scoped privileged-admin path is safer if approved and available.
2. Obtain a production-eligible, scope-reviewed **catalog-only** immutable
   candidate through an authorized Release Manager source/ancestry procedure
   or an independently approved component-specific release contract. The
   source-only image above does not presently pass that release gate.
3. Independently attest exact candidate source/image, rollback image/source,
   changed-source scope, protected controls, live identity profile and freeze.
4. Require a fresh authenticated Owner exact-SHA release approval; consume
   through the native release transaction and verify live SHA and health.
5. Require a separate exact approval for a safe, named test catalog record;
   execute via Jason's governed write capability, verify every submitted
   provider field, confirm no `ImpersonationResourceId` on these 4 operations,
   confirm human audit attribution and denial-is-zero-writes. Any cleanup
   mutation needs its own exact authorization.

The rollback baseline is the preserved verified running runtime image and
revision above; an executable rollback transaction/receipt must be prepared
and verified before any promotion. No rollback has been exercised against
production. Preserve original MCP, all Ticket Core/PMv4 processes, provider
secrets, and the production freeze throughout.
