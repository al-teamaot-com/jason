# OpenClaw + JKD-001 Operational Hardening

## Purpose

This runbook governs the deployed OpenClaw machine-trust, human-delegation, authority-state, replay-state, audit, key-lifecycle, and backup/recovery boundaries.

## Proven host state

On 2026-08-08 the Jason host proved:

- Ed25519 OpenClaw machine authentication with the private key retained inside the persistent OpenClaw secret mount;
- Jason public-key fingerprint pinning;
- signed machine-service execution through JKD-001, governance gates, and the Central Orchestrator;
- replay rejection;
- explicit human -> OpenClaw delegation with the human principal kept distinct from the OpenClaw service identity;
- human authority evaluated independently from the delegation record;
- immediate fail-closed behavior after delegation revocation;
- no provider credentials or external provider network calls in either synthetic proof;
- authority, replay, ingress-audit, and orchestration-audit SQLite state at mode `0600`.

## Operational health

Run:

```bash
python3 tools/openclaw_authority_operational_health.py
```

A passing report requires:

- authority, replay, ingress-audit, and orchestration-audit databases present;
- each security-sensitive database at mode `0600`;
- SQLite `PRAGMA integrity_check` returns `ok` for each database;
- trusted-key registry is present and, when present, mode `0600`;
- authority database backup and restore both pass integrity checks;
- restored authority record counts match the live source;
- no provider contact and no provider credential resolution.

The backup/restore proof uses an ephemeral local temporary directory and does not replace the live database.

## Delegation lifecycle

List sanitized delegation metadata:

```bash
python3 tools/delegation_maintenance.py list
```

Deactivate delegations whose `effective_until` has elapsed while retaining their historical records:

```bash
python3 tools/delegation_maintenance.py deactivate-expired \
  --recorded-by svc-jason-maintenance \
  --correlation-id maintenance-$(date +%s)
```

Expiration maintenance must never delete delegation history. A newly expired record becomes `expired` and generates an authority-audit event. Revocation remains explicit and immediate through the governed JKD-001 admin command.

## OpenClaw signing-key lifecycle

The OpenClaw private key remains only in the OpenClaw persistent secret boundary. Jason stores public keys and fingerprints only.

List safe public metadata:

```bash
python3 tools/register_openclaw_public_key.py \
  --registry /var/lib/jason/openclaw/trusted-keys/registry.json \
  list
```

Registering a replacement key should follow an overlap-first rotation:

1. generate the replacement private key inside the OpenClaw secret boundary;
2. derive/copy only the public key to Jason;
3. register the new key ID with its expected fingerprint;
4. prove a signed synthetic request with the new key;
5. update OpenClaw to use the new key ID;
6. revoke the old public-key record;
7. prove the old key ID is rejected;
8. securely retire the old OpenClaw private key according to the host secret-retention policy.

Revoke a trusted public-key record:

```bash
python3 tools/register_openclaw_public_key.py \
  --registry /var/lib/jason/openclaw/trusted-keys/registry.json \
  revoke \
  --key-id <key-id> \
  --reason '<reason>'
```

Revocation changes only Jason's public trust registry. It must not print or retrieve private key material.

## Backup and recovery

The authority database contains institutional authorization history and must be recoverable without weakening file permissions.

Requirements:

- use SQLite online backup semantics, not raw copying while a writer is active;
- recovered files must be mode `0600`;
- run `PRAGMA integrity_check` before accepting a backup or restore;
- compare authority object counts during proof tests;
- preserve authority audit and historical delegation records;
- a restore does not itself reactivate expired/revoked delegations or contexts;
- production restoration remains a governed operational change and requires a separate approved restore procedure.

## Fail-closed rules

Stop or deny when:

- security-state permissions are broader than owner-only;
- a SQLite integrity check fails;
- the trusted-key registry has no valid active key for a production ingress;
- machine signature, timestamp, nonce, replay claim, principal binding, or delegation fails;
- a delegation is missing, inactive, expired, scope-mismatched, or below the requested mode;
- JKD-001 does not issue an exact execution context;
- the Central Orchestrator cannot validate the context;
- any flow would require OpenClaw to contact a provider directly or agents to communicate directly.

## Constitutional boundary

Operational maintenance never grants authority. Expiry cleanup, health inspection, key registry maintenance, and backup proof are administrative controls around the existing governed architecture. OpenClaw remains ingress/delegate, JKD-001 remains the authority service, governance gates remain mandatory, and the Central Orchestrator remains the sole execution coordinator.
