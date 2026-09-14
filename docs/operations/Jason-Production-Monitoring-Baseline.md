# Jason Production Monitoring Baseline

## Purpose

This baseline defines the operational signals that the Jason Command Center should display and the conditions that should raise an alert. Monitoring is observational only; it must never grant authority, bypass Jason governance, call providers with raw monitoring credentials, or expose secrets/provider records into Prometheus labels.

The baseline was refreshed after the 2026-09-14 host recovery and MCP v4 provider-read cutover.

## Monitoring boundary

The observability stack may read host state, Docker metadata, local health endpoints, secret-safe operational snapshots, and already-produced Jason telemetry. It must not:

- read or export provider credentials;
- print OpenBao unseal shares, tokens, AppRole values, OAuth/JWT material, API keys, or provider secrets;
- bypass the Central Orchestrator to perform external-provider canaries;
- mutate authority or provider state;
- include raw ticket/document/user/device evidence in Prometheus labels;
- treat dashboard status as authorization.

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

## Jason runtime / MCP contract monitors

| Signal | Expected production value |
| --- | --- |
| `jason-runtime` state | running |
| `jason-runtime` Docker health | healthy |
| `jason-mcp-pilot` state | running |
| MCP image | `jason-mcp:autotask-entra-67da8d80ca97-repaired` until the next explicitly accepted release |
| MCP source revision | `67da8d80ca9703505d651e9e0935f5bd1aa7c651` until superseded |
| provider-read activation profile | `itglue-autotask-entra-governed-catalog-v4` |
| Autotask requester mode | `jason_managed` while transitional authorization remains approved |
| MCP network | `jason-core` |
| MCP port binding | `10.87.246.157:8765 -> 8000/tcp` |
| MCP restart policy | `no` |
| required read-only credential mounts | present |
| watched MCP environment duplicate count | 0 desired |

### Known current exception

The live MCP currently contains duplicate Docker environment entries for source revision/profile/requester-mode because the v4 container was built from the previous environment file plus explicit overrides. Runtime composition and live capability execution prove the effective profile is v4, but the duplicate count should remain visible as a warning until a controlled container recreation removes the ambiguity.

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

**Current state:** all four provider paths have live post-cutover acceptance evidence, but continuous governed provider canaries are not yet deployed. Until the canary implementation exists, the dashboard should distinguish “production contract healthy” from “external provider canary healthy” rather than representing source-code presence as provider health.

## Recovery / rollback monitors

The dashboard should show:

- pre-v4 rollback MCP container exists;
- current production MCP image/profile contract;
- authority backup existence/integrity from the most recent accepted cutover;
- OpenBao recovery record exists;
- current boot kernel-corruption count.

Current rollback reference: `jason-mcp-pilot-pre-v4-20260914T085704`.

Current authority backup reference: `/var/lib/jason/authority/authority-pre-v4-20260914T085704.sqlite3`.

Monitoring must never remove rollback/recovery assets automatically.

## Product-quality monitors / review items

Not every quality problem is suitable for a Prometheus alert, but the Command Center/status documentation should track these active gaps:

1. **Provider foreign-key leakage:** unresolved IDs presented where a human/business value should have been resolved. First observed with Autotask assigned resource.
2. **Microsoft tenant-level capability coverage:** Entra user reads are live; tenant/domain/license/Conditional Access/Exchange resource families remain missing.
3. **Duplicate MCP environment entries:** current production warning until controlled cleanup.
4. **Temporary provider requester authorization:** Autotask and IT Glue Jason-managed requester authorization remains transitional debt.
5. **Continuous provider canaries:** acceptance proof exists but continuous governed canaries are pending.

## Alert severity guidance

### Critical

- runtime not healthy;
- MCP not running;
- OpenBao sealed/uninitialized/unreachable;
- current-boot kernel corruption/error signature detected;
- root filesystem unexpectedly read-only;
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

A dedicated `Jason Production Health` dashboard should provide at-a-glance panels for:

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

## Notification routing

Prometheus alert rules may be evaluated and shown in Prometheus/Grafana even without Alertmanager. External notification delivery (Teams/email/page) is a separate operational change and should be added deliberately so that alert routing does not accidentally create an unauthorized action path.
