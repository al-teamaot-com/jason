# AOT Microsoft 365 group administration — controlled release packet

**Status: pilot authorization preparation only; NOT DEPLOYED.**

**Current source-isolation notice (2026-11-12):** The separate PMv4 issuer
release preparation detected that the protected pilot AppRole runtime mounts
are not preflight-ready. A distinct source-only release candidate deliberately
sets `config/microsoft_graph/group-admin-release.json` to the exact OFF profile,
leaving this future pilot **unactivated**. The ON scope described below is a
later, separately approved M365 production project, not part of that PMv4
candidate. See `PMv4-Stage-A0-M365-Group-Pilot-Activation-Isolation-20261112.md`.

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
`/opt/jason/bootstrap/secrets/openbao/microsoft-graph-group-{read,write}-approle`
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

## Fresh operational blockers found during controlled release preparation

- Existing **group-read** and **group-write** OpenBao credential material is
  already provisioned, but the four ID files in protected bootstrap paths are
  root:root 0600. The run-as-1000 production containers cannot read them as-is.
  The source-only addition to the existing
  `tools/microsoft_group_admin_identity_bootstrap.py` prepares precisely those
  four file permissions to root:1000 0640, using authenticated local Owner
  elevation, a prior verified root-owned bootstrap receipt, an explicit
  `aot-m365-group-app-role-runtime-files-four-only` scope, descriptor-bound
  no-follow validation, partial-failure restoration and a root-protected audit
  receipt. It changes **no secret bytes, KV roles, existing mounts, group data,
  application grants or running services**. It remains **UNEXECUTED**.
- Root-protected live control readback at preparation time reported
  `circuit_breaker.state=open` and `production-drift.status=drift_detected`
  with a failed `jason-openclaw-authority-health.service` unit. Do not bypass
  this blocker, hide the failed service, or substitute ordinary container
  health for the required root health proof. The independently governed
  recovery process must return fresh closed-breaker/clean-drift evidence.
- The exact protected-main source includes unrelated PMv4 Stage A0
  `config/pmv4-stage-a0-issuer-activation.json` `mode=on`, while current
  `jason-mcp-pilot` reports `JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false`.
  Therefore a broad production main promotion is **not** only a Microsoft
  group operation. The additional activation requires its own authorization
  or a separately vetted and source-bound compartmentalized release that
  leaves the existing runtime behavior unchanged.
- Until those gates are satisfied, do not seek an unconditional release
  approval or run either Graph mutation. Source-only CI, staging images
  and pilot plans do not prove live operational readiness.

A reviewed exact action after code merge is `--prepare-runtime-access` with
the exact source SHA, authenticated local Owner privilege, and
`--approval-scope aot-m365-group-app-role-runtime-files-four-only`.
Run it **only after an appropriate exact-action authorization** and before the
nonmutating native production release preflight. Afterwards verify four
root:1000 0640 files and the new auditable receipt, with both running
container IDs unchanged.

## Source-only central authority acceptance

The exact AOT regular Owner principal is verified in the live Entra-to-Jason
binding database as
`person-entra-bee80bdcffb04c50b453c09d4d411f5f`, mapping to Microsoft
object `bee80bdc-ffb0-4c50-b453-c09d4d411f5f` and no preselected client.
The MCP action route resolves only this principal to `client-aot-internal`.

In an approved source-activated runtime, the existing JKD-001 authority
service persists only two **exact capability** grants: one for
`identity.group.create` and one for `identity.group.member.add`.
Both bind to that Owner subject, AOT organization, the fixed AOT client, exact
execute permission and `approval_required=true`. They expire at
2026-12-12 00:00 UTC and are not created while the profile is off. Neither a
group create nor a membership add is preapproved by installing a grant.
The regular authenticated Owner must provide **separate current exact-action
approval** for each operation. The existing central ledger persists the
time-limited approval and request/argument binding; an unrelated principal,
client, request ID or previous approval record is rejected.

Composition and real SQLite identity-authority tests verify these conditions
along with default-off registration. The activation is not considered ready
for live use until those checks, Graph credential preflight and actual provider
readback also succeed in a controlled production release.
