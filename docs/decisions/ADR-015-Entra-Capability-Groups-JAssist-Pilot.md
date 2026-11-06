# ADR-015 — Scoped Entra Access Groups for Jason Capabilities

**Status:** Owner-proposed architecture accepted for J-Assist preproduction; tenant group creation pending
**Decision context:** 2026-11-06 follow-up to ADR-014
**Authority:** AOT Owner, access to J-Assist pilot for Al Davis, Lindsey Collins and Adam Navrat only
**Production:** Frozen; no enabling browser Send or QuickBooks access

## Decision

Use **dedicated Entra security groups per business capability**, rather
than hardcoding individual names/emails/object IDs or conferring a generic
"all Jason tools" administrator role. Initial group name:

- `AOT-Jason-JAssist-Users` — J-Assist reviewed screenshot intake pilot.

Initial membership: Al Davis (regular Entra identity), Lindsey Collins,
Adam Navrat. Server checks the immutable **group object ID** returned
after Entra creation, not this mutable display name. Group has assigned
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

- Independent AOT Entra group object ID is pinned after group creation.
- An actual verified Datto device from AOT's account is required.
- Check membership and enabled status on every privileged image intake
  and image read; revocation denies subsequent accesses.
- Provisioning, membership changes and service coupling remain audited
  independent operations.
- No generic grant covering all Jason apps or group role inheritance.
- Production remains disabled; no fallback to the three-person code
  allowlist once the group is configured.
- The group creation script performs a read-only preflight, requests
  explicit confirmation, creates only this one J-Assist group and its
  three verified users, and reads back exact membership.

## References

- https://learn.microsoft.com/en-us/graph/api/group-post-groups?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/directoryobject-checkmembergroups?view=graph-rest-1.0

## Implementation

`experiments/j-assist-bridge/entra_group_screen_authority.py` is a
preproduction-only, dependency-injected, default-deny contract for live
server-side membership checks. It has no provider connector or live
production configuration until creation returns the exact group object ID.
