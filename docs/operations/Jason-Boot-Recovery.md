# Jason Boot Recovery

**Status:** Approved single-host pilot recovery control  
**Approved by:** AOT Owner / Jason Governance Authority  
**Effective date:** 2026-09-24

## Purpose

A host reboot or OpenBao container restart must not leave the Jason pilot unavailable until an operator manually reconstructs transient state.

The boot-recovery control restores only the already-approved single-host pilot runtime shape. It does not grant new provider authority, broaden credentials, change client scope, or bypass Jason governance.

## Recovery sequence

`jason-boot-recovery.service` runs as root after Docker and network readiness. It:

1. ensures the existing `openbao` container is running;
2. reads OpenBao health state;
3. when sealed, uses the existing protected `/opt/jason/bootstrap/secrets/openbao/init.json` recovery artifact to submit only the configured Shamir threshold of Base64 shares to the local OpenBao listener;
4. never prints or persists unseal shares outside the existing protected artifact;
5. restores the ephemeral IT Glue and Autotask runtime AppRole staging under `/run/jason-runtime-credentials/openbao` using the existing governed staging tool;
6. ensures `jason-runtime` uses `unless-stopped`, starts it, and waits for health;
7. ensures `jason-mcp-pilot` uses `unless-stopped`, starts it, and verifies its internal health endpoint;
8. starts existing Teams/OpenClaw/Ollama containers when present.

A periodic timer reruns the idempotent recovery check so an OpenBao container restart can recover without a host reboot.

## Security decision

OpenBao remains configured for Shamir sealing, but this single-host pilot already retains the protected initialization artifact on the same host for recovery. Automatic local recovery therefore does not claim split-custody protection against host-root compromise.

For the current pilot, AOT Owner explicitly accepts automatic root-only local unseal so unattended reboot recovery takes priority over a manual post-reboot ceremony.

This is **not** the preferred future multi-host/production design. A production-grade deployment should replace this local recovery pattern with an approved hardware- or KMS-backed auto-unseal design, or with true off-host split custody when unattended recovery is not required.

## Secret handling

The recovery process must never:

- print unseal shares, root tokens, RoleIDs, SecretIDs, provider credentials, or access tokens;
- place protected values on a command line;
- copy the protected initialization artifact into Git, tickets, chat, logs, or monitoring;
- synthesize new provider authority;
- fall back to environment variables containing production provider credentials.

## Installation

Repository-controlled files:

- `tools/jason_boot_recovery.py`
- `infrastructure/boot-recovery/jason-boot-recovery.service`
- `infrastructure/boot-recovery/jason-boot-recovery.timer`

Host installation:

```bash
sudo install -o root -g root -m 0750 tools/jason_boot_recovery.py /usr/local/sbin/jason-boot-recovery
sudo install -o root -g root -m 0644 infrastructure/boot-recovery/jason-boot-recovery.service /etc/systemd/system/jason-boot-recovery.service
sudo install -o root -g root -m 0644 infrastructure/boot-recovery/jason-boot-recovery.timer /etc/systemd/system/jason-boot-recovery.timer
sudo systemctl daemon-reload
sudo systemctl enable jason-boot-recovery.service jason-boot-recovery.timer
sudo systemctl start jason-boot-recovery.service
sudo systemctl start jason-boot-recovery.timer
```

## Acceptance

A recovery is accepted only when:

- OpenBao reports initialized and unsealed;
- all four ephemeral provider-read staging files have UID/GID `1000:1000`, mode `0400`, and nonzero length;
- `jason-runtime` is healthy;
- `jason-mcp-pilot` passes `/healthz`;
- no protected value appears in service output.
