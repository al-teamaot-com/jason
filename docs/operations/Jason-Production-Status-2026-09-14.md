# Jason Production Status — 2026-09-14

## Purpose

This record captures the current production state after the governed provider-read v4 cutover, host/OpenBao recovery, production-health monitoring deployment, accepted-level rollback checkpoint, and the governed Datto site-pagination correction completed on 2026-09-14. It is a factual operating record, not a replacement for architecture, recovery, or security-control documentation.

## Current production state

Jason is operating in governed read-only mode. The live MCP is `jason-mcp-pilot` on image `jason-mcp:datto-pagination-6da45b3ef66d`, image ID `sha256:320015a9196bacab883149da8257a40f1061ab002c50b14c694975e979989b49`, sourced from Git commit `6da45b3ef66d08762cbeed66c5c540c873b20889`. The active provider-read profile remains `itglue-autotask-entra-governed-catalog-v4`.

The live interface reports:

- mode: read-only;
- governed execution: Central Orchestrator;
- direct provider access: disabled;
- write tools: disabled.

The separate `jason-runtime` container is running and healthy. Its container identity remained unchanged during the Datto pagination deployment. OpenBao is initialized and unsealed, and its container identity also remained unchanged during that deployment.

The current MCP launch contract includes 15 bind mounts. Twelve credential-related mounts are read-only and are mounted inside the MCP under `/run/jason-secrets/openbao/...`. The deployment validation verified that all live bind sources were Docker-accessible and that the read-only credential source files matched the credential bytes already mounted in the running MCP without printing credential contents or host source paths.

## Governed provider-read milestone

Live Jason has production governed read access to all four target operational data sources:

| Provider | Current governed surface | Production validation |
| --- | --- | --- |
| Datto RMM | managed endpoint/site/alert reads already present in the governed catalog | live governed site search now completes the full provider-reported 45-site collection |
| IT Glue | 10 documentation search/read capabilities | live governed organization search completed after v4 cutover; broad unscoped disclosure correctly failed closed at the information-release boundary |
| Autotask | 11 service-management search/read/count capabilities | live governed ticket count completed after v4 cutover |
| Microsoft Entra / Graph | exact user search and exact user read | live governed user search and read completed after v4 cutover |

The v4 authority cutover added 23 observe-only provider grants: 10 IT Glue, 11 Autotask, and 2 Microsoft Entra. Existing Datto RMM observe grants were preserved. The Datto pagination correction introduced no new authority grants and no provider write grant.

## Datto site-pagination correction

A real-world governed `management.site.search` exposed a correctness defect: Datto returned a successful first provider page containing 10 sites while `pageDetails.totalCount` reported 45. Ordinary unfiltered site enumeration could treat that first successful page as sufficient evidence instead of completing the provider collection.

Source commit `6da45b3ef66d08762cbeed66c5c540c873b20889` corrects this by making `datto_rmm.site.search` request complete bounded collection handling by default. The existing provider-neutral pagination adapter remains bounded to a maximum of 20 pages and 1000 items and fails closed on incomplete or unsafe continuation behavior.

Focused regression coverage models five provider pages totaling 45 sites (`10 + 10 + 10 + 10 + 5`) and verifies a final complete collection of 45. Focused provider-adaptation and Datto connector tests passed before production deployment.

After production cutover, a live governed MCP `management.site.search` succeeded against Datto RMM with:

- `pageDetails.count = 45`;
- `pageDetails.totalCount = 45`;
- `discovery_complete = true`.

This is the production proof that Jason no longer stops at the first 10-site provider page for ordinary governed site enumeration.

Detailed deployment evidence is recorded in `docs/operations/Jason-Datto-Site-Pagination-Production-Deployment-2026-09-14.md`.

## Autotask ticket-status correction

The Autotask status-label defect discovered during acceptance was fixed before production cutover. Autotask's `Tickets/entityInformation` endpoint returns entity-level metadata only; field/picklist data must be read from `Tickets/entityInformation/fields`. The connector resolves labels such as `New` through that field metadata and then uses the numeric picklist value for the bounded count/search operation.

Focused Autotask + Microsoft Entra regression tests passed before cutover. A live patched connector proof successfully resolved `Status = New` and executed the Autotask `/query/count` path before production activation.

## Information-release behavior

Provider authentication is not treated as disclosure authority. Provider reads continue through identity/authority evaluation, Central Orchestrator, provider-specific information authorization, and the information-release boundary.

A post-cutover IT Glue test demonstrated this invariant: a broad unscoped organization request was denied with `INFORMATION_RELEASE_DENIED` / `DERIVED_OUTPUT_TRANSFORMATION_REQUIRED` rather than releasing data. More specific bounded searches were allowed when authorized.

Autotask and IT Glue currently use the approved temporary Jason-managed requester-authorization path while preserving all other governance controls. Long-term debt remains tracked to restore stronger provider-native requester authorization where feasible.

## Host and recovery state

The host previously experienced an EXT4 metadata error and kernel list/pointer corruption across multiple 7.0 kernels. Memtest86+ completed without memory errors and Intel NVMe SMART data was healthy. The root filesystem was repaired and has remained clean through repeated current-boot kernel checks.

Current operating observations:

- kernel: `7.0.0-31-generic`;
- root filesystem: ext4, independently verified mounted read/write;
- current production-health root-writable metric: `1`;
- current production-health kernel signature count: `0`;
- current failed systemd unit count: `0`;
- Secure Boot remains disabled from diagnostics and should only be re-enabled deliberately after stability is established;
- BIOS is materially old and should not be flashed casually as part of normal Jason changes.

If corruption recurs, stop normal change work and investigate the board/memory-controller/firmware/intermittent storage path rather than assuming the SSD is bad.

## Rollback and recovery assets

The immediate pre-pagination MCP is preserved as:

- rollback container: `jason-mcp-pilot-pre-pagination-20260914T154422Z`;
- rollback image: `jason-mcp:pre-pagination-20260914T154154Z`;
- rollback image ID: `sha256:6d9303e501fac2690110f7526520ce2947be8783dcf3106be5709da1e1e5006d`.

The older pre-v4 MCP remains preserved as container `jason-mcp-pilot-pre-v4-20260914T085704` using image `jason-mcp:ticket-read-e91d5925290b`.

The pre-v4 authority database backup is `/var/lib/jason/authority/authority-pre-v4-20260914T085704.sqlite3`; the backup passed SQLite integrity validation at creation time.

OpenBao's canonical non-secret recovery documentation remains `docs/operations/Jason-OpenBao-Initialization-and-Recovery-Record.md`. Protected initialization material must not be copied into documentation, logs, Prometheus labels, dashboard panels, or chat.

The accepted provider-read-v4 checkpoint remains preserved at:

- directory: `/home/al/Jason-Evidence/Accepted-Checkpoints/jason-accepted-level-20260914T135724Z`;
- archive: `/home/al/Jason-Evidence/Accepted-Checkpoints/jason-accepted-level-20260914T135724Z.tar.gz`;
- archive SHA-256: `2193e1f7a28616f84ca55bf07d44b968e196077291c32e040c5319a23619b864`.

That checkpoint is a historical rollback/reference point representing the accepted v4 state before the pagination correction. It is intentionally not rewritten to imply that its older MCP image remains the current live image. The detailed checkpoint record remains `docs/operations/Jason-Checkpoint-2026-09-14-Provider-Read-v4.md`.

## Monitoring and dashboard state

The `Jason Production Health` dashboard is deployed and accepted in production. Deployment source `34bbf4df087cd7c07ff844183c48744b31fbca48` passed source validation, Prometheus rule validation, exporter startup, Prometheus scrape acceptance, Grafana provisioning acceptance, metric-contract acceptance, and post-deployment core-isolation checks.

Production observability state after exporter version 2 acceptance:

- `jason-production-health-exporter.service`: active;
- production-health exporter version: `2`;
- production-health exporter endpoint: `http://127.0.0.1:9467/metrics`;
- Prometheus production-health target: UP;
- Grafana dashboard UID: `jason-production-health`;
- Prometheus production alert rules: loaded;
- `jason-runtime`: running/healthy;
- `jason-mcp-pilot`: running on the pagination-corrected image/source above;
- OpenBao: running, initialized, and unsealed;
- required MCP secret-mount contract: pass;
- immediate pre-pagination rollback available: yes;
- pre-v4 MCP rollback available: yes;
- root filesystem host-namespace writable metric: 1;
- current-boot kernel error signature count: 0;
- failed systemd unit count: 0.

The production-health monitor detects the known duplicate MCP environment configuration: two entries each for `JASON_SOURCE_REVISION`, `JASON_PROVIDER_READ_ACTIVATION_PROFILE`, and `JASON_AUTOTASK_REQUESTER_AUTH_MODE`. The Datto pagination deployment deliberately preserved those duplicate-entry counts exactly rather than mixing issue #180 cleanup into an unrelated correctness change. The active/effective source revision is the pagination source commit above; the provider profile and requester mode remain unchanged.

### Root-filesystem monitor correction

Exporter version 1 incorrectly reported `jason_root_filesystem_writable 0` because the service deliberately uses `ProtectSystem=strict`, causing its own `/proc/mounts` to reflect the exporter's read-only service namespace instead of the host mount namespace.

Exporter version 2 is deployed and accepted. It prefers `/proc/1/mounts` for host mount state while preserving `ProtectSystem=strict`. Standard-library validation proved both RW/RO parsing and the live host root state before installation. The live v2 metric reports `jason_root_filesystem_writable 1`.

After Prometheus reevaluation, the stale `JasonRootFilesystemNotWritable` alert cleared. At accepted-level checkpoint time, the only active Jason alert was the expected `JasonMCPDuplicateEnvironment` warning.

The monitoring system intentionally does not direct-call external providers or expose credentials/provider records. Continuous governed provider canaries remain future work and must traverse the same Jason identity/authority/Central-Orchestrator path as real reads. Issue #181 tracks that work.

## Known production debt / gaps

### Duplicate MCP environment entries

The live MCP still contains duplicate entries for `JASON_SOURCE_REVISION`, `JASON_PROVIDER_READ_ACTIVATION_PROFILE`, and `JASON_AUTOTASK_REQUESTER_AUTH_MODE`. The pagination deployment used a raw Docker Engine API recreation path specifically to preserve the existing duplicate-entry counts rather than silently normalizing them. Runtime composition and live provider reads prove the effective configuration is working, but duplicated configuration remains ambiguous and should be cleaned up during a separately controlled MCP recreation. Tracked in GitHub issue #180.

### User-relevant output enrichment

Real-world tests have shown provider-native implementation identifiers in user-facing evidence, including Autotask foreign keys and raw Datto site fields. Provider foreign keys and implementation details should be translated into authoritative business values before presentation when the user needs the meaning rather than the implementation identifier.

Immediate design need: add canonical service-resource/technician read/search capabilities backed by Autotask Resources and continue tightening generic dynamic evidence projection so provider-native IDs remain internal unless needed for disambiguation, troubleshooting, audit, or an explicit user request. Tracked in existing user-relevant-output work.

### Microsoft tenant-wide coverage

Current Microsoft Graph production capabilities are intentionally narrow: `identity.user.search` and `identity.user.read`. Jason does not yet have governed tenant-wide reads for tenant/organization facts, verified domains, subscriptions/license inventory, Conditional Access, or Exchange/mailbox configuration.

Jason must say that those resource families are unavailable rather than saying Microsoft/Entra as a whole is unavailable. The Jason System Registry is Jason's own topology/operational registry and is not an authoritative fallback for Microsoft tenant facts. Tracked in GitHub issue #179.

### Provider-native requester authorization

Temporary Jason-managed requester authorization remains an approved transitional control for Autotask and IT Glue. Existing follow-up issues track restoration of provider-native requester authorization or an equivalent stronger mapping where the provider supports it reliably.

### Provider health canaries

Live provider reads were proven during acceptance and again through the Datto pagination production verification, but continuous external-provider canaries have not yet been added to the monitoring stack. Any such canary must remain low cadence, bounded, governed, read-only, non-disclosing, and must not bypass Jason by calling provider APIs with raw credentials from the monitoring system. Tracked in GitHub issue #181.

## User-facing operating principles confirmed by real-world testing

1. **User-Relevant Output Principle** — Jason translates provider-native evidence into canonical, human-relevant business information before presentation. Provider IDs and implementation details remain internal unless they are necessary to understand, disambiguate, troubleshoot, audit, or fulfill an explicit request.
2. **Capability-Aware Answer Principle** — Jason distinguishes what it can know, what it actually checked, and which capability/resource family is missing. It must not imply an entire provider is unavailable when only one capability family is unavailable, and it must not substitute a non-authoritative source.
3. **Authoritative-source principle** — Missing capability is preferable to invented or weakly sourced information. Foreign-key enrichment and cross-provider correlation must use governed authoritative reads.
4. **Collection-completeness principle** — A successful provider page is not automatically a complete collection. When authoritative metadata proves additional records exist, Jason must follow governed pagination to the full feasible collection within bounded safety limits or explicitly report that the result is partial/bounded.

The detailed user-relevant output and capability-awareness rule is in `docs/architecture/Jason-User-Relevant-Output-and-Capability-Awareness.md`.

## Current change-control state

PR #174 remains draft/open/unmerged. Its current head includes the pagination source correction, but the production deployment did not merge the PR and did not enable provider writes.

The Datto site-pagination defect is corrected and live-proven in production. Current operational work must continue to preserve the rollback containers/images, authority backups/checkpoints, OpenBao recovery assets, and the read-only/Central-Orchestrator security boundary.

The accepted provider-read-v4 checkpoint remains the historical recovery/reference level before this pagination change, while `docs/operations/Jason-Datto-Site-Pagination-Production-Deployment-2026-09-14.md` records the subsequent production promotion and live verification.
