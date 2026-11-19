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
- 2026-11-19 read-only host preflight: SharePoint AppRole RoleID/SecretID missing, validated production microsoft_graph_sharepoint client boundary missing, Grafana authenticated-user proxy header disabled, governed SharePoint runtime read capabilities inactive. No provider changes made.
- No image build or deployment initiated on the production host. No OpenBao secret read/write performed.

## Mandatory missing evidence / hard gates
1. Dedicated Entra app certificate and OpenBao credential/profile under *Jason's own identity*, validated current, not merely previously documented.
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
