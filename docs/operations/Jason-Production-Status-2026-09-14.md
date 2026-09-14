# Jason Production Status — 2026-09-14

## Purpose

This record captures the current production state after the governed provider-read v4 cutover, host/OpenBao recovery, production-health monitoring deployment, and accepted-level rollback checkpoint completed on 2026-09-14. It is a factual operating record, not a replacement for architecture, recovery, or security-control documentation.

## Current production state

Jason is operating in governed read-only mode. The live MCP is `jason-mcp-pilot` on image `jason-mcp:autotask-entra-67da8d80ca97-repaired`, sourced from Git commit `67da8d80ca9703505d651e9e0935f5bd1aa7c651`. The active provider-read profile is `itglue-autotask-entra-governed-catalog-v4`.

The live interface reports:

- mode: read-only;
- governed execution: Central Orchestrator;
- direct provider access: disabled;
- write tools: disabled.

The separate `jason-runtime` container is running and healthy. It was not restarted during the MCP v4 cutover, production-health monitoring deployment, exporter-v2 correction, or accepted-level checkpoint.

OpenBao is initialized, unsealed, and using raft storage. Runtime provider credentials are staged as read-only bind-mounted files under `/run/jason-runtime-credentials/openbao`; `/run` is ephemeral and the credential staging must be restored after a host reboot before dependent containers are started.

## Governed provider-read milestone

Live Jason has production governed read access to all four target operational data sources:

| Provider | Current governed surface | Production validation |
| --- | --- | --- |
| Datto RMM | managed endpoint/site/alert reads already present in the governed catalog | live governed site read completed after v4 cutover |
| IT Glue | 10 documentation search/read capabilities | live governed organization search completed after v4 cutover; broad unscoped disclosure correctly failed closed at the information-release boundary |
| Autotask | 11 service-management search/read/count capabilities | live governed ticket count completed after v4 cutover |
| Microsoft Entra / Graph | exact user search and exact user read | live governed user search and read completed after v4 cutover |

The v4 authority cutover added 23 observe-only provider grants: 10 IT Glue, 11 Autotask, and 2 Microsoft Entra. Existing Datto RMM observe grants were preserved. No provider write grant was introduced.

## Autotask ticket-status correction

The Autotask status-label defect discovered during acceptance was fixed before production cutover. Autotask's `Tickets/entityInformation` endpoint returns entity-level metadata only; field/picklist data must be read from `Tickets/entityInformation/fields`. The connector now resolves labels such as `New` through that field metadata and then uses the numeric picklist value for the bounded count/search operation.

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

The pre-v4 MCP is preserved as container `jason-mcp-pilot-pre-v4-20260914T085704` using image `jason-mcp:ticket-read-e91d5925290b`.

The pre-v4 authority database backup is `/var/lib/jason/authority/authority-pre-v4-20260914T085704.sqlite3`; the backup passed SQLite integrity validation at creation time.

OpenBao's canonical non-secret recovery documentation remains `docs/operations/Jason-OpenBao-Initialization-and-Recovery-Record.md`. Protected initialization material is not to be copied into documentation, logs, Prometheus labels, dashboard panels, or chat.

The accepted current-level checkpoint was successfully created at:

- directory: `/home/al/Jason-Evidence/Accepted-Checkpoints/jason-accepted-level-20260914T135724Z`;
- archive: `/home/al/Jason-Evidence/Accepted-Checkpoints/jason-accepted-level-20260914T135724Z.tar.gz`;
- archive SHA-256: `2193e1f7a28616f84ca55bf07d44b968e196077291c32e040c5319a23619b864`.

That checkpoint includes integrity-verified current authority and identity-binding SQLite backups, a secret-safe container contract snapshot, safe production-health metrics, alert state, rollback material, a manifest, and SHA-256 hashes. It changed no services, made no provider requests, and made no authority mutation. The detailed checkpoint record is `docs/operations/Jason-Checkpoint-2026-09-14-Provider-Read-v4.md`.

## Monitoring and dashboard state

The `Jason Production Health` dashboard is deployed and accepted in production. Deployment source `34bbf4df087cd7c07ff844183c48744b31fbca48` passed source validation, Prometheus rule validation, exporter startup, Prometheus scrape acceptance, Grafana provisioning acceptance, metric-contract acceptance, and post-deployment core-isolation checks.

Production observability state after exporter version 2 acceptance:

- `jason-production-health-exporter.service`: active;
- production-health exporter version: `2`;
- production-health exporter endpoint: `http://127.0.0.1:9467/metrics`;
- Prometheus production-health target: UP;
- Grafana dashboard UID: `jason-production-health`;
- Prometheus production alert rules: loaded;
- `jason-runtime`: running/healthy and container identity unchanged;
- `jason-mcp-pilot`: running and container identity unchanged;
- OpenBao: running, initialized, unsealed, and container identity unchanged;
- Prometheus and Grafana were not restarted for the exporter-v2 correction;
- MCP required secret-mount contract: pass;
- pre-v4 MCP rollback available: yes;
- root filesystem host-namespace writable metric: 1;
- current-boot kernel error signature count: 0;
- failed systemd unit count: 0.

The production-health monitor correctly detects the known duplicate MCP environment configuration: `environment_unique=0` and one extra value each for `JASON_SOURCE_REVISION`, `JASON_PROVIDER_READ_ACTIVATION_PROFILE`, and `JASON_AUTOTASK_REQUESTER_AUTH_MODE`. The accepted effective image/source/profile/requester-mode checks all remain PASS, so this is configuration ambiguity rather than a current runtime outage. `JasonMCPDuplicateEnvironment` is firing as expected. Issue #180 tracks cleanup.

### Root-filesystem monitor correction

Exporter version 1 incorrectly reported `jason_root_filesystem_writable 0` because the service deliberately uses `ProtectSystem=strict`, causing its own `/proc/mounts` to reflect the exporter's read-only service namespace instead of the host mount namespace.

Exporter version 2 is deployed and accepted. It prefers `/proc/1/mounts` for host mount state while preserving `ProtectSystem=strict`. Standard-library validation proved both RW/RO parsing and the live host root state before installation. The live v2 metric reports `jason_root_filesystem_writable 1`.

After Prometheus reevaluation, the stale `JasonRootFilesystemNotWritable` alert cleared. At accepted-level checkpoint time, the only active Jason alert was the expected `JasonMCPDuplicateEnvironment` warning.

The monitoring system intentionally does not direct-call external providers or expose credentials/provider records. Continuous governed provider canaries remain future work and must traverse the same Jason identity/authority/Central-Orchestrator path as real reads. Issue #181 tracks that work.

## Known production debt / gaps

### Duplicate MCP environment entries

The v4 MCP was created from the old environment file plus explicit v4 overrides. `docker inspect` therefore shows duplicate entries for `JASON_SOURCE_REVISION`, `JASON_PROVIDER_READ_ACTIVATION_PROFILE`, and `JASON_AUTOTASK_REQUESTER_AUTH_MODE`. Runtime composition proved that the active process is using the v4 profile and live Microsoft capabilities prove the v4 surface is active, so this is not currently a functional outage. It should nevertheless be removed during a controlled MCP recreation because duplicated configuration is ambiguous. The production-health monitor explicitly exposes the duplicate count until corrected. Tracked in GitHub issue #180.

### User-relevant output enrichment

A real-world test asked who was assigned to an Autotask ticket and Jason returned an Autotask resource ID instead of the technician's name. This is a product-quality defect. Provider foreign keys must be resolved through authoritative governed reads before being presented when the user needs the business meaning rather than the implementation identifier.

Immediate design need: add canonical service-resource/technician read/search capabilities backed by Autotask Resources and use them to resolve assigned resource, creator, owner, technician, queue/status and similar foreign-key references as needed. Tracked in GitHub issue #178.

### Microsoft tenant-wide coverage

Current Microsoft Graph production capabilities are intentionally narrow: `identity.user.search` and `identity.user.read`. Jason does not yet have governed tenant-wide reads for tenant/organization facts, verified domains, subscriptions/license inventory, Conditional Access, or Exchange/mailbox configuration.

Jason must say that those resource families are unavailable rather than saying Microsoft/Entra as a whole is unavailable. The Jason System Registry is Jason's own topology/operational registry and is not an authoritative fallback for Microsoft tenant facts. Tracked in GitHub issue #179.

### Provider-native requester authorization

Temporary Jason-managed requester authorization remains an approved transitional control for Autotask and IT Glue. Existing follow-up issues track restoration of provider-native requester authorization or an equivalent stronger mapping where the provider supports it reliably.

### Provider health canaries

Live provider reads were proven during acceptance, but continuous external-provider canaries have not yet been added to the monitoring stack. Any such canary must remain low cadence, bounded, governed, read-only, non-disclosing, and must not bypass Jason by calling provider APIs with raw credentials from the monitoring system. Tracked in GitHub issue #181.

## User-facing operating principles confirmed by real-world testing

1. **User-Relevant Output Principle** — Jason translates provider-native evidence into canonical, human-relevant business information before presentation. Provider IDs and implementation details remain internal unless they are necessary to understand, disambiguate, troubleshoot, audit, or fulfill an explicit request.
2. **Capability-Aware Answer Principle** — Jason distinguishes what it can know, what it actually checked, and which capability/resource family is missing. It must not imply an entire provider is unavailable when only one capability family is unavailable, and it must not substitute a non-authoritative source.
3. **Authoritative-source principle** — Missing capability is preferable to invented or weakly sourced information. Foreign-key enrichment and cross-provider correlation must use governed authoritative reads.

The detailed architectural rule and acceptance criteria are in `docs/architecture/Jason-User-Relevant-Output-and-Capability-Awareness.md`.

## Current change-control state

PR #174 remains draft/open/unmerged. The v4 production cutover did not merge the PR and did not enable provider writes. Current operational work must preserve the rollback container, authority backups/checkpoints, OpenBao recovery assets, and the read-only/Central-Orchestrator security boundary.

This state is now an **accepted stabilization checkpoint**. Do not make opportunistic cleanup changes merely because they are available. Changes should be driven by a real-world test failure, a monitored operational risk, an explicitly prioritized capability, or a security/reliability requirement. The duplicate MCP environment cleanup is real debt, but because effective v4 operation is proven, it should be scheduled deliberately rather than performed simply to make the dashboard green.
