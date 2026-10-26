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

- `jason-openclaw-authority-health.service` — lightweight, read-only health check.
- `jason-openclaw-authority-health.timer` — refreshes current availability every five minutes.
- `jason-openclaw-authority-full-integrity.service` — the original full SQLite `PRAGMA integrity_check` and authority backup/restore proof.
- `jason-openclaw-authority-full-integrity.timer` — schedules that heavyweight full check daily, separately from the frequent check and release reconciliation.

The frequent service runs `tools/openclaw_authority_fast_health.py` and atomically writes only secret-safe JSON to:

`/var/lib/jason/openclaw/operational-health.json`

It performs short, read-only SQLite schema lookups and current signing-key and delegation checks. **It cannot claim PASS unless the complete, independently generated full integrity and restore proof has passed within the last 30 hours.** It fails closed if that record is missing, stale, partial, unsafe, or demonstrates a failed backup/restore. Full scans are never performed in the five-minute service or synchronous host reconciliation.

The full service retains `tools/openclaw_authority_health_snapshot.py` and writes the full, mode-`0600` proof to:

`/var/lib/jason/openclaw/operational-full-health.json`

On the first upgrade, the frequent check may adopt the last actual `0600` full PASS snapshot into the separate full-proof path **only after independently checking all four DB integrity results, backup/restore details, signing keys, ownership, and age**. Its original modified timestamp is preserved; no missing proof is fabricated or treated as fresh. The new daily full service subsequently refreshes the evidence.

Both snapshots are owner-only mode `0600`. Operational health fails closed if required SQLite state is missing, has non-owner-only permissions, cannot be read, lacks a recent successful full integrity and backup/restore proof, or has unhealthy signing keys. CCC retains its separate provider canaries and deployment-specific requirements.

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
