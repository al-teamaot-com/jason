# ADR-015 — Scoped Entra Access Groups for Jason Capabilities

**Status:** Owner-approved; AOT pilot Entra group created and membership read back as verified on 2026-11-06; backend integration preproduction only
**Decision context:** 2026-11-06 follow-up to ADR-014
**Authority:** AOT Owner, access to J-Assist pilot for Al Davis, Lindsey Collins and Adam Navrat only
**Production:** Frozen; no enabling browser Send or QuickBooks access

## Decision

Use **dedicated Entra security groups per business capability**, rather
than hardcoding individual names/emails/object IDs or conferring a generic
"all Jason tools" administrator role. Initial group name:

- `AOT-Jason-JAssist-Users` — J-Assist reviewed screenshot intake pilot.
- **Exact Entra group object ID:** `5273dd8a-1456-4985-b0a3-c00061267e26` (Owner-admin creation script reported `RESULT=VERIFIED`, `MEMBER_COUNT=3`).

Initial membership, confirmed by the Owner-run Graph script:
Al Davis (regular Entra identity), Lindsey Collins, Adam Navrat.
Server checks the immutable **group object ID** returned
by Entra creation, not the mutable display name. Group has assigned
membership, mail disabled, no privileged Entra directory roles and
Owner-managed membership. Members' Entra object IDs must be resolved
from the AOT directory and verified as enabled before group creation.
The Entra admin session `al_admin@teamaot.com` is not itself a member.

Use `POST /users/{id}/checkMemberGroups` from a server-owned Graph
permission context to verify **live** membership in the exact group,
plus separately read the user's `accountEnabled` and server-side
validated Entra OAuth `oid`. Access-token group claims, email, display
name and browser-provided user info are not sufficient. The existing
`EntraSendAuthority` JWT signature, audience, client, tenant and scope
checks remain mandatory. The backend checks Datto device ownership,
consent, DLP and audit separately.

The group grants **screen assistance eligibility only**, not native
Datto Administrator assignment, Datto PowerShell authority, destructive
endpoint actions, QuickBooks data access, accounting exports, or any
standing production release rights. ADR-014 remains the eventual native
Datto Administrator membership policy; this is a temporary explicit
pilot identity delegation while Datto membership evidence is unresolved.

## QuickBooks and additional services

AOT can reuse the **same Entra group-based authorization pattern**, not
the J-Assist group itself, for future systems. QuickBooks must have its
own least-privilege group(s) separated by precise purpose, for example
`AOT-Jason-QuickBooks-Read` and
`AOT-Jason-QuickBooks-Write-Approvers`. Group names and permissions are
design examples only; no QuickBooks group, consent, connection or
membership has been created. Accounting data access and any financial
mutation still require provider-native QuickBooks permissions, company
scope, exact-action governance and relevant approvals. Entra group
membership is an eligibility input, never a replacement for QuickBooks
authorization.

## Lifecycle and safety

- Independent AOT Entra group object ID is **pinned**: `5273dd8a-1456-4985-b0a3-c00061267e26`.
- An actual verified Datto device from AOT's account is required.
- Check membership and enabled status on every privileged image intake
  and image read; revocation denies subsequent accesses.
- Provisioning, membership changes and service coupling remain audited
  independent operations.
- No generic grant covering all Jason apps or group role inheritance.
- Production remains disabled; no fallback to the three-person code
  allowlist once the group is configured.
- The Owner executed the group-creation script after exact authorization;
  it verified three enabled AOT identities, created one security group,
  and returned `RESULT=VERIFIED` and exact three-user membership. This is
  user-provided provider evidence, not an independent server credential test.
- Live backend membership lookup must still be connected and accepted.
- Microsoft Graph `checkMemberGroups` is **transitive**: nested groups
  would expand access. Group nesting must be prohibited for this pilot
  unless separately approved and reviewed.

## References

- https://learn.microsoft.com/en-us/graph/api/group-post-groups?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/directoryobject-checkmembergroups?view=graph-rest-1.0

## Implementation

`experiments/j-assist-bridge/entra_group_screen_authority.py` is a
preproduction-only, dependency-injected, default-deny contract pinned to the
created group object ID.

`experiments/j-assist-bridge/entra_group_membership_reader.py` performs
strict Graph-response validation of an enabled user read and
`POST /users/{oid}/checkMemberGroups` for the single approved group.
`experiments/j-assist-bridge/entra_group_http_transport.py` adapts these
operations to Jason's **existing** tenant application token provider and
its governed HTTP transport. It uses exactly the AOT tenant ID, canonical
Graph v1.0 HTTPS host, per-call credentials, bounded timeout, and rejects
all other methods, Graph URLs and group request bodies. It must
use a trusted server-owned Graph application token and AOT tenant binding;
the existing browser JAssist.Send token must never be repurposed as a Graph
bearer token. No live membership connector is registered, and screenshot
transmission is disabled pending governed device-bound intake acceptance.

Graph least-privilege app permission alternatives for this server-side
adapter include `User.Read.All` plus `GroupMember.Read.All` or `Group.Read.All`;
actual granted server identity permission must be confirmed before enabling.
No Graph application consent was added by the group creation script.
