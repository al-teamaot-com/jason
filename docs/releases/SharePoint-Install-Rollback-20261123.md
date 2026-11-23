# Jason SharePoint installation and rollback package

This package binds the merged reader, site controls, credential projections,
Grafana controls, protected policy additions and daily discovery to one exact
source SHA. It prepares review material and tests configuration/rollback; it
does **not** confer production authority or install a privileged release lane.

## Approved target requested by the Owner

On November 23 the Owner requested that the bank-statement site be approved:
`https://absolnet.sharepoint.com/sites/AOTAccountingDocuments`.
Its previously recorded Graph ID is
`absolnet.sharepoint.com,8f4cd7bf-72b8-4f7e-9803-c47abcbb232f,e5b7a724-dc9b-406b-aed8-2961f1f71153`.
Revalidate that URL/ID with Jason's dedicated application before changing policy.
Only this site is requested enabled at installation. Every other new site stays
disabled. This approval does not change document sensitivity/release rules,
Microsoft permissions, document contents or the financial organizer.

The conversation request is retained as exact **intent**, not fabricated
authenticated approval evidence. At preparation, the MCP Owner-authority check
returned `AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED`. Production site enablement must
wait for independently verified Owner authority and an audited exact-site
decision through the existing governed administration service. Never use the
Owner's delegated SharePoint connection or create a raw SQLite grant instead.

## Contents and verification

`tools/sharepoint_install_package.py` has only `prepare` and `verify` commands.
It packages exact Git blobs and a deterministic plan/manifest, rejects a dirty
source or an existing/protected output path, and verifies every source blob
against the exact Git commit. Changed payload, added files, expanded site scope
or a rehashed unauthorized plan fail verification. No live container environment,
token, certificate private key, bank statement or credentials are included.

The package includes all Microsoft Graph connector source, the runtime reader,
site-control image/Compose/systemd/dashboard files, existing provisioning tools,
the pure native container and policy delta planners, rollback requirements and
tests. The native runtime must still be built from the exact complete reviewed
Git revision by the existing Release Manager; this source closure is not a
replacement production runtime image.

## Single installation scope

1. Before mutation, the native root release path seals current private
   before-images and independently validates source, CI, rollback, Owner,
   freeze/hold, fresh health, shared locks and effective root policy.
2. Add only `jason-sharepoint-site-control`,
   `jason-sharepoint-discovery.service` and `jason-sharepoint-discovery.timer`
   to the effective root allowlists. Source policy is not proof of root policy.
3. Use the existing exact-SHA boundary bootstrap to verify the dedicated
   certificate, application-only token and complete Graph discovery, then record
   and read back one `client-aot-internal` / `microsoft_graph_sharepoint` /
   `sharepoint-read` binding. Keep existing unrelated boundary rows intact.
4. Provision shared `jason-sharepoint-site-state`, a private service token and
   read-only dedicated AppRole mounts. Verify UID 1000 access without widening
   host ACLs, printing values or using a second authentication integration.
5. Deploy the pinned isolated site-control image; complete discovery; every
   discovered site starts disabled. Verify Accounting's exact URL/ID, independently
   validate the Owner decision, enable only that site through the governed
   administration service, and retain revision/audit/readback.
6. Through the native runtime release, add exactly the SharePoint profile,
   tenant, dedicated credential mount and shared site registry specified in
   `plan.json`. The pure container planner preserves unrelated environment,
   mounts, commands, health checks, restart/network settings and ports.
7. Preserve the existing Grafana image and settings; enable only
   `GF_DATAPROXY_SEND_USER_HEADER=true` through controlled replacement.
   Create only datasource `jason-sharepoint-control` and dashboard
   `jason-sharepoint-site-access`. Existing conflicting UIDs deny admission.
   Never overwrite an existing secure datasource token that cannot be recovered.
8. Prove live MCP reads, Owner Grafana round trip, immediate revoke, forbidden
   site/tenant denials, unchanged Ticket Core and protected peers, logging and
   native drift. Install the exact daily **04:30 America/New_York** units and
   enable the timer last. A manual discovery run is not proof of a scheduled run.

## Native release boundary

The existing root objective pilot registers only documentation actions and the
independent component controller protects shared Runtime/MCP. Neither permits
the package to apply arbitrary privileged changes. The runtime deploy helper
also preserves existing mounts by default; the SharePoint Compose overlay alone
does not make the native release add those mounts.

Therefore `production_ready` remains false until the existing native root
release path has admitted the exact typed projection and auxiliary installation
scope, pinned immutable images, source/CI, effective root policy before-image,
complete rollback and independently verified Owner decision. This review
package must not be invoked as a new root installer, as an unapproved alternate
release lane, or as an excuse to restart healthy protected services. Do not ask
for production approval against a fabricated Release Manager ID. Native release
admission/trust changes remain a separately governed release if required.

## Rollback and interrupted execution

Disable the new timer first, roll back Runtime through the native exact private
before-image, remove only newly created Grafana UIDs, restore Grafana's previous
configuration/image, then remove only the new sidecar/owned unit files.
Restore root policy only if it still matches this transaction's after-image;
otherwise stop for bounded reconciliation rather than overwrite a newer policy.

Never restore the complete live boundary/site databases from old backup files.
Retain newer site switches, authorizations, discovery/audit records and receipts.
Revoke only an unchanged binding created by this transaction, after checking no
later consumer exists, through Jason's boundary service. Existing credentials
and private material remain in place. Recovery must read receipts and native
state before retrying; an unknown outcome never permits a duplicate mutation.

Recheck protected peers, freeze/hold, observability and fresh root drift. A
rollback conflict remains an explicit blocker, not permission to reset state.

## Reproduction

From a clean exact review commit, with a nonsecret baseline observation JSON:

```bash
clear
cd /path/to/verified/jason-worktree
python3 tools/sharepoint_install_package.py prepare \
  --repo "$PWD" --source-sha <exact-40-character-reviewed-sha> \
  --baseline /path/to/private/baseline-observation.json \
  --package /path/to/new/SharePoint-Install-Rollback.zip
python3 tools/sharepoint_install_package.py verify \
  --repo "$PWD" --source-sha <same-exact-sha> \
  --package /path/to/new/SharePoint-Install-Rollback.zip
```

Baseline fields are exactly `runtime_source`, `runtime_image`, `mcp_image` and
`observed_at`. They record an observation and never substitute for fresh native
root acceptance or the private before-images used for actual rollback.
