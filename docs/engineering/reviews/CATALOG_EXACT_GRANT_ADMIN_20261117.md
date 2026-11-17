# Autotask catalog: narrowly bounded Owner grant administration

**2026-11-17 — source-only, not production-deployed, no authority grants issued.**
**Risk:** high (authentication / authority administration). This candidate
implements the Owner-approved *preparation* of a catalog-only path. It is not
an authorization to merge without independent security review, promote a
production image, modify an Owner global allowlist, grant live authority, or
make an Autotask mutation.

## Problem and exact intent

Jason's existing `grant_exact_authority`, `list_exact_authority_grants`, and
`revoke_exact_authority_grant` actions require Owner-wide administration.
The installed `JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES=person-al`
recognizes only the legacy principal, while the authenticated regular Owner
has separate active Entra identity
`person-entra-bee80bdcffb04c50b453c09d4d411f5f`. The proposed broad
allowlist helper in draft PR #2519 is **on hold** because the same global
setting also governs Datto and other privileged workflows. The existing
separate Autotask execution identity correction is merged as PR #2515.

This candidate allows that already-bound regular Owner principal to administer
*only their own* four active AOT Autotask catalog `execute` grants, each with
`approval_required=true`. It does not turn the everyday account into an Owner
admin and does not use the human account to execute the external Autotask API.

## Fixed authority boundary

- **Opt-in MCP setting:**
  `JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE=aot-catalog-self-owner-v1`.
  Absent setting denies non-Owner administration; unexpected setting fails
  closed. The setting is a deployment configuration, never a caller argument.
- **Exact Entra claim binding:** tenant
  `f7054323-d52b-4863-8c2f-1898f0b6077c`, object
  `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`. Require the original MCP
  middleware's authenticated OAuth bearer, `entra-oauth-bearer` assurance,
  active, unscoped AOT person binding, and exact derived
  `person-entra-bee80bdcffb04c50b453c09d4d411f5f`. Email text and
  arbitrary user-supplied `subject_id` do not authenticate anything.
- **Fixed exact capability set:** `service.service.create`,
  `service.service.update`, `service.service.bundle.create`,
  `service.service.bundle.update`. Only `execute`; `approval_required=true`;
  `client_id=None`; grantee must equal the authenticated actor. The existing
  registered-capability, active-subject, exact-grant ID, audit, idempotency,
  and durable repository gates remain in force.
- **Readback and rollback:** the existing `list_exact_authority_grants`
  action shows **only** matching self-owned catalog execute grants in this
  narrow mode; unrelated grant metadata never escapes. The existing
  `revoke_exact_authority_grant` action may revoke only matching self-owned
  catalog grants by their exact IDs. Deny other subjects, operations, scopes,
  permission modes, approval-disabled grants, or revocation of unrelated IDs.
- **Clear audit:** the existing append-only authority audit records true
  principal, exact capability and grant ID. Restricted mutations additionally
  carry `CATALOG_SELF_GRANT_ADMIN` reason code. Fail closed before grant writes
  if audit is unavailable. No provider credential or access token is logged.
- **No wider role:** the global Owner allowlist, autonomous worker authority,
  Datto component approvals, playbook approvals, privileged client reads,
  ticket writes, and PMv4 remain unchanged. The separately configured V4
  `admin-separated-v1` admin profile cannot activate this fallback.
- **No new MCP action publication:** extend the existing, already published
  three exact-grant administration actions. A new MCP tool catalog update is
  not a prerequisite. Global Owner admin behavior is unchanged by default.

## Execution identity and release independence

The **separate** runtime connector feature (merged PR #2515) must be activated
through the independent setting
`JASON_AUTOTASK_CATALOG_AUTH_MODE=jason_managed` on the runtime. It selects
Jason's dedicated `autotask.write` AppRole/API-only Autotask execution account
for the four catalog writes, with no `ImpersonationResourceId`, while keeping
human requester authority and exact-action approval. This grant-admin code
only permits tightly bounded grant administration: it cannot activate the
runtime feature, change a provider credential, forge an exact action approval,
or authorize a broad production release.

## Verification

Isolated, no-network, read-only MCP container with no provider secrets or
production mounts: **87 tests passed** across catalog-grant administration,
legacy authority-admin, read authority-admin, release-owner identity,
procurement MCP handoff, and release-approval regressions. Tests cover four
positive actions; execution approval enforcement; idempotence and audit;
self-only and noncatalog denial; unknown/missing mode; wrong tenant/object,
principal, assurance and client context; cross-identity listing/revocation;
inactive identity and capability; missing audit; no shared Owner promotion;
Datto Owner-only controls remaining denied.

A separate Datto approval test module has ten failures in the no-session
container, all `MCP_AUTHENTICATION_REQUIRED`. The exact same ten failures
were reproduced on a clean protected-main baseline in the same test harness.
They are **not** claimed as passing or as caused by this change. The two
remaining Datto tests passed on both sources. Full provider-backed acceptance
has not occurred.

## Remaining independent gates

1. Independent security review of the exact fixed tenant/object, existing
   OAuth binding path, three modified MCP admin entrypoints, audit markers,
   security test cases, and non-overlap with global Owner powers.
2. Protected-source review and CI on exact candidate SHA. If merging source
   is separately approved, do so without treating the merge as deployment.
3. Governed **catalog-only** release ancestry and native preproduction with
   immutable runtime/MCP image digests, a verified running rollback SHA,
   production freeze preservation, and negative tests. The existing release
   gate rejects a catalog-only snapshot not reachable as an approved protected
   ancestor; broad `main` deployment is not approved merely to ship this fix.
4. Fresh authenticated Owner exact-release approval and independent host
   verification before any production mutation. Explicitly enable only the
   catalog-grant MCP profile and the catalog runtime service-identity mode.
5. After deployment, issue at most four exact self-owned AOT grants through
   the existing authenticated MCP tools. Each external Autotask create/update
   remains separately approved and must have provider readback and audit.
   The disposable inactive test record described in PR #2520 is **proposed
   only**; no write is authorized by this document.

**No direct production writes, root/Owner identity remapping, SDK token
forgery, unapproved image promotion, use of the broad shared Owner allowlist,
or deliberate restart of live Ticket Core or PMv4 is permitted.**
