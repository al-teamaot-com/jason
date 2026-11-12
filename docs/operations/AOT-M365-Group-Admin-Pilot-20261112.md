# AOT Microsoft 365 Group Administration Pilot — Consent and Release Handoff

**Current status (2026-11-12):** AOT administrator created both app registrations and independently read back each exact application permission grant through Microsoft Graph PowerShell. Restricted staging certificate pairs have been generated. Public certificates are on the Owner's PC; Entra certificate upload and governed OpenBao provisioning remain pending. No group, membership, credential in production runtime, or deployment was changed.

## Verified AOT facts (2026-11-12)

- Client in Jason's durable Microsoft boundary registry: `client-aot-internal`.
- AOT tenant: `f7054323-d52b-4863-8c2f-1898f0b6077c`, domain `teamaot.com`.
- Existing validated `microsoft_graph / directory-read` app: `c94301b7-7194-46ab-aab7-94f9366f51a9` (do not modify or broaden; it supports current Jason user reads and Teams identity enrichment).
- Validated mail-related applications also exist; these are unrelated and must not be repurposed.
- No `microsoft_graph_group_read` or `microsoft_graph_group_write` boundary was present for AOT in the read-only production registry check prior to application onboarding. Do not register as VALIDATED until certificate/token and consent are independently rechecked.
- Jason's governed `identity.user.read` succeeded for `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`, the enabled regular AOT account associated with `al@teamaot.com`.
- Live Jason capability discovery returns no registered active `identity_group` mutation capability.
- Project Jason PR #2454 contains the shared implementation, not an activated runtime capability.

These facts were verified through authorized read-only Project Jason/runtime operations. No Microsoft Graph application roles were changed or assumed.

## Exact proposed low-impact group pilot

The immutable *proposal*, not an approval or executable directive, is in
`config/microsoft_graph/pilots/aot-group-admin-20261112.json`.

- **Create:** ordinary assigned security group `Jason M365 Governed Pilot 2026-11-12` with mail nickname `jason-m365-pilot-20261112`.
- **Owner:** the verified active AOT user object `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`.
- **Membership:** add that same AOT user as a direct member *after* the group creation returns a readback-verified group object ID and a separately authorized exact membership action.
- **No mail-enabled group**, Microsoft Teams/SharePoint site, license change, privileged role assignment, guest invitation, or notification.
- **Cleanup:** retain until separate cleanup is approved; the current operation catalog does not permit group deletion.

## Microsoft administrator consent — granted, independently read back by setup script

AOT has created two **separate AOT-owned multitenant app registrations** through Microsoft Entra, preserving separation of read and mutation identities. Verified app metadata:

1. `Jason - M365 Group Read`: app `bb8f8e09-f851-4e0d-9c4a-95ff36d34b9a`, SP `92191ddb-36dc-40f8-9b22-a070f68ff1e3`. Granted `Group.Read.All`, `User.Read.All`; proposed profile `group-read`.
2. `Jason - M365 Group Write`: app `6583ee4b-5aa7-4c82-a46e-472f03a4c467`, SP `b15da46c-31f9-41a4-bb80-4d5eab615f81`. Granted `Group.Create`, `GroupMember.ReadWrite.All`, `User.Read.All`; proposed profile `group-write`.

Use administrator-granted consent within the exact AOT tenant. App-only Graph group permissions operate at tenant scale; these must not be granted without the Owner/admin's deliberate security decision. Do not grant `Directory.ReadWrite.All` or `RoleManagement.ReadWrite.Directory`.

The consent must be issued by an AOT account with **Privileged Role Administrator** (or Global Administrator) authority, or an approved custom role that can grant the exact Microsoft Graph **application app roles**. Microsoft states that Cloud Application Administrator alone cannot grant Microsoft Graph application roles. Use an authenticated Entra administrator session and retain auditable consent evidence; do not attempt a privileged Graph app-role grant from an unrelated service token.

Only upload public certificate halves to the app registrations. Provision matching private keys into separately restricted approved OpenBao credential boundaries, not chat, scripts, files in Git, shell arguments or logs. Reuse Jason's existing MSAL token and secret infrastructure.

After registration, obtain the two **application IDs**, approved **service-principal records**, consent/grant evidence and safe certificate thumbprint/generation metadata. Register client-boundary records for the two exact provider/profile pairs only after verifying consent. Tokens are in memory only.

**This is the first external action for which administrator consent or approval is required.** Do not silently create apps, modify a customer's directory or reuse the existing directory-read app to avoid consent.

### Certificate registration boundary — pending

On the Jason host two RSA-3072 self-signed pilot key/certificate pairs were generated with private mode 0600 inside a private mode-0700 staging directory. Only public DER certificates were copied to `C:\Users\AlDavis\Documents\Jason-M365-Public-Certs`.

- Read public SHA-1: `AB1EAD35B802F170BDFB7531637E923039B2F983`.
- Write public SHA-1: `C020401DAB7CF05BFEFE84024AA323913D903885`.
- Validity: November 12, 2026 through November 12, 2027 (pilot self-signed).
- Enrollment script: `C:\Users\AlDavis\Documents\Jason-M365-Certificate-Upload.ps1`. This requires authorized interactive administrator sign-in and exact confirmation; it has not been run.
- The private keys are *not* in production OpenBao, in Git or on the Owner's PC. Remove the restricted staging files after controlled vault transfer and verification.

## Post-consent automated acceptance

1. Inspect the exact provider/profile/client/tenant bindings, distinct app IDs, validated consent timestamps and the actual read/write token tenant/app IDs.
2. Read-only Graph preflight: `GET /groups` and `GET /users` with bounded selection using the group-read credential.
3. Verify pilot alias does not already exist, the proposed owner account remains active, and the pilot owner/client/tenant mapping is unchanged.
4. Prepare a central governed create plan; bind exact Owner approval to the current immutable source/release and the exact group fields.
5. Perform exactly one approved Graph `POST /groups` and independently verify group ID, type, alias, owner and tenant.
6. Resolve the **actual returned group object ID**, prepare a second exact membership plan, acquire the required approval, execute once, and read back direct membership.
7. Reconcile ambiguous outcomes with read-only Graph checks; never blindly repeat a POST.
8. Independently validate ticket-processing health, tenant isolation, approval evidence, production freeze restoration and rollback readiness.

## Deployment boundary

Current PR #2454 is a **draft source candidate**, not a production authorization. Verify the final immutable candidate SHA, fully reviewed change scope, CI/security evidence, compatible production baseline and verified rollback SHA, then obtain exact governed production release approval. Do not deploy or unfreeze on pilot-selection authority alone. If current production activation lacks the new group capability, an isolated, reviewed activation change remains required.

The previous dormant group-membership source branch `feature/governed-entra-group-membership-20261029` addresses more restricted finance-group use and shares `identity.group.member.add` semantics. Reconcile its security-group allowlist/independent-approval requirements with this generic operation catalog before any activation; do not merge duplicate write-provider implementations or silently weaken an established approval rule.

## Required human action

The AOT app-role consent has been granted. **Next action requiring Owner interaction:** authenticate as the AOT Entra administrator and approve enrollment of the two exact public certificates using the prepared PowerShell script. After live read-only tenant token validation, a separate exact-SHA governed production authorization is still required before release or actual group mutation.

No technician should be asked to paste credentials or hand-assemble Microsoft access tokens.

Microsoft administrator consent role requirements: https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/grant-admin-consent

## Concurrent credential-provider integration reconciliation — 2026-11-12

The central integration gate flagged additional source overlaps with PRs #2455
and #2336 in the common OpenBao provider mappings/provisioning code. Both were
inspected before release preparation:

- PR #2455 adds an independent IT Glue write secret and AppRole definition
  (`it_glue.readwrite`), with its own path and tests.
- PR #2336 adds an independent SharePoint write secret and AppRole definition
  (`microsoft_graph.sharepoint_write`), with its own path and tests.
- This PR adds only `microsoft_graph.group_read` and
  `microsoft_graph.group_write` using separate Microsoft group provider
  AppRoles. All three additions are additive; none requires deleting or
  overwriting another provider's secret mapping.
- Other overlap with PRs #2395 and #2378 is an independent security CI step
  for administrator browser approval. Retain both CI steps.
- These reviews establish compatible proposed merge intent, not permission
  to merge either other PR or alter any production secret/provider access.

All concurrent logical names, KV paths and AppRole names must remain distinct
when reviewed in the eventual protected integration/release candidate.
