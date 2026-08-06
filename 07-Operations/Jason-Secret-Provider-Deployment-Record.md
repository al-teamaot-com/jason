# Jason Secret Provider Deployment Record

**Environment:** Jason pilot host  
**Profile:** Pilot  
**Status:** BLOCKED — technical runtime, backup, restore, and canonical Autotask binding are verified; human ownership and escalation assignments remain unresolved  
**Owner:** Jason Architecture Authority  
**Last reconciled:** 2026-08-06

## Purpose

This is the canonical non-secret operational record for the secret provider used by the Jason pilot environment. Capabilities and runbooks must rely on this record rather than rediscovering infrastructure details during execution.

`UNVERIFIED` or `BLOCKING` means the available evidence is insufficient. It is not permission to guess.

## Verified deployment facts

| Field | Verified value | Status |
|---|---|---|
| Selected provider | OpenBao | Verified |
| Runtime type | Docker container | Verified |
| Service or container name | `openbao` | Verified |
| Runtime image | `ghcr.io/openbao/openbao:2.6.1` | Verified |
| Listener or endpoint | `127.0.0.1:8200` mapped to container port `8200/tcp` | Verified |
| Pilot TLS mode | HTTP on loopback only | Verified for single-host pilot; remote or multi-host use requires TLS |
| Canonical wrapper | `/usr/local/bin/jason-secret` | Installed and executable |
| OpenBao configuration path | `/opt/jason/infrastructure/openbao/config` mounted read-only at `/openbao/config` | Verified |
| Storage backend | Integrated Raft at `/opt/jason/infrastructure/openbao/data` | Verified |
| Authentication method | Dedicated OpenBao service token stored at `/etc/jason/openbao.token` | Verified |
| Runtime token ownership and mode | `root:root`, mode `0600` | Verified |
| Runtime token parentage | Orphan token; no parent accessor | Verified |
| Runtime policy | `jason-contract-test` plus `default` | Verified |
| Logical contract path | `secret/data/jason/contract-test` | Verified |
| Audit device | File audit output at `/opt/jason/infrastructure/openbao/audit/audit.log` | Verified present and receiving requests |
| Seal status | Initialized and unsealed | Verified after threshold unseal ceremony |
| Seal method | Manual Shamir unseal, 3-of-5 | Verified from protected initialization material and successful unseal |
| Bootstrap credential | Revoked and `/etc/jason/openbao-bootstrap.token` removed | Verified |
| Contract-test input | `/etc/jason/openbao-contract-test.value` removed after commissioning | Verified |
| Health-check command | `/usr/local/bin/jason-secret --health` | Verified; returns `healthy` |
| Secret-resolution contract test | `/usr/local/bin/jason-secret --contract-test jason.contract-test` | Verified; returns `contract-ok` |
| Production bootstrap gate | Production readiness denies bootstrap credential presence except explicit check-only commissioning mode | Verified |
| Backup unit | `/etc/systemd/system/jason-openbao-backup.service` | Installed; governed manual execution completed successfully on 2026-08-06 |
| Backup schedule | `/etc/systemd/system/jason-openbao-backup.timer`, daily at 02:30 | Installed and active when last inspected |
| Backup destination | `/opt/jason/backups/openbao` | Verified |
| Existing Raft snapshots | Multiple mode-`0600` snapshots and SHA-256 sidecars | Verified inventory |
| Last successful automated backup | 2026-08-06 09:05 EDT; snapshot `/opt/jason/backups/openbao/openbao-raft-Jason-20260806T130505Z.snap`; checksum verified | Verified |
| Last successful restore test | 2026-08-06; isolated governed restore from the verified snapshot; restored cluster identity and authenticated secret contract matched the live source | Verified |
| Operational owner | UNVERIFIED | Blocking |
| Escalation contact | UNVERIFIED | Blocking |

## Logical secret mappings

| Logical name | Provider reference | Required fields | Status |
|---|---|---|---|
| `jason.contract-test` | `secret/data/jason/contract-test` | contract value | Verified commissioning contract only |
| `autotask.readonly` | `secret/data/connectors/autotask/production/read-only` | `username`, `secret`, `integration_code` | Verified canonical read-only contract; dedicated AppRole artifacts present |
| `it_glue.readonly` | `secret/data/connectors/it-glue/production/read-only` | `api_key` | Path documented; live binding not approved by this record |
| `datto_rmm.readonly` | UNVERIFIED | Provider-defined read-only fields | Blocking |

## Governed evidence references

- Deployment verification JSON: `/home/al/Jason-Evidence/OpenBao/openbao-verification-20260805T133421Z.json`
- Deployment verification Markdown: `/home/al/Jason-Evidence/OpenBao/openbao-verification-20260805T133421Z.md`
- Recovery fingerprint: `/home/al/Jason-Evidence/OpenBao/openbao-recovery-fingerprint-20260806T113030Z.json`
- Authenticated contract evidence: `/home/al/Jason-Evidence/Secret-Provider/openbao-contract-test-20260806T114905Z.json`
- Bootstrap retirement evidence: `/home/al/Jason-Evidence/Secret-Provider/openbao-bootstrap-retirement-20260806T120329Z.json`
- Verified Raft backup: `/opt/jason/backups/openbao/openbao-raft-Jason-20260806T130505Z.snap`
- Verified Raft backup checksum: `/opt/jason/backups/openbao/openbao-raft-Jason-20260806T130505Z.snap.sha256`
- Governed isolated restore evidence: `/home/al/Jason-Evidence/OpenBao/openbao-raft-restore-test-20260806T150504Z.json`

The evidence contains non-secret status, identity, version, path, permission, fingerprint, and contract results. It must not contain tokens, passwords, unseal shares, recovery keys, API credentials, or secret values.

## Readiness decision

The OpenBao runtime foundation, canonical secret wrapper, automated backup workflow, isolated restore workflow, and canonical `autotask.readonly` binding are technically verified. The environment remains **blocked for CAP-001 live Autotask reads** only until the following human governance assignments are explicitly approved and recorded:

1. Name the operational owner.
2. Name the escalation contact.

CAP-001 check-only validation remains authorized. A production live read is not authorized until those assignments are recorded; technical evidence must not be used to infer or invent human authority.

## Change rule

Any change to the provider runtime, endpoint, wrapper, authentication method, logical mappings, storage backend, audit device, backup process, recovery method, token lifecycle, ownership, escalation path, or readiness gates must update this record in the same governed change.
