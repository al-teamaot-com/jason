# Jason Boot Recovery Production Acceptance — 2026-09-24

**Status:** Installed and non-disruptively accepted; full host reboot acceptance pending explicit approval  
**Authority:** AOT Owner / Jason Governance Authority  
**Repository change:** PR #223  
**Merged source:** `4e3b7a4ad26c70650b78ce7b61e9408d439ed743`

## Incident context

A power outage occurred while build/worktree cleanup was in progress. After the host returned, the Jason operating system and several supporting containers were online, but the governed Jason runtime path was not fully available.

Observed causes:

1. `/run/jason-runtime-credentials` was absent after reboot. This was expected because `/run` is ephemeral, but no boot process restaged the required IT Glue/Autotask AppRole files.
2. OpenBao was initialized but sealed. The runtime failed closed with HTTP 503 during AppRole authentication.
3. `jason-mcp-pilot` had Docker restart policy `no`.
4. Prometheus had a stale bind mount to the disposable `openai-usage-reporting-20260922` worktree, and the expected `prometheus.yml` path had become a directory after the interrupted cleanup.

No provider mutation was required to recover Jason.

## OpenBao recovery evidence

The protected initialization artifact was verified before use:

- path: `/opt/jason/bootstrap/secrets/openbao/init.json`;
- owner: `root:root`;
- mode: `0600`;
- SHA-256: `877c7ff2688282444a1f232f3e12bec633dad09349513c48431da9aaf7a7d6c6`, matching the canonical recorded fingerprint.

Three Base64 Shamir shares were submitted directly from the protected file to the local OpenBao unseal API. The share values were not printed, copied into shell history, chat, Git, or evidence.

Observed progression:

- share 1: accepted, progress 1, sealed true;
- share 2: accepted, progress 2, sealed true;
- share 3: accepted, progress reset, sealed false.

Final OpenBao state:

- initialized: true;
- sealed: false;
- HA enabled: true;
- health endpoint: HTTP 200.

## Runtime credential recovery

The existing governed staging tool restored the four ephemeral provider-read artifacts:

- Autotask RoleID;
- Autotask SecretID;
- IT Glue RoleID;
- IT Glue SecretID.

Verified metadata:

- runtime UID/GID: `1000:1000`;
- mode: `0400`;
- all four files nonzero;
- no credential value printed.

## Boot-recovery implementation

PR #223 added:

- `tools/jason_boot_recovery.py`;
- `infrastructure/boot-recovery/jason-boot-recovery.service`;
- `infrastructure/boot-recovery/jason-boot-recovery.timer`;
- `docs/operations/Jason-Boot-Recovery.md`.

CI validation passed before merge.

Installed host state:

- `/usr/local/sbin/jason-boot-recovery`: root-owned executable;
- `jason-boot-recovery.service`: enabled;
- `jason-boot-recovery.timer`: enabled and active.

The first installed service execution completed successfully and emitted:

- `OPENBAO_UNSEAL=NOT_NEEDED` because the incident recovery had already unsealed OpenBao;
- `OPENBAO_READY=PASS`;
- `RUNTIME_CREDENTIAL_STAGING=ALREADY_READY`;
- `JASON_RUNTIME_HEALTH=PASS`;
- `JASON_MCP_PILOT_HEALTH=PASS`;
- `JASON_BOOT_RECOVERY=PASS`.

A journal scan for common secret-bearing patterns returned `RECOVERY_LOG_SECRET_CHECK=PASS`.

## Core service acceptance

Final non-disruptive checks returned:

- `openbao`: running, `restart=unless-stopped`;
- `jason-runtime`: running, healthy, `restart=unless-stopped`;
- `jason-mcp-pilot`: running, `restart=unless-stopped`;
- `jason-teams-gateway`: running, `restart=unless-stopped`;
- `openclaw-openclaw-gateway-1`: running, healthy, `restart=unless-stopped`;
- MCP internal health: HTTP 200.

## Monitoring durability repair

Prometheus was recreated from the durable main-repository source:

`/home/al/projects/jason/infrastructure/showcase/prometheus/prometheus.yml`

rather than the deleted disposable worktree.

Post-repair acceptance:

- Prometheus: HTTP 200 / healthy;
- Grafana: HTTP 200;
- Prometheus restart policy: `unless-stopped`.

Grafana was not recreated during this repair.

## Security/governance decision

The current pilot uses Shamir 3-of-5 sealing, but the protected initialization artifact is retained on the same host. AOT Owner explicitly accepts root-only local automatic unseal for this **single-host pilot** so host restart does not require manual recovery.

This choice does not provide meaningful additional protection against compromise of host root. It must not be represented as split custody, HSM protection, or KMS-backed auto-unseal.

Future production/multi-host architecture should use an approved hardware/KMS auto-unseal design or true off-host custody.

The boot recovery controller restores only the already-approved runtime shape and grants no provider, client, mutation, approval, or business authority.

## Acceptance limitation

A complete host reboot/power-cycle was **not performed after installing the new recovery control**. Under Jason governance, reboot is disruptive and requires explicit approval.

Therefore the accepted statement is:

> The boot-recovery controller, timer, OpenBao recovery method, credential restaging, runtime/MCP recovery path, monitoring repair, and secret-safe logging are installed and live-proven on the running host.

Do **not** claim:

> A post-install full host reboot recovery cycle has been proven.

That final disruptive acceptance remains pending a separately approved reboot test.
