# SharePoint site access — isolated engineering release evidence

**State:** source candidate for independent review; **NOT production eligible**, not approved and not deployed. This document must be updated with the final exact reviewed SHA, independent review digest, production rollback and live acceptance prior to any release-manager promotion.

## Objective
One reusable Jason workload identity for every AOT-owned SharePoint site; site-level access toggles through Grafana, immediately effective without development or restart; daily Graph app-only discovery adds new sites disabled; exact AOT SharePoint hostname allowlist required; AOT Accounting's Bank Checking Accounts Register is a consumer of this same integration and has no separate credential or access component.

## Source and isolation
- Parent reader development: PR #1330, `feature/reusable-sharepoint-reader-20261012`.
- Site-control dependent PR: #2616, `feature/sharepoint-site-access-config-20261119`.
- Isolated engineering worktree: `integration/sharepoint-site-controls-20261119`.
- Running production runtime/MCP images must not be modified or restarted merely to install site control. Sidecar source defines its own image, volume, and two existing Docker networks; no ports published.
- Grafana dashboard UID `jason-sharepoint-site-access`, separate datasource `jason-sharepoint-control`, packaged independently, without changing the global observability dashboard manifest. Dashboard is not live until provisioning is authorized.
- Only an isolated conditional hook was added to the runtime composition; the protected ticket-processing core, Autotask catalog write path and JSON playbook migration implementation files remain unchanged. The runtime hook performs no provider/capability registration with the activation profile unset. Full production non-regression proof is still required.

## Verification completed in engineering
- Unactivated reusable reader now performs a mandatory site policy check internally when a trusted site access registry is injected; existing exact-file workload remains unchanged. New AOT site-scoped workload profile may enumerate only when backed by a validated service binding and enabled site. Site browsing does not grant unreviewed financial document content release.
- Unit tests: site discovery pagination, unknown/cross-tenant denial, new-sites-disabled, retained switches, atomic scan failure, manual site toggles with optimistic revisions, authenticated Grafana datasource proxy denial and authorized readback.
- Focused Jason runtime SharePoint composition tests.
- Representative smoke: JSON playbook store/document tests, Autotask ticket create/update, release-manager gate.
- `docker compose config --quiet` on isolated sidecar: passed with inert placeholder environment.
- Grafana target-only installer now supports read-only preflight and reviewed exact-SHA application, verified datasource/dashboard UID and existing Jason folder. No running Grafana service is restarted by its API workflow.
- Current host recheck (2026-11-19): the validated SharePoint boundary is still absent, the Grafana authenticated-user proxy header is disabled, and governed SharePoint runtime read capabilities are inactive. Root-only OpenBao `status` and `verify` checks pass for the dedicated reader AppRole; artifacts are complete, the secret is present, runtime access is active, no token is persisted, and no secret values were printed. The Owner-approved ACL is `750 root:al` on the AppRole directory and `640 root:al` on both files; read-only access was verified as UID 1000. The certificate/private-key match, app-only token claims, and Graph enumeration remain pending the read-only bootstrap preflight. No boundary row has been written.
- No production image build or deployment was initiated. No OpenBao credential values were printed or modified.

## Mandatory missing evidence / hard gates
1. A real app-only token proving that the OpenBao private key matches Jason’s verified Entra certificate, with the tenant, service-principal and `Sites.Read.All` claims validated.
2. Validated dedicated Microsoft Graph SharePoint client boundary and app-only read of AOT Accounting and a second AOT site.
3. Governed runtime read catalog, manifest, and Owner-bound invoker are now staged behind an OFF-by-default exact activation profile. Still required: production activation and real MCP read registration/readback, dedicated app credential mounts, persistent site-policy store shared into the runtime, and independent preproduction verification. No provider bypass.
4. Actual sidecar image build at exact immutable base digest, package SBOM/security scan, isolated network and secret mount review, unprivileged read/write access verification.
5. Grafana authenticated datasource and dashboard live-readback; Owner enable/disable without restart; no unauthorized operator access. Existing Grafana lacks the authenticated-user proxy header setting; enabling it is a **separately approved, controlled Grafana configuration change/restart** with observability rollback and canary, not a side effect of this source change.
6. A full AOT tenant daily discovery scan with accurate pagination; new site disabled; error handling verified.
7. Negative permissions, content sensitivity and cross-tenant isolation tests; bank-statement location uses same authorized connector.
8. Production regression and baseline after installation: PMv4 protected ticket processing, services/bundles, and JSON playbook migration unaffected.
9. PMV3 exact candidate SHA, manifest/scope SHA256, rollback SHA, frozen-state check, signed Owner approval and Release Manager acceptance.

**Release mechanism constraint:** The current protected-main Release Manager deploys an exact full main SHA, including unrelated already-merged changes. This branch is not a production-eligible release candidate until protected-main integration, complete scope inventory/overlap review, isolated preproduction and exact-SHA Owner freeze exception. Avoid deploying from feature worktree or using a sidecar as an unauthorized alternate production lane.

**No production authorization is implied by the owner's instruction to finish engineering.** If any gate cannot be proven, remain in source-review state rather than claim operational readiness.

## Concurrent PR #2455 overlap review (2026-11-19)

Reviewed the exact changed-file patches in independent IT Glue write PR #2455:
- `implementation/connectors/core/openbao_secrets.py`: additive `it_glue.readwrite` secret contract.
- `tools/provider_secret_provision.py`: additive `it_glue_write` AppRole provider profile.
- `implementation/runtime_service/src/jason_runtime/composition.py`: separate disabled-by-default IT Glue write registration and invoker.

Our integration's changes in those same three files add the dedicated `microsoft_graph.sharepoint_read` secret contract/provider and dormant AOT SharePoint reader registration, while preserving previously merged SharePoint writer, Microsoft group and Constant Contact code. **No IT Glue write changes are merged, authorized or activated by this integration.** The overlapping IT Glue PR must be independently re-reviewed for concurrent source changes at its merge/release time; this records coordination, not a waiver.

Integration coordination: #2455

## Updated isolated preproduction evidence and prerequisites (2026-11-19)

- Built standalone source image from the **unchanged running runtime image**
  `sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132`
  using a locally tagged reference that resolved to that exact immutable ID. Preprod image
  ID: `sha256:d6fd9d5d0ab14bdadc4c57b0cddb4a0b4c3bd38f1e1376b7794cb5b58830fbaa`.
  This is local build evidence, **not a release-signable production artifact**.
- Offline image imports and AOT SharePoint site-state test PASS. Separate ephemeral
  containers shared the same synthetic policy SQLite file and demonstrated
  discovered=disabled, explicitly enabled and immediate runtime readback.
- Canonical root-protected AppRole provisioner requires `microsoft_graph_sharepoint`
  and its `role-id` / `secret-id` files in
  `/opt/jason/bootstrap/secrets/openbao/microsoft-graph-sharepoint-read-approle`.
  A root-only host readback on 2026-11-19 verified the AppRole artifacts, and a separate credential ACL check confirmed read-only access for runtime UID 1000. The production client-boundary database has no validated SharePoint profile row. Authenticated Entra admin-center readback verified application `Sites.Read.All` consent for Jason’s dedicated SharePoint reader app. The app overview showed one active certificate and zero client secrets; its thumbprint and expiry were verified. The certificate/private-key match, app-only token, and Graph enumeration remain pending.
- Microsoft Graph `sites/getAllSites` requires **application** `Sites.Read.All`,
  with tenant admin consent. The documented nextLink can use
  `/v1.0/sites/oneDrive.getAllSites?$skiptoken=...`; the bounded pagination validator
  now accepts both documented Graph paths and rejects foreign hosts.
- Grafana has the Infinity datasource and Volkov Labs Forms panel installed, but
  current `GF_DATAPROXY_SEND_USER_HEADER` is not configured. Enabling the setting
  requires separate exact-change approval and may restart Grafana. Do not substitute
  delegated Owner SharePoint connector for Jason's app-only workload identity.
- Shared persistent state is explicitly named `jason-sharepoint-site-state` and the
  standalone runtime overlay is **off by default**. Controlled release activation
  must mount this volume and dedicated AppRole into the governed runtime; no
  deployment or restarts are effected by adding the overlay source.
- Tenant-wide application `Sites.Read.All` consent has been verified in Entra. OpenBao lifecycle status/contract verification and the approved UID 1000 read-only credential access have passed. The app-only Graph token and enumeration, Accounting bank-statement readback, live Grafana Owner session, and daily timer verification remain outstanding.

### Exact remaining authorized sequence

1. **Verified:** authenticated Entra readback confirms the dedicated Jason app, active certificate thumbprint/expiry and tenant-wide application `Sites.Read.All` grant. Do not request duplicate consent; do not use delegated Owner access.
2. **Verified:** root-only OpenBao `status` and `verify` pass; dedicated AppRole artifacts exist, the secret is present, runtime access is active, and UID 1000 has read-only file access. No credential values were printed.
3. **Pending:** run the exact-SHA read-only bootstrap to prove certificate/key match, app-only token claims and full AOT site enumeration. Only after that succeeds, obtain exact Owner approval for the boundary-only write, persist one validated AOT boundary through the canonical Kernel repository, and verify the readback.
4. In isolated preprod, enable only two approved test sites, exercise search,
   metadata, forbidden cross-tenant/content reads, refresh and revoke, and confirm
   all newly discovered other sites remain disabled. Use the same reader for the
   Accounting bank-statement location, with separate document release classification.
5. Provision persistent shared site registry, Owner-authenticated Grafana site
   controls and the daily timer with exact file scopes. Run full Grafana
   authentication/authorization and controlled change-readback tests.
6. Independent PR review, merge reviewed source to protected main only when approved,
   run native Release Manager `prepare`, `preprod`, `review-impact --record`, exact
   signed scope + rollback verification, obtain authenticated Owner exact-release
   approval and one-transaction freeze exception; only then promote and verify
   PMv4, service catalog, JSON playbook, Grafana and scheduled discovery canaries.

**Do not request `approve_release_candidate` with a source-branch SHA**: the
native tool only authorizes an actual production-eligible Release Manager ID
whose candidate SHA and scope already passed independent review.
