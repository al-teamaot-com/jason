# AOT Microsoft 365 Group Administration Pilot — Consent and Release Handoff

**Current status:** Source-only preparation completed. No Microsoft tenant write, new application registration, consent grant, credential change, or production deployment performed.

## Verified AOT facts (2026-11-12)

- Client in Jason's durable Microsoft boundary registry: `client-aot-internal`.
- AOT tenant: `f7054323-d52b-4863-8c2f-1898f0b6077c`, domain `teamaot.com`.
- Existing validated `microsoft_graph / directory-read` app: `c94301b7-7194-46ab-aab7-94f9366f51a9` (do not modify or broaden; it supports current Jason user reads and Teams identity enrichment).
- Validated mail-related applications also exist; these are unrelated and must not be repurposed.
- No `microsoft_graph_group_read` or `microsoft_graph_group_write` boundary is present for AOT in the currently readable production boundary registry.
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

## Exact Microsoft consent boundary (not yet crossed)

Create two **separate AOT-owned multitenant app registrations** through Microsoft Entra, preserving separation of read and mutation identities. Proposed display names:

1. `Jason - M365 Group Read`: Microsoft Graph **application** permissions `Group.Read.All` and `User.Read.All`; proposed profile `group-read`.
2. `Jason - M365 Group Write`: Microsoft Graph **application** permissions `Group.Create`, `GroupMember.ReadWrite.All`, and `User.Read.All`; proposed profile `group-write`.

Use administrator-granted consent within the exact AOT tenant. App-only Graph group permissions operate at tenant scale; these must not be granted without the Owner/admin's deliberate security decision. Do not grant `Directory.ReadWrite.All` or `RoleManagement.ReadWrite.Directory`.

Only upload public certificate halves to the app registrations. Provision matching private keys into separately restricted approved OpenBao credential boundaries, not chat, scripts, files in Git, shell arguments or logs. Reuse Jason's existing MSAL token and secret infrastructure.

After registration, obtain the two **application IDs**, approved **service-principal records**, consent/grant evidence and safe certificate thumbprint/generation metadata. Register client-boundary records for the two exact provider/profile pairs only after verifying consent. Tokens are in memory only.

**This is the first external action for which administrator consent or approval is required.** Do not silently create apps, modify a customer's directory or reuse the existing directory-read app to avoid consent.

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

An authorized AOT Microsoft Entra administrator must consent to the two narrowly specified app registrations and Graph **application** permissions, or expressly approve an authenticated, auditable administrator workflow that does the same. A separate exact-sha governed release authorization is also required before production deployment.

No technician should be asked to paste credentials or hand-assemble Microsoft access tokens.
