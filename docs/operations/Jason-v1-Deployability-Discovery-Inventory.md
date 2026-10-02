# Jason v1.0 Deployability Discovery Inventory

**Parent:** #743  
**Workstream:** #747  
**Status:** Initial read-only discovery pass  
**Date:** 2026-10-02

## Safety boundary

This document records read-only discovery only. No production runtime, service, container, database, schedule, provider configuration, secret, network, or deployment state was changed.

Production deployment or production-impacting remediation remains blocked until explicit Owner approval.

## Objective

Identify everything the current Jason production host depends on, classify each dependency, and expose anything that prevents a clean environment from reproducing Jason using only released artifacts, documented configuration, governed secrets, and supported prerequisites.

## Initial host baseline

Observed on the current Jason host:

| Item | Observed |
| --- | --- |
| Host OS | Ubuntu 24.04.4 LTS x86_64 |
| Python | 3.12.3 |
| Docker | 29.6.2 |
| Docker Compose | v5.3.1 |
| Repository checkout | /home/al/projects/jason |
| Checkout branch during discovery | feature/gpt-insights-tech-assist-20261001 |
| Checkout HEAD during discovery | ab894ee4f131a7d26ede97a23174adb2e34a04bc |
| /opt/jason/current | /opt/jason/releases/c4a0c71ed618ac974a3ad04aef3a5a688c421d2e |
| Observability current | /opt/jason/observability/releases/33e229219ddf2c1afcd66f2068a14efa2a723808 |
| CCC current | /opt/jason/ccc-releases/c220164099d2655f5795f48a82aec7b298b8125b |

The repository checkout is therefore not itself authoritative evidence of the running release. Runtime identity must be derived from deployed artifacts, image labels, release symlinks, and a future deployment manifest.

## Existing reproducibility foundations

The current implementation already contains several useful primitives:

- versioned release directories under `/opt/jason/releases/<sha>`;
- a `/opt/jason/current` release symlink;
- versioned observability and CCC release trees;
- Docker image labels carrying Jason source revision for primary core containers;
- production deployment helpers that create rollback image tags and verify source revision;
- a governed bootstrap script;
- documented OpenBao bootstrap and recovery controls;
- runtime health checks;
- persistent state separated from container filesystems in several major components.

These should be preserved and consolidated rather than replaced.

## Running component inventory

The production host currently includes, at minimum:

### Jason platform/runtime

- `jason-runtime`
- `jason-mcp-pilot`
- `jason-teams-gateway`
- `jason-teams-gateway-pilot`
- `jason-core.service`
- multiple Jason exporters and maintenance services/timers

### Supporting platform services

- OpenBao
- OpenClaw gateway
- Grafana
- Prometheus
- Ollama
- node-exporter
- autonomy flight recorder
- work-item exporter

### Business/provider-specific supporting services

- KFS PostgreSQL

This inventory must still be reconciled against required vs optional capabilities for v1.0.

## Network prerequisites

Observed Docker networks used by current runtime:

- `jason-core`
- `jason-observability`
- `openclaw_default`

The current runtime Compose file declares these as external networks. A clean installer therefore must create or validate them before startup instead of assuming they already exist.

## Operational state inventory

Persistent or potentially durable state currently exists across several locations.

### /var/lib/jason

Observed classes include:

- authority databases and historical authority backups;
- client-boundary database;
- playbook registry and run history;
- governed execution state;
- autonomy operational/shadow/targeted-wake state;
- identity authority;
- model usage;
- orchestration events;
- security audit;
- Teams identity and continuation state;
- resolution memory;
- reflection state;
- support-repair and autonomous-repair spools;
- procurement state;
- trusted keys;
- CCC state;
- client posture;
- production-health state;
- provider-health canaries;
- runtime secret material/references.

### Docker volumes

Observed durable volumes include:

- KFS PostgreSQL data;
- Grafana data;
- Prometheus data;
- Ollama data;
- OpenBao file/storage volume in addition to bind-mounted OpenBao data paths.

### Other host state

- `/home/al/.local/state/jason`
- `/opt/jason/infrastructure/openbao/{data,audit,logs}`
- `/opt/jason/services/openclaw/data/*`

Issue #752 must determine which state is authoritative, which is rebuildable, and which must be included in backup/restore.

## Secret-delivery inventory

No secret contents were read.

Current runtime bind mounts show credential material or credential references arriving from multiple host roots, including:

- `/opt/jason/bootstrap/secrets`
- `/var/lib/jason/runtime-secrets`
- `/run/jason-runtime-credentials`
- `/home/al/jason-secrets`
- service-specific secret locations under `/opt/jason/services`

This is a deployability blocker because the clean-install contract cannot currently describe one canonical secret-enrollment location/process.

The existing secrets runbook documents provider-specific AppRole artifacts under `/opt/jason/bootstrap/secrets/openbao/<provider>-read-approle/`, while live runtime mounts also use the additional roots above. This drift must be reconciled without weakening the governed secrets model.

Destination: #748 and #749.

## Systemd and scheduling inventory

Observed host-level Jason services include:

- boot recovery;
- CCC;
- client-posture exporter;
- core;
- delegation maintenance;
- documentation reconciliation;
- Grafana assurance;
- OpenBao backup;
- OpenClaw authority health;
- playbook exporter;
- production-health exporter;
- reflection exporter;
- resolution-memory exporter;
- security-control exporter;
- status exporter;
- usage exporters.

Observed timers include boot recovery, Grafana assurance, OpenClaw authority health, delegation maintenance, documentation reconciliation, OpenBao backup, and CCC.

There are also user-cron `@reboot` entries invoking helper programs under `/home/al/.local/bin`.

A clean deployment cannot rely on manually accumulated systemd units and per-user cron state. Required schedules must be declared and installed deterministically.

Destination: #749.

## Host-local executable dependencies

Observed runtime dependencies outside a versioned Jason release include:

- `/home/al/.local/bin/jason-client-posture-exporter-start`
- `/home/al/.local/bin/jason-resolution-memory-exporter-start`
- `/home/al/.local/bin/jason-security-control-exporter-start`
- `/home/al/jason-runtime-tools/work_item_exporter.py`

The work-item exporter is directly bind-mounted into a running container from the home directory.

These are strong candidates for production-only/manual host state unless proven to be deterministic outputs of repository-controlled installation.

Destination: #747 follow-up and #749.

## Bootstrap assessment

Repository files:

- `bootstrap/bootstrap.sh`
- `bootstrap/dependencies.json`

Current declared minimums include Python 3.12, Docker 24.0, and Docker Compose 2.20 for the OpenBao profile.

The current host passes those prerequisite checks when the script is invoked with:

`bash bootstrap/bootstrap.sh --check --secrets-provider openbao`

However, the tracked file mode is `100644` / host mode `664`. Therefore the runbook-style direct invocation:

`./bootstrap/bootstrap.sh --check`

fails with permission denied on the current checkout.

More importantly, the bootstrap currently validates core prerequisites and can start the optional OpenBao reference container, but it does not yet perform a full Jason deployment. It does not presently initialize/validate the complete set of:

- release artifact installation;
- Jason networks;
- all required runtime services;
- systemd/timers;
- configuration schema;
- database/state initialization and migrations;
- complete governed secret enrollment;
- provider/client configuration;
- readiness across all required components;
- deployment manifest.

Destination: #749.

## Platform/configuration separation findings

The current runtime Compose file mixes generic platform settings with AOT-specific operational settings.

Examples observed include:

- AOT-named Datto RMM component names;
- concrete Datto component UIDs and approval modes;
- `jason@teamaot.com` as the SES default sender;
- provider-specific activation/autonomy defaults;
- model/pricing settings;
- MSP-specific provider configuration.

This does not mean those settings are incorrect for AOT. It means they should be supplied through the MSP configuration/policy layer rather than embedded as generic platform defaults where appropriate.

Destination: #748.

## Runtime identity findings

The main running core containers currently report source revision:

`c4a0c71ed618ac974a3ad04aef3a5a688c421d2e`

for:

- `jason-runtime`
- `jason-mcp-pilot`
- `jason-teams-gateway`

The host also has independently versioned components, including:

- observability release `33e229219ddf2c1afcd66f2068a14efa2a723808`;
- CCC release `c220164099d2655f5795f48a82aec7b298b8125b`;
- a Teams pilot container using release-tag `9f477e0d` without the same source-revision labels.

This confirms that a single repository HEAD is insufficient to identify a running Jason deployment. The v1.0 deployment manifest must be component-aware.

Destination: #750.

## Legacy/placeholder service requiring classification

`jason-core.service` currently runs:

`/usr/bin/sleep infinity`

under user/group `jason`.

It may be an intentional host anchor or a legacy placeholder. Its required role is not yet established by this discovery pass. A clean deployment specification must either document and install it intentionally or remove it from the required platform model.

No change was made.

## Initial classification matrix

| Dependency/state | Classification | Reproducibility status |
| --- | --- | --- |
| Python/Docker/Compose minimum versions | External prerequisite | Partially declared |
| Jason release directories/images | Platform artifact | Good foundation |
| Runtime Compose definitions | Platform + MSP configuration | Mixed; needs separation |
| AOT provider mappings/Datto components/default sender | MSP configuration/policy | Embedded in runtime config |
| OpenBao | Secrets provider implementation | Documented but runtime enrollment paths drift |
| AppRole RoleID/SecretID files | Secret/bootstrap material | Governed, but locations fragmented |
| /var/lib/jason authority/openclaw/playbook DBs | Operational state | Persistent but restore scope not fully canonical |
| KFS PostgreSQL data | Provider/business operational state | Persistent volume; restore scope required |
| Grafana/Prometheus/Ollama volumes | Supporting state/cache | Must classify rebuildable vs required |
| OpenClaw config/workspace | Platform/supporting operational state | Host-bound; clean-install contract needed |
| systemd services/timers | Platform operations | Partly repo-controlled, host-installed |
| per-user cron jobs | Host operational state | Non-deterministic until installer owns them |
| /home/al/.local/bin helpers | Host-local tooling | Deployability blocker until controlled |
| /home/al/jason-runtime-tools/work_item_exporter.py | Host-local runtime code | Deployability blocker |
| Docker external networks | Platform prerequisite | Must be created/validated |
| image source-revision labels | Deployment identity | Good foundation |
| component release symlinks | Deployment identity | Good foundation |
| one unified deployment manifest | Platform capability | Missing |

## Initial blockers

1. No single end-to-end clean-install/bootstrap path exists yet.
2. Secret bootstrap/runtime paths are fragmented.
3. Required operational state is not yet represented as a complete backup/restore contract.
4. Several runtime helpers exist outside versioned release directories.
5. Scheduling is split across systemd and user cron.
6. Runtime configuration contains MSP/AOT-specific values that should be separated from generic platform defaults.
7. Multiple component revisions are simultaneously valid, but no unified component-aware deployment manifest exists.
8. The bootstrap script is tracked without executable permission despite documentation using direct execution syntax.
9. External Docker networks are assumed rather than created/validated by the bootstrap.
10. The role of `jason-core.service` is not yet established for reproducible deployment.
11. Installed production systemd state is not fully source-identical: two OpenBao backup units and `jason-core.service` are host-only, and the production-health exporter has an installed configuration drift from the repository copy.
12. Live container Compose metadata is insufficient to reconstruct deployment origin/configuration for all core components.
13. The runtime exposes a large environment-driven configuration surface that is not yet governed by one explicit v1.0 configuration schema.

## Systemd reconciliation pass

The installed systemd units were compared by filename and SHA-256 against repository-controlled definitions.

### Exact repository matches

The majority of installed Jason units match repository-controlled files exactly, including boot recovery, CCC, delegation maintenance, documentation reconciliation, Grafana assurance, OpenClaw authority health, and the principal observability/exporter units.

This is positive evidence that much of the host service layer is already reproducible.

### Host-only units

The following installed units had no same-named unit definition under the repository infrastructure/deploy trees:

- `jason-core.service`
- `jason-openbao-backup.service`
- `jason-openbao-backup.timer`

The OpenBao deployment record documents the backup unit/timer as installed production state, but the actual unit definitions are not presently stored as same-named repository artifacts. Repository search found documentation and verification code referencing them, not a source unit definition.

A reproducible installer must either generate these units from version-controlled templates or carry the exact unit files as versioned artifacts.

### Installed-vs-repository drift

`jason-production-health-exporter.service` differs from the repository copy.

The observed difference is an expected-provider-profile value:

- repository: `itglue-autotask-entra-procurement-mail-contract-attachment-resource-catalog-v9`
- installed host: `itglue-autotask-entra-procurement-billing-reconciliation-catalog-v10`

This may represent a legitimate operational update, but the current deployment model does not make the source of that override self-evident. Environment-specific operational values should be supplied through explicit configuration or deterministic generation instead of an edited installed unit.

Destination: #748 and #749.

## Container lineage / configuration discovery pass

Current container metadata is not sufficient by itself to reconstruct all deployment inputs.

Observed:

- `jason-runtime` reports Compose project/service labels but no Compose working-directory/config-file labels;
- `jason-mcp-pilot` reports the same Compose project/service identity as `jason-runtime` despite being a separate live container/image;
- `jason-teams-gateway` does not expose equivalent Compose-origin labels.

The current runtime runbook instructs operators to derive Compose working directory/config from live labels. That strategy is not reliable for every currently running component.

The v1.0 deployment manifest and installer must carry authoritative deployment-source/configuration identity directly rather than depending on incidental Docker Compose labels.

Destination: #750.

## Runtime environment-name discovery

Only environment variable **names** were inspected; no values were read.

The core runtime/MCP surfaces expose a large environment-driven configuration contract covering authority/state paths, provider activation, Autotask/Datto/DNSFilter/KFS/Backup.NET profiles, autonomy, model settings, Teams integration, and other provider-specific controls.

The Teams gateway environment also includes credential-shaped names such as `MSTEAMS_APP_PASSWORD`. This discovery does not establish how the value is sourced, only that the running process receives such a variable.

For v1.0, configuration schema validation must explicitly distinguish:

- non-secret MSP configuration;
- governed policy;
- secret references/files;
- prohibited raw secret-in-environment patterns.

Destination: #748 and #749.

## Next discovery steps

- reconcile every installed Jason systemd unit against a repository-controlled source — **initial pass complete; host-only/drift items identified above**;
- reconcile every runtime bind mount against a declared platform/configuration/secret/state class;
- identify every host-local file used by a running service/container that is not part of a versioned release;
- enumerate required database schemas/migrations and initialization commands;
- enumerate required provider/client configuration inputs without reading secret values;
- identify which observability/local-model components are mandatory vs optional for v1.0;
- define the initial canonical dependency inventory consumed by #749.

## Production status

No production mutation was performed during this discovery pass.
