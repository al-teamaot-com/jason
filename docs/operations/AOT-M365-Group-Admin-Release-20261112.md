# AOT Microsoft 365 group administration — controlled release packet

**Status: final-source CI / release approval preparation. NOT DEPLOYED.**

## Governance and scope

- Approved AOT tenant: f7054323-d52b-4863-8c2f-1898f0b6077c.
- Governed client: client-aot-internal.
- Exact requester: authenticated AOT Entra owner object bee80bdc-ffb0-4c50-b453-c09d4d411f5f, Jason person-entra-bee80bdcffb04c50b453c09d4d411f5f.
- New operations only: identity.group.create and identity.group.member.add.
- Approved fixed test group: Jason M365 Governed Pilot 2026-11-12; nickname jason-m365-pilot-20261112; ordinary assigned **security** group.
- Owner and prospective direct member: AOT user bee80bdc-ffb0-4c50-b453-c09d4d411f5f.
- Distinct Entra Graph app-only identities, certificates and admin consent already verified. Production OpenBao AppRoles, KV records and exact client-boundary records were provisioned and read-verified under a **prior configuration-only approval**.
- Deployment itself is **NOT** covered by that earlier authorization. Do not silently unfreeze or restart production.

## Source activation and service isolation

The single shared adapter and catalog is opt-in only. Production release source file
`config/microsoft_graph/group-admin-release.json` declares exactly one AOT pilot
profile. Runtime and MCP deployment scripts independently read the same file
and reject unreviewed host overrides; the rollback image always disables it.
Kernel lifecycle stays BUILDING and provider PLANNED without that profile;
exact profile moves only the two capabilities to ACTIVE.

The existing Central Orchestrator, JKD001 authorities, exact-action ledger,
idempotency, evidence and approval mechanisms remain authoritative.
MCP uses the existing `execute_governed_capability` route, but neither
capability is available unless activated and authorized. The MCP derives the
client exclusively from a verified AOT Owner binding, not a caller-supplied
client or tenant selector. Each mutation needs a separately authenticated
exact-action approval, including remediation justification/evidence and
post-action readback. A general request to deploy cannot authorize either
Graph POST.

No ticket worker, Autotask provider, existing Microsoft read app, release
approval authority or Teams approval fallback is modified.

## Credential isolation

Read: microsoft_graph_group_read / group-read; AppID
bb8f8e09-f851-4e0d-9c4a-95ff36d34b9a.

Write: microsoft_graph_group_write / group-write; AppID
6583ee4b-5aa7-4c82-a46e-472f03a4c467.

Source-controlled deployment adds exactly four read-only binds from
`/var/lib/jason/runtime-secrets/openbao/microsoft-graph-group-{read,write}-approle`
into
`/run/jason-secrets/openbao/microsoft-group-{read,write}` for the role and
secret ID. Those host projections must be established using already-approved
OpenBao AppRoles, have root:1000 ownership, file mode 0640, and contain no
symbolic links. They are **not** part of the current live containers; absence
must fail preflight rather than silently reuse another app identity.

The reviewed rollback flag is limited to exactly the four group AppRole bind
destinations on the old runtime or MCP `:rollback-current` image, with
`JASON_M365_GROUP_ADMIN_PROFILE=` disabled; it does not remove unrelated
existing secrets.

## Required immutable release evidence

1. A final candidate SHA after merging/rebasing and a SHA256 of the reviewed
   source diff from `origin/main`. Record them in PR #2454 and the exact
   release manager entry; never approve a moving branch name.
2. Verify current running `jason-runtime` and `jason-mcp-pilot` image
   source revisions and identities, their retained matching image tags and
   source tree. Last observed source / proposed rollback SHA:
   `d1b8c196dadd4b672ec8ba47075f27bb61c98d63`.
3. Review the complete **production baseline to candidate** delta, including
   unrelated commits on main; do not assume the feature-branch diff is the
   entire operational change scope.
4. Verify GitHub CI and security checks at the exact candidate SHA,
   including default-off/active tests, cross-tenant denials, planner/ledger,
   updated rollback mount omission, native runtime and MCP regression tests.
5. Build and test candidate runtime and MCP images under separate, immutable
   staging tags. Do not replace live containers in preproduction.
6. Verify credentials/certificates, live group alias absence, account-active
   status, OpenBao bounded app identities and exact boundary records.
7. Use the existing Release Manager production transaction (prepare,
   preprod, review-impact, unfreeze-release, promote) with exact SHA,
   rollback and immutable Owner authorization. Preserve the production
   freeze and hold except inside that one approved transaction.

## After a separately approved production release

- Check both live services healthy and on the exact candidate SHA.
- Verify both group actions discoverable **only** for the verified AOT Owner
  principal and not for other principals/tenants.
- Recheck ticket processing and core service regression canaries.
- Obtain a separate, auditable exact-action approval for the **fixed** group
  creation (name, alias, group type, owner and description), including
  affirmative remediation review and provider evidence.
- Create the group **once** through the governed tool; verify actual group ID,
  alias/type, owner and audit before considering the first action complete.
- Obtain a second, distinct exact-action approval for membership of the
  **same** verified AOT account in the exact returned group ID; execute once,
  read back membership, reconcile unknown provider results with GET not retry.
- Retain the pilot group until separately approved cleanup. Do not create
  Teams workspaces or SharePoint sites, assign licenses, manage roles, or
  modify other groups as part of this pilot.

## Failure handling and rollback

If candidate preflight fails, do not unfreeze or deploy. If deployment fails,
use the existing Release Manager controlled rollback to the exact retained
`d1b8c196dadd4b672ec8ba47075f27bb61c98d63` source and images, remove
only the four new group credential binds and turn the group profile off.
Check post-rollback ticket health, MCP authority and no newly exposed group
capabilities. Restore the original freeze bytes, engineering Owner pause and
automatic promotion hold; retain auditable failure/recovery evidence.

An HTTP success without group/owner or membership readback is **not**
operational completion. A successfully deployed runtime without the live
approval-bound pilot verification is **not** end-to-end completion.

## Owner approval template (to be filled from final CI-verified candidate)

I authorize exactly one Project Jason controlled production unfreeze and
release of the Microsoft 365 AOT group administration candidate SHA
<CANDIDATE_SHA>, reviewed complete production-to-candidate scope
SHA256 <FULL_REVIEW_SCOPE_SHA256>, and rollback source/image SHA
d1b8c196dadd4b672ec8ba47075f27bb61c98d63, for AOT tenant
f7054323-d52b-4863-8c2f-1898f0b6077c and the two approved group
capabilities only. Preserve existing ticket processing, restore the original
production freeze and holds, verify runtime and MCP health, and automatically
roll back on failed release validation. This is **not** authorization to create
or modify a Microsoft 365 group; each pilot Graph change requires a separate
exact-action Owner approval and readback. No standing release authority is
granted.

Do not replace the placeholders or request this approval until source
review, CI, rollback availability and native preproduction checks pass.
