# Jason Production Monitoring Baseline

## Purpose

This baseline defines the operational signals that the Jason Command Center displays and the conditions that should raise an alert. Monitoring is observational only; it must never grant authority, bypass Jason governance, call providers with raw monitoring credentials, or expose secrets/provider records into Prometheus labels.

The baseline was refreshed after the 2026-09-14 host recovery and MCP v4 provider-read cutover. The dedicated production-health dashboard/exporter was deployed and accepted on 2026-09-14.

## Monitoring boundary

The observability stack may read host state, Docker metadata, local health endpoints, secret-safe operational snapshots, and already-produced Jason telemetry. It must not:

- read or export provider credentials;
- print OpenBao unseal shares, tokens, AppRole values, OAuth/JWT material, API keys, or provider secrets;
- bypass the Central Orchestrator to perform external-provider canaries;
- mutate authority or provider state;
- include raw ticket/document/user/device evidence in Prometheus labels;
- treat dashboard status as authorization.

## Deployed production-health stack

The accepted deployment includes:

- systemd service `jason-production-health-exporter.service`;
- secret-safe exporter endpoint `http://127.0.0.1:9467/metrics`;
- Prometheus file-SD job `jason-production-health`;
- alert rule group `jason-production-health`;
- Grafana dashboard UID `jason-production-health`;
- rollback-protected observability-only deployment tooling.

Acceptance proved that `jason-runtime`, `jason-mcp-pilot`, and OpenBao container identities were unchanged by the monitoring deployment. The deployment does not call external providers and does not introduce provider writes.

## Critical host monitors

| Signal | Expected | Alert intent |
| --- | --- | --- |
| Host/node exporter reachable | 1 | host or observability failure |
| Root filesystem usage | < 85% warning; < 95% critical | avoid capacity-related failure |
| Root filesystem mount | read/write | fail immediately if root unexpectedly read-only |
| Current-boot kernel corruption/error signatures | 0 | detect recurrence of EXT4/Oops/GPF/list corruption/I/O/media errors |
| Failed systemd units | 0 | detect host service degradation |

Kernel error matching should include at minimum: `EXT4-fs error`, `general protection fault`, `list_del corruption`, `I/O error`, `media error`, `kernel BUG`, and `Oops:`.

Because of the 2026-09-14 incident, any recurrence of those signatures is a high-priority investigation event. Monitoring should not automatically reboot the host.

### Root mount namespace requirement

The production-health exporter service deliberately uses `ProtectSystem=strict`. Therefore the exporter's own `/proc/mounts` represents its hardened service mount namespace and can report `/` as read-only even when the host root filesystem is healthy and mounted read/write.

The host root-mount monitor must read PID 1's mount namespace via `/proc/1/mounts` first, with `/proc/mounts` only as a fallback. Do not weaken the systemd sandbox to make the metric pass. Exporter version 2 implements this correction and has regression tests for host-namespace preference/fallback.

The original production acceptance sample returned `jason_root_filesystem_writable 0` because exporter version 1 used the service namespace. That observation is a monitoring false negative, not evidence that the host root filesystem remounted read-only. The host had already been independently verified read/write and kernel-error count was zero. Version 2 must be deployed before this particular metric/alert is treated as authoritative.

## Jason runtime / MCP contract monitors

### Durable desired-state contract — 2026-09-22

Production Health now reads the secret-safe desired-state contract at `/var/lib/jason/production-health/contract.json` before falling back to the older `JASON_EXPECTED_*` systemd environment values. This prevents an approved MCP release from appearing unhealthy merely because the long-lived exporter unit still names a prior image or source revision.

The contract contains only deployment metadata needed for verification: approved MCP image/source revision, provider activation profile, Autotask requester mode, bounded Datto execution profile/allowlist/component scope/device class, and feature-state metadata. It must never contain credentials, tokens, secret values, returned provider records, or client data. `infrastructure/showcase/production_health_contract.example.json` documents the schema. Updating this contract is part of each production MCP promotion.

Datto site-variable create/update intentionally reuses the existing Datto execution identity; Production Health therefore verifies the shared Datto execution profile and the Datto execution credential mount pair rather than requiring the retired dedicated `owner-site-variable-v1` environment profile. When Kyocera KFS is part of the approved production MCP baseline, the KFS OpenBao role/secret mount destinations are also required and must be read-only.

On 2026-09-22 the live MCP credential mounts were corrected to read-only, the duplicate/stale `JASON_SOURCE_REVISION` entry was removed, source provenance was aligned to the active KFS production commit, the runtime received its repository-defined `/healthz` Docker health check, and the exporter was advanced to contract version 5. Prometheus subsequently reported all Production Health contract signals healthy with zero firing alerts.


| Signal | Expected production value |
| --- | --- |
| `jason-runtime` state | running |
| `jason-runtime` Docker health | healthy |
| `jason-mcp-pilot` state | running |
| MCP image | `jason-mcp:kfs-prod-c3e0728` at the 2026-09-22 accepted KFS release |
| MCP source revision | `c3e0728eb6f434d2ba033ae6b3eb72e3616ef95d` at the 2026-09-22 accepted KFS release |
| provider-read activation profile | `itglue-autotask-entra-procurement-catalog-v5` |
| Autotask requester mode | `jason_managed` while transitional authorization remains approved |
| MCP network | `jason-core` |
| MCP port binding | `10.87.246.157:8765 -> 8000/tcp` |
| MCP restart policy | `no` |
| required read-only credential mounts | present |
| watched MCP environment duplicate count | 0 desired |

### Resolved production drift — 2026-09-22

The prior duplicate/stale MCP environment state is resolved. `JASON_SOURCE_REVISION`, the MCP provenance labels, the active image tag, and `/var/lib/jason/production-health/contract.json` must identify the same accepted production release. `JasonMCPDuplicateEnvironment` and `JasonMCPContractDrift` remain enabled as regression detectors.

The `JasonMCPDuplicateEnvironment` Prometheus rule uses a two-minute `for` period. An immediate post-deployment query can therefore legitimately show zero firing alerts even while the duplicate metric is nonzero; the rule should be evaluated after the hold period before asserting notification state.

## OpenBao / credential monitors

| Signal | Expected |
| --- | --- |
| OpenBao container | running |
| OpenBao health endpoint | initialized and unsealed |
| required MCP credential bind destinations | present |
| staged credential leaf type | regular file (validated during recovery/deployment) |
| staged credential permissions | mode 0400, UID/GID 1000 where applicable |

The monitoring exporter may inspect mount destinations and OpenBao's unauthenticated health endpoint. It must not read credential contents.

Because `/run` is ephemeral, post-reboot operational checks must verify credential staging before dependent provider-read containers are treated as ready.

## Authority / governance monitors

The following are required operational invariants even when not all are scraped every 15 seconds:

- exactly one active Microsoft-to-Jason binding for the production requester context used by the pilot;
- provider read grants remain OBSERVE-only;
- no provider write surface becomes discoverable;
- `direct_provider_access=false`;
- `write_tools_enabled=false`;
- governed execution remains Central Orchestrator;
- expected v4 capability catalog remains active;
- information-release denial remains fail-closed for disallowed/unbounded disclosure.

High-frequency scraping should not execute authority mutations or external provider reads. Authority/capability contract validation is better performed through a low-frequency secret-safe snapshot/canary job whose output contains only pass/fail/count metadata.

## Provider health monitoring

Provider connectivity must eventually have low-cadence governed canaries for:

- Datto RMM;
- IT Glue;
- Autotask;
- Microsoft Graph.

These canaries must execute through the same Jason identity/authority/Central-Orchestrator path as a real request. They must use bounded non-sensitive selectors and export only status, latency, provider name, canonical capability name, and safe error class/reason. They must not log returned user/ticket/document/device records or provider-native identifiers.

**Current state:** all four provider paths have live post-cutover acceptance evidence, but continuous governed provider canaries are not yet deployed. Until the canary implementation exists, the dashboard distinguishes “production contract healthy” from “external provider canary healthy” rather than representing source-code presence as provider health. Issue #181 tracks this work.

## Recovery / rollback monitors

The dashboard shows or should show:

- pre-v4 rollback MCP container exists;
- current production MCP image/profile contract;
- authority backup existence/integrity from the most recent accepted cutover;
- OpenBao recovery record exists;
- current boot kernel-corruption count.

Current rollback reference: `jason-mcp-pilot-pre-v4-20260914T085704`.

Current authority backup reference: `/var/lib/jason/authority/authority-pre-v4-20260914T085704.sqlite3`.

Monitoring must never remove rollback/recovery assets automatically.

## Product-quality monitors / review items

Not every quality problem is suitable for a Prometheus alert, but the Command Center/status documentation tracks these active gaps:

1. **Provider foreign-key leakage:** unresolved IDs presented where a human/business value should have been resolved. First observed with Autotask assigned resource. Issue #178.
2. **Microsoft tenant-level capability coverage:** Entra user reads are live; tenant/domain/license/Conditional Access/Exchange resource families remain missing. Issue #179.
3. **Duplicate MCP environment entries:** resolved in production on 2026-09-22; retain the alert as a regression detector. Historical tracking: Issue #180.
4. **Temporary provider requester authorization:** Autotask and IT Glue Jason-managed requester authorization remains transitional debt.
5. **Continuous provider canaries:** acceptance proof exists but continuous governed canaries are pending. Issue #181.

## Alert severity guidance

### Critical

- runtime not healthy;
- MCP not running;
- OpenBao sealed/uninitialized/unreachable;
- current-boot kernel corruption/error signature detected;
- host root filesystem unexpectedly read-only after the host-namespace monitor is authoritative;
- unexpected provider write capability/authority detected.

### Warning

- MCP image/source/profile drift;
- duplicate watched MCP environment variables;
- required credential mount contract drift;
- failed systemd unit(s);
- rollback container missing;
- root filesystem >85%;
- stale authority operational-health snapshot;
- provider canary unavailable/degraded once canaries are implemented.

## Dashboard layout

The dedicated `Jason Production Health` dashboard provides at-a-glance panels for:

- runtime health;
- MCP running state and contract compliance;
- OpenBao initialized/unsealed state;
- kernel error count;
- failed systemd units;
- root mount RW and disk usage;
- MCP env-duplicate count;
- credential mount contract;
- rollback presence;
- current active alert table;
- existing host CPU/memory trends.

The existing Command Center, usage, and authority dashboards remain useful and should not be replaced.

The `Jason Governed Actions` dashboard must render zero alert counts explicitly with `or vector(0)`, expose pending alerts separately from firing alerts, and show both pending/firing rows in its alert table. This prevents a healthy zero-alert state from appearing as Grafana `N/A` and preserves the Prometheus hold-period distinction.


## Notification routing

Prometheus alert rules are evaluated and displayed in Prometheus/Grafana. External notification delivery (Teams/email/page) is a separate operational change and should be added deliberately so that alert routing does not accidentally create an unauthorized action path.
