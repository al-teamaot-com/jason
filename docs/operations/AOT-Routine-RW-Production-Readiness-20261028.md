# AOT Routine RW — Production Readiness and Activation Runbook
**Date:** 2026-10-28
**Status:** Candidate source/integration testing; production promotion and provider acceptance NOT performed.
**Release policy:** Existing Production Manager exact-SHA release process. Production freeze and unattended incident hold remain active.

## Scope and intended behavior
This release candidate combines three bounded, existing-governance RW pathways:
1. Autotask: routine human technician ticket create, ticket update and internal note, using existing provider-native Autotask impersonation and exact intent/plan approval.
2. IT Glue: notes-only update of one unrestricted IT Glue configuration, with exact client-to-organization verification, prior-revision conflict detection, one PATCH and post-write GET.
3. Microsoft Entra: standard, **disabled cloud-only** user creation under an approved customer onboarding request, exact UPN, verified cloud source directory, pre-existing sealed initial password, one Graph POST and independent post-write GET. Licensing, groups, secure password handoff and account enablement are separately authorized downstream operations; this candidate is not an entire onboarding workflow.

This reuses JKD-001, J-102, the Central Orchestrator, the existing capability/provider registry and existing OpenBao. There is NO blanket admin grant, no direct provider execution outside the orchestrator, and no routine authorization for disruptive or privileged operations.

## Feature flags — default OFF

| Capability | Runtime environment value | Required extra dependency |
| --- | --- | --- |
| Autotask routine human RW | `JASON_AOT_ROUTINE_RW_PROFILE=autotask-ticket-v1` | Existing active Autotask ticket-create/update/note profiles and impersonation/mutation gates |
| IT Glue configuration notes | `JASON_IT_GLUE_ROUTINE_RW_PROFILE=configuration-notes-v1` | Separate IT Glue write API key, client boundary, exact per-client technician grant |
| Entra standard cloud user creation | `JASON_ENTRA_STANDARD_USER_CREATE_PROFILE=cloud-user-v1` | Dedicated Graph application with User.Create permission, distinct certificate/credential, authorized client cloud-source boundary, request-specific sealed initial credential, exact per-client technician grant |

Unset each value or use any other value to keep its capability disabled. The production Compose file sets all three to empty by default. For IT Glue and Entra, profile-on alone is insufficient: the registry does not activate without the exact mounted non-empty AppRole bootstrap files.

## Provider-specific prep: IT Glue
- Provision a **dedicated** IT Glue API user/key that can update only the intended configurations. Verify the provider account's effective rights; an OpenBao role does not limit privileges granted by the actual IT Glue API key.
- Provision an OpenBao AppRole with only the `jason-itglue-configuration-notes-write-policy.hcl` read policy and secret `secret/data/connectors/it-glue/production/configuration-notes-write` containing `api_key`.
- Mount a **separate**, root-protected AppRole role_id/secret_id pair to the runtime paths under `/run/jason-secrets/openbao/it-glue-write/`. Neither the read-only IT Glue AppRole nor key is usable as fallback.
- Create and independently verify a Jason `ClientBoundary` for the exact client with provider `it_glue`, profile `configuration-notes-v1`, validated status, and the numeric IT Glue organization ID as its external tenant ID.
- Confirm the controlled test configuration's exact ID, actual organization ID, unrestricted state, existing notes and last-updated marker are returned by the provider API. **If the provider does not expose the required unrestricted/revision attributes, leave the capability disabled and implement verified equivalent evidence before activation.**
- An authorized owner grants `documentation.configuration.update` **execute/approval_required=true** for exact `client_id` to the technician through Jason's existing `grant_exact_authority` tool; not blanket organization-wide authority.

## Provider-specific prep: Microsoft Entra
- Prepare a separate, consented Microsoft Graph application using the least privilege appropriate for creating regular users (Microsoft Graph User.Create, validate permissions in actual tenant). Do NOT reuse the existing directory-read application.
- Create a validated `ClientBoundary` for provider `microsoft_graph_user_create`, profile `user-create`, exact managed client, approved app ID and Microsoft tenant GUID, primary managed domain, `external_scope_ids` including `source:entra_cloud`. Cross-check it matches the independently validated client's `microsoft_graph` `directory-read` boundary.
- Create the distinct OpenBao certificate credential secret `secret/data/connectors/microsoft-graph/production/user-create` (private_key_pem, certificate_pem, certificate_thumbprint, generation), and separately mount its least-privilege AppRole.
- Create a distinct AppRole for reading the exact hashed onboarding-password secret path `secret/data/connectors/microsoft-graph/onboarding-passwords/<sha256(client_id|request_id|upn)>`; it must not have general credential, token or provider privileges. Provision each sealed credential *before* invoking user creation. Provide out-of-band secure delivery to authorized users; do not return password in chats or ticket notes.
- The owner grants `identity.user.create` execute/approval_required=true for an exact client/technician through the existing Jason owner-only grant administration. No organization-wide multi-tenant user-create grant.
- The technician independently verifies the client requester/contact and Autotask ticket, then uses `attest_standard_user_onboarding_request(client_id, ticket_number, user_principal_name, customer_contact_id, contact_verified=true)` to create a 30-minute, exact-UPN attestation receipt. **This records a human attestation, not automated proof of contact identity; do not attest without checking source evidence.** Put receipt's `onboarding_request_id` and exact client_id into the subsequent governed `identity.user.create` request.
- For AD-synchronized, hybrid, privileged, guest, MFA recovery, privileged groups, purchased licenses, mailbox delegation or already-existing UPNs, do not use this cloud-only create operation.

## Exact authorized action flows
**Autotask:** authenticated AOT technician → exact active ticket capability → existing Autotask Resource impersonation → independent provider-native authorization → J-102 plan fingerprint/approval → mutation → reread/verify.

**IT Glue:** authenticated AOT technician submits `client_id` and exact configuration id/notes → MCP consumes client_id as a control argument → JKD-001 exact per-client grant and exact short-lived approval → trusted validated client-to-IT Glue organization binding → preimage check → one notes-only PATCH → independent GET.

**Entra:** authenticated AOT technician attests the authorized client ticket/contact and exact requested UPN → existing JKD-001 approval record → exact per-client execution grant → validated client/source/tenant and credential bound to the request → plan commitment → duplicate UPN check → exactly one disabled standard user POST → independent GET/readback. No license/group/user activation without separately accepted workflow.

## Preproduction acceptance — required before declaring production ready
1. Confirm current protected GitHub `main` SHA and all merged PRs since known-good runtime; check open PR/file overlaps and local worktrees. Never overwrite another developer's work.
2. Green GitHub validation (including AOT Routine RW CI, MCP discovery, security regressions), code review and exact tested SHA. Document file-level scope and provider credential requirements.
3. Build an immutable preproduction runtime/MCP pair from exact SHA **with production mutations OFF** and separate test-state files; run independent compile/import/Compose validation.
4. Verify the three feature flags OFF: Autotask existing read remains functional; IT Glue/Entra remain BUILDING/undiscoverable. Test that missing AppRoles, missing client mapping, wrong tenant, inactive technician and unknown capabilities fail closed.
5. Set up dedicated **non-production** provider test credentials and a verified test client. Test one reversible Autotask ticket field change and one internal note; then a controlled IT Glue notes change (and compensate using an authorized second change); finally creation of a disabled disposable Entra test user. Check no admin/extra license/group rights, and independently reread exact target. No live test customer action without approval.
6. Prove duplicate/ambiguous delivery, stale note preimage, revoked grant, invalid/wrong tenant, non-human identity, disabled flags, missing AppRole, password leakage, expired exact-UPN authorization, cross-client request and provider-403 tests. Record only non-sensitive verification metadata.
7. Verify rollback: ensure precise previous known-good release artifact, PM/circuit status, and ability to disable each profile; never delete created user automatically.
8. Independently execute current foundational Autotask count → **complete pagination** → exact ticket read and other core affected read canaries both before and after deployment under **real authenticated AOT human** identity; HTTP health alone is insufficient.
9. Only after the Owner explicitly issues an **exact-SHA freeze exception** and PM review/preproduction acceptance, use the native governed PM prepare/review-impact/promote transaction. Do not remove freeze/incident-hold markers or run direct Docker/shell promotion.

## Rollback and operator outcomes
Turning off a profile through a governed release prevents future writes, even if a durable exact authority grant or external credential persists. Revoke individual client grants and AppRoles if a source is compromised. A successful Graph account creation is **not** undone by silently deleting the account; follow separately authorized offboarding. A failed post-write provider read is **unverified**, never a claim of successful completion. Record exact correlation and error state.

## Explicit unverified external conditions at source-PR close
At source-build time, write credentials and OpenBao AppRoles were not provisioned, client write boundaries/permissions were not independently verified in production, no controlled live provider mutation was attempted, and no PM preproduction image/functional canaries were run. The deployment freeze and incident hold remained active. These are acceptance gates, not code-completion claims.

## Concurrent MCP read work (#2110)
PR #2110 is an independently gated Autotask **read** preproduction change.
Its reviewed MCP server patch touches `_contract_client_context_for_identity`
and `_governed_read` for staff contract/company scoping; this RW candidate
changes `_governed_execute`, imports the exact-client write selector and
adds a separate onboarding attestation tool. The functions do not overlap.
That source review is recorded in PR #2125's Integration coordination field.
Do not merge or pre-approve #2110 as part of this release candidate.

## MCP/runtime release parity and offline acceptance
Jason's MCP container composes a separate runtime registry. Both native
`infrastructure/jason-mcp/production-deploy.sh` and
`infrastructure/jason-runtime/production-deploy.sh` now forward explicitly configured routine-RW
profiles and six dedicated AppRole bind mounts. It preserves previous settings when
no profile override was given and rejects incomplete, empty or symlinked credential
mount pairs. These are source-only changes; no live container has been modified.

New offline preproduction tests compose the complete Jason runtime with
temporary SQLite databases and inert synthetic credential files. They establish:
profile unset means no write-capability registration; profile enabled without
credential files remains disabled; synthetic complete pairs register the exact
two provider invokers; and a missing Entra onboarding-credential pair leaves
Entra disabled while independently configured IT Glue remains available.
These simulated tests never send a provider mutation.

### Independent read-only prerequisite findings
- Release-control last-known-good revision:
  `b40c2f4a47e60e31e2241e4a4d55759242c2b580`. Its runtime and MCP
  Docker images and source-release directory were verified present.
- The connected `al` SSH shell cannot run `sudo -n`; OpenBao is healthy,
  but there are no provisioned dedicated RW AppRole bootstrap credentials.
  An authorized administrator must provide an approved provisioning mechanism
  before actual write secrets can be staged.
- The only currently verified Microsoft Graph directory-read boundary in
  the inspected registry maps to AOT's existing internal tenant
  (`client-aot-internal`, `teamaot.com`), not a separately verified isolated
  test tenant. Do not create a test identity in that real tenant on this
  testing authorization alone.
- The governed IT Glue read path confirmed XYZ Test Company and unrestricted
  configuration records with organization, notes and update timestamps.
  A dedicated IT Glue write user/API key is still required for an actual test.

This evidence does not satisfy administrative consent, dedicated write-token
provisioning, test-tenant validation, live write acceptance, PM preproduction,
or exact-SHA production authorization.

## OpenBao AppRole commissioning and concurrent PR review — 2026-10-29
The AOT owner executed the approved interactive one-time local provisioning script
with administrator credentials entered only into the host terminal. The observed
non-secret receipts were:

- `APPROLE_CREATED_AND_PROTECTED=jason-itglue-configuration-notes-write`
- `APPROLE_CREATED_AND_PROTECTED=jason-microsoft-graph-user-create`
- `APPROLE_CREATED_AND_PROTECTED=jason-microsoft-graph-onboarding-password`
- `APPROLE_PROVISIONING=PASS`, `PRODUCTION_DEPLOYMENT=NO`,
  `PROVIDER_API_KEYS_CREATED=NO`, `TEMPORARY_ADMIN_SESSION_REVOKED=YES`

OpenBao remains initialized and unsealed. Noninteractive `al` cannot inspect
root-only bootstrap files and must not bypass root custody. Dedicated provider
API keys, Graph application consent, exact client mappings, and genuine write
acceptance are **not** supplied by AppRole creation alone.

The currently deployed protected release advanced independently to
`d71cde5d24bdd65e67cb5c44d29eaf5f104edcbf`. This is now the release
controller's recorded **last known good** and both live container source
revisions. The prior LKG `b40c2f4a47e60e31e2241e4a4d55759242c2b580`
remains in the recorded previous slot. Future exact-SHA release review must use
the **current** verified rollback SHA, not the original 2026-10-28 snapshot.
The full combined RW source branch was merged non-destructively with latest
protected main; focused tests passed and the isolated worktree remained clean.

Two overlapping PRs were reviewed without being modified or merged:

- **PR #2128**: the current exact source tree matched the reconciled PR #2125
  tree, so there is no distinct file-content delta to apply. This is a duplicate
  release-candidate source line, not additional permission to deploy.
- **PR #2137**: intentionally narrow Autotask-only Stage B1 release. It changes
  the MCP/runtime deployment scripts and Compose file by limiting rollout to
  the opt-in Autotask profile, whereas this candidate also includes separately
  disabled IT Glue and Entra capabilities. The difference is intentional and
  must be resolved by release sequencing rather than merging both rollout
  policies blindly. Preserve the independent Autotask-first pilot.

The provider credential next step is dedicated IT Glue custom API key creation
under IT Glue **Admin > Settings > API Keys**, with *Password Access disabled*.
A source-independent, local-only staging helper was prepared at
`/home/al/jason-admin-tools/stage-itglue-rw-api-key.py`. Its `--check-only`
mode passed against the unsealed local OpenBao. It accepts the key and OpenBao
administrator password via non-echoing local terminal prompts and uses KV v2
CAS=0 to prevent overwrite; it has **not** been run with a key. Vendor key
creation is via the IT Glue administrator UI and cannot be silently inferred
from existing read-only credentials.
