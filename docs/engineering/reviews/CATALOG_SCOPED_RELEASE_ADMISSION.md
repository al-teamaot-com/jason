# Autotask catalog dual-image scoped release admission

**Lifecycle:** source-only protected Production Manager extension, 2026-11-17.
**Explicit Owner instruction:** prepare a narrow catalog runtime/MCP release-admission
mechanism; DO NOT expand the global Owner allowlist; DO NOT deploy without a
separate exact release approval. There is no independent human security-reviewer
role in this project. Protected CI, exact-source evidence and normal governed
Owner approvals remain required.

## Scope and why this is not a broad main release

PR #2515 merged the runtime Autotask API-service identity correction.
PR #2522 merged narrowly scoped exact catalog grant administration as source
only, feature SHA `b0e3b84415a83cb603c53c7efbf4867eab829665`, merged in
`235fbe23a821d29a0925b9ab033632b952034c8e`. Neither feature is active in
production. Ordinary native Release Manager `create`/`prepare` builds entire
source `main`, which would bundle unrelated PMV4, Ticket Core, SharePoint and
control-plane modifications. The earlier isolated snapshot fails ordinary
all-repository CI because it starts at older live production source; merely
merging it as a second ancestor cannot safely remove the updated protected
scope controls. A native version-blind release is prohibited.

The exact catalog-only snapshot source is
`d73f680864bd75cd714a89f36ae8a3190dc60e66`, based on live source
`d1b8c196dadd4b672ec8ba47075f27bb61c98d63`. Its binary diff SHA256
is `574361739ef89969a22932a9cb8731432b9b715a5a0a78fbdbd66d79a2494256`.
Exactly nine reviewed files differ, including the runtime Autotask connector,
MCP bounded catalog administration, regression tests, documented evidence and
security workflow. All other source is identical to running production.
The isolated snapshot remains on the exact published Git branch and was never
merged directly into protected main (archived draft #2524).

## New native Production Manager command

`python3 tools/release_manager_host_runner.py --repo <repo> catalog-scope-admit`

This is **read-only source admission evidence**, not `create`, `prepare`,
`approve` or `promote`. It never makes the production state-root, writes
release records, issues human approval, touches provider credentials, runs
Autotask mutations, remaps the Owner, unfreezes, restarts services, deploys
Docker containers, or relaxes the existing native Release Manager. Its only
external commands are Git evidence, the existing GitHub required CI checks,
Docker inspection, and both native **`--preflight`** invocations. Its output
always includes `native_production_eligible_record_created=false`,
`owner_approval_recorded=false`, `production_mutations=false`, and
`provider_writes=false`. The receipt SHA256 binds the exact evidence.

The canonical immutable manifest is checked in to protected source as
`config/catalog-scoped-release-admission.json`; the command obtains it from
`git show <verified origin/main SHA>:<manifest path>`, never mutable worktree
bytes. JSON schema/keys, exact nine-file allowlist, git source commits,
rollback SHA and snapshot branch are pinned. Unknown fields, altered settings, changed code outside the allowlisted
catalog files, stale origin/main or absent protected GitHub checks fail
closed. The manifest is versioned in protected Git and the pinned snapshot
branch must follow the catalog-only release namespace. Future reviewed
catalog-only release versions can change the pinned SHA, immutable image
IDs and rollback through a protected manifest update, without rebuilding the
release-admission code; added executable files require a deliberate code and
security test review. Required CI is the existing nine native checks
**plus** the `governed-security-regressions` SEC-007 job.

## Shared MCP server source without cross-PMV4 deployment

The existing MCP `server.py` is shared with Ticket Core, PMV4 and other
capabilities; the protected-main file *as a whole* differs from the old
production-derived snapshot and cannot be copied wholesale as a release.
Instead the admission verifier checks **byte-for-byte equality of exactly
five catalog-administration function bodies** among the frozen snapshot,
the already merged feature commit, and current protected main. Dedicated
catalog module, tests, exact-plan test and runtime connector are likewise
blob-equal to protected main. Newer unrelated server functions remain in
protected main for development, not in the two isolated production images.
The verifier also compares all other top-level Python AST nodes between
running-production baseline and snapshot; it rejects adding unrelated imports,
endpoint functions, globals or Ticket Core behavior even if a manifest is
repinned. Any unreviewed change to a catalog function or extra executable
snapshot path blocks admission.
This gate does NOT claim approval of a PMV4 single-component release, since
`server.py` is expressly a shared source path.

## Immutable dual-image and rollback evidence

- Runtime candidate image: `sha256:98f5d3f4a16e55b9a49fa424056dc30a8139dc443f4948d2aaf524ac4fa9dddf`
- MCP candidate image: `sha256:ea8a3fca67b9f75dbd2ec4156cb8d1a657c13efd72886b4d16e54046070de9b9`
- Rollback runtime image: `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`
- Rollback MCP image: `sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477`
- Existing exact production freeze SHA256: `bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f`

Admission inspects both live containers, running host source pointer,
original image digests, live runtime health, rollback image availability,
immutable candidate image IDs/source labels, unchanged freeze bytes, original
Owner allowlist, and unactivated catalog settings. It runs each current
pinned `deploy_live_container.py --preflight` with one exact setting and zero
extra mounts, verifying source/candidate images and outcome. It repeats main
and live readback after preflights to deny concurrent drift. It never reads or
returns raw provider secrets as evidence.

The two *future, exact-action, separately approved* release settings are:

- `JASON_AUTOTASK_CATALOG_AUTH_MODE=jason_managed` on the runtime
- `JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE=aot-catalog-self-owner-v1` on MCP

Neither is authorized to be applied by this source-only change. Do not add the
regular Entra Owner to `JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES`.
The precise four catalog actions require per-operation approval, and the
human requester remains separately auditable from Jason's Autotask API-only
execution identity.

## Gates remaining after source admission

This read-only admission command **does not** make the normal Production
Manager's full-main `create` path accept a scoped image or alter its deployed
single-SHA alignment/host reconciler contract. That would be a separate
production-control mutation, not permitted by this preparation. Before
promoting either image, the exact scope receipt must be consumed by an
Owner-approved, scope-aware native Production Manager transaction preserving
candidate/rollback source and image identities, host/PMV4 non-interference,
root-owned installer custody, atomic lock, freeze, health, rollback and
post-deployment readback. If that complete transaction is not installed and
verified, **promotion must remain blocked**, even with a passing admission
report. An ordinary broad-main production release must not be substituted.

After an eligible transaction is independently verified, require **one
fresh authenticated Owner approval** for its exact manifest, image IDs,
source and rollback; approval of this engineering PR is not such approval.
A separate exact-action approval is required for a named inactive/no-billing
Autotask test service, with provider write/readback and zero impersonation.

## Engineering acceptance

- Pure-Git source and strict manifest checks, five shared-function comparisons,
  CI cross-checks and modified-file allowlisting.
- Negative tests for forged remote origin, SHA drift, unexpected paths,
  changed code, deleted CI, expired/failed checks, invalid Owner settings,
  runtime/MCP image replacement, missing rollback, frozen marker drift,
  unhealthy containers, duplicate sensitive environment keys, bad native
  preflight output, and read-only CLI state-root guarantees.
- Existing Production Manager `create`, `prepare`, `approve`, `promote`,
  `rollback-release` and production worker controls are unchanged by default.
- Do NOT report 100% of the *production rollout* until exact production
  deployment and an actual Autotask API write/readback are verified.
