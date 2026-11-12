# Microsoft 365 governed group operations — source integration milestone

**Source status:** Implemented and offline-tested in draft PR #2454. **Runtime status:** NOT deployed, NOT live-tenant consented or write-verified.

## Reused architecture — no single-use technician scripts
- microsoft_graph/governed_operations.py: immutable semantic allowlisted operation descriptors; no arbitrary Graph requests, tokens or URLs.
- microsoft_graph/group_executor.py: one shared group operation adapter implementing existing ProviderPreparedExecution and GovernedConnectorCapabilityInvoker prepare/execute contracts.
- orchestrator/service.py: central exact-action approval, plan fingerprint, idempotency, audit, approved mutation execution; no core changes.
- microsoft_graph/group_reader.py: bound read-only Graph group/member/owner/user evidence using existing UserDirectory reader.
- microsoft_graph/group_preflight.py: safe read-only scoped identity and Graph read probe before pilot.
- Kernel Client Boundary Registry and existing MSAL/OpenBao application identity: tenant-specific authentication.
- microsoft_graph/service_catalog.py: separate group-read and group-write permission profiles.

No runtime registration was added in this source-only slice. It cannot perform a production client mutation.

## Credentials and consent

Use two AOT-owned multitenant application identities **per integration profile**, not per group or action. Existing directory-reader and ticket identities remain unchanged.

| Group provider boundary | Profile | Microsoft Graph application permissions |
| --- | --- | --- |
| microsoft_graph_group_read | group-read | Group.Read.All, User.Read.All |
| microsoft_graph_group_write | group-write | Group.Create, GroupMember.ReadWrite.All, User.Read.All |

Both must map to the same exact client and tenant UUID, use different application IDs, and have validated boundary statuses, timestamps, independently authorized admin consent and centrally held certificate credentials. The standard MSAL/OpenBao components can be reused with distinct provider/profile configuration and secrets. GDAP and Partner Center enumeration do not, by themselves, grant app-only permissions.

The write permission User.Read.All is required for assigning an existing user owner with Group.Create. Avoid Directory.ReadWrite.All and RoleManagement.ReadWrite.Directory for this scope.

## Supported operations

1. identity.group.create: create assigned security or Microsoft 365 group, with a required verified active user owner. Parameters: display name, mail nickname, group type, owner UUID and optional description. Derive all actual Graph group properties and owner binding internally. Reject dynamic, role-assignable and unsupported group classes.
2. identity.group.member.add: add an existing active **user** to an eligible Microsoft 365 or security group by exact group and user UUID. Reject role-assignable, synchronized, dynamic, mail-enabled security/distribution groups and duplicate direct membership.

The catalog does not accept user-supplied tenant ID, token, application ID, Graph URL, HTTP verb, API version, PowerShell or arbitrary payload.

## Execution

1. Validate authenticated principal, authorized client/tenant bindings and ordinary technician entitlement.
2. Pre-read referenced object identity and group alias/current membership.
3. Prepare a secret-free exact-action execution plan with selected operation, client/tenant/app/boundary, route and payload.
4. The existing central executor authorizes the exact plan, checks idempotency and re-prepares; changes are denied.
5. Recheck boundary, entitlement, plan, Graph preconditions and scoped write-token immediately before one POST.
6. Read back group properties and designated owner, or direct membership, from the same tenant via separate read credential.
7. Audit only safe evidence. For uncertain outcomes, never re-POST blindly.

## Pilot readiness

The MicrosoftGroupTenantPreflight.inspect method validates boundary status, separately scoped read/write tokens and read-only GET for groups and users. It deliberately returns live_mutation_permitted=False and write_permission_grant_verified=False because token issuance and read-only Graph calls cannot prove successful write consent.

Automated tests cover central exact-action approval and idempotent replay through the real CentralOrchestrator/SQLite ledger, cross-client and cross-tenant denial, revoked consent and entitlement, invalid app token, security/M365 group creation, owner/readback, user membership, duplicate denial, dynamic/synced/role-assignable groups, invalid routes, provider failure and Graph read pagination. No real client tenant was modified.

## Next major milestone: consent-backed live test

1. Identify one separately authorized test tenant and existing user owner/member.
2. Register and consent group-read/group-write app identities and certificate credentials using the existing approved secret infrastructure; verify unique tenant mappings.
3. Run the read-only preflight and record observed permission evidence.
4. Prepare exact test group and membership actions, approvals and cleanup disposition; Teams approval is not required when authenticated Owner exact-action approval meets governance.
5. Execute an exact test through the authorized runtime and verify group owner/membership, audit, no duplicate effects and unaffected ticket processing.
6. Before production deployment, obtain current source SHA, CI/security evidence, rollback SHA and applicable PMV3 or formally amended approval.

No tenant registration, permissions, live Graph calls, production deploy or production ticket processing changes were performed by this source-only workstream.

## External references

- https://learn.microsoft.com/en-us/graph/api/group-post-groups?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/group-post-members?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/group-list-members?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/permissions-reference

Project Jason Governance Handbook (Nov 3, 2026), PMV3 production boundaries and proposed PMV4 modularity remain applicable. The PMV4 one-approval lifecycle is not an enacted production authorization without its amendment.
