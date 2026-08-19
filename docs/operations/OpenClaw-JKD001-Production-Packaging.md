# OpenClaw + JKD-001 Production Operations Packaging

## Purpose

Package the already-proven OpenClaw -> JKD-001 -> governance -> Central Orchestrator boundary as repeatable host operations without changing its authority model.

This package does not grant provider access, add human authority, resolve provider credentials, or create agent-to-agent communication.

## Installed units

### Delegation lifecycle

- `jason-delegation-maintenance.service` — one-shot governed expiration normalization.
- `jason-delegation-maintenance.timer` — runs hourly with randomized delay.

Elapsed delegation records with `status=active` are changed to `expired`. Records are not deleted. Each changed delegation emits an `authority.delegation.expired` audit event with a unique maintenance correlation ID.

### Operational health

- `jason-openclaw-authority-health.service` — one-shot health snapshot.
- `jason-openclaw-authority-health.timer` — refreshes the snapshot every five minutes.

The service runs `tools/openclaw_authority_health_snapshot.py`, which executes the governed operational health proof and atomically writes only secret-safe JSON to:

`/var/lib/jason/openclaw/operational-health.json`

The snapshot is mode `0600`.

Operational health fails closed if required SQLite state is missing, has non-owner-only permissions, fails integrity checking, backup/restore proof fails, the trusted-key registry is missing or not `0600`, or there is no active OpenClaw signing key.

## Command Center

The existing Jason status exporter reads the latest secret-safe operational snapshot. It does not perform maintenance or backup operations itself.

Metrics include:

- `jason_openclaw_authority_operational_health`
- `jason_openclaw_trusted_signing_keys`
- `jason_openclaw_delegations{state=...}`
- `jason_authority_backup_restore_proof`
- `jason_openclaw_authority_snapshot_age_seconds`

Grafana dashboard `Jason OpenClaw / JKD-001 Operations` shows health, active trusted signing-key count, backup/restore proof, snapshot age, and delegation lifecycle counts. No key fingerprints, public-key contents, private-key information, credentials, or provider payloads are exported as metrics.

## CatchMeUp

`tools/catch_me_up.py` reports:

- production operations unit state;
- sanitized operational-health status;
- active trusted-key count;
- active/expired-active/inactive delegation counts;
- backup/restore integrity summary;
- provider-contacted/provider-credentials-used flags.

CatchMeUp reads the snapshot only. It does not perform authority maintenance or key lifecycle actions.

## Installation

Run from the Jason repository:

```bash
bash tools/install_openclaw_authority_operations.sh
```

The installer:

1. validates required repository assets;
2. preserves `/var/lib/jason/openclaw` as owner-only state;
3. installs the four systemd unit files;
4. enables both timers;
5. performs one immediate delegation-maintenance run;
6. writes the first health snapshot;
7. verifies the timers are active and the snapshot is mode `0600`.

The installer does not resolve provider credentials, contact a provider, rotate keys, or generate private key material.

## Fail-closed rules

- Never delete delegation history as lifecycle cleanup.
- Never treat an elapsed delegation as authority even before maintenance normalizes its stored state.
- Never run provider capabilities from maintenance/health services.
- Never place private signing keys under `/var/lib/jason`.
- Never expose trusted-key fingerprints or paths as Prometheus labels unless specifically approved; current metrics expose counts only.
- A missing or zero-active-key trusted registry is unhealthy.
- A stale health snapshot is observably stale through its age metric and must not be interpreted as current proof.

## Next trust operation

The next controlled trust milestone is an overlap-first Ed25519 rotation proof:

1. generate a second private key only inside the OpenClaw persistent secret boundary;
2. register the corresponding public key under a new key ID;
3. prove both old and new signed synthetic requests authenticate during overlap;
4. switch the synthetic signing proof to the new private key;
5. revoke the old public-key record;
6. prove the new key succeeds and the old key fails closed;
7. preserve rotation evidence without storing private material.

Do not delete the old private key until the new trust path and old-key revocation have both been proven.
