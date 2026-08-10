# Jason Secret Provider Deployment Record

**Environment:** Jason pilot host  
**Profile:** Pilot  
**Status:** READY — OpenBao runtime, provider-specific AppRole paths, recovery, backup, restore, and governed read-only provider bindings are verified for the currently approved pilot scope  
**Owner:** Jason Architecture Authority  
**Last reconciled:** 2026-08-10

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
| Historical/general wrapper | `/usr/local/bin/jason-secret` | Installed and executable; not the canonical provider runtime |
| OpenBao configuration path | `/opt/jason/infrastructure/openbao/config` mounted read-only at `/openbao/config` | Verified |
| Storage backend | Integrated Raft at `/opt/jason/infrastructure/openbao/data` | Verified |
| Production provider authentication | Provider-specific OpenBao AppRole through JKD-003 | Verified for Autotask, IT Glue, and Datto RMM read-only bindings |
| Provider bootstrap credential pattern | `/opt/jason/bootstrap/secrets/openbao/<provider>-read-approle/{role-id,secret-id}` | Verified pattern |
| Runtime provider token lifecycle | Short-lived AppRole service token; one allow-listed KV v2 read; self-revoked; not persisted | Verified by tests and live provider proof |
| Shared persistent provider runtime token | Prohibited | Verified architecture rule |
| Historical wrapper token-file health path | May be unconfigured while production provider AppRole runtime is healthy | Verified operational distinction on 2026-08-10 |
| Audit device | File audit output at `/opt/jason/infrastructure/openbao/audit/audit.log` | Verified present and receiving requests |
| Seal status | Initialized and unsealed | Verified during 2026-08-10 host preflight |
| Seal method | Manual Shamir unseal, 3-of-5 | Verified from protected initialization material and successful unseal |
| Bootstrap credential | Revoked and `/etc/jason/openbao-bootstrap.token` removed | Verified |
| Commissioning contract-test input | `/etc/jason/openbao-contract-test.value` removed after commissioning | Verified |
| Historical wrapper health command | `/usr/local/bin/jason-secret --health` | Commissioning/general wrapper only; not a production-provider readiness gate |
| Historical wrapper contract command | `/usr/local/bin/jason-secret --contract-test <logical-name>` | Commissioning/general wrapper only; not a production-provider readiness gate |
| Canonical production-provider readiness | AppRole resolver tests + provider provisioning preflight + sanitized bounded live-read proof | Verified for IT Glue and Datto RMM on 2026-08-10 |
| Host validation Python | Repository-local `~/projects/jason/.venv` built from `implementation[dev]` | Verified; system Python did not contain pytest during 2026-08-10 validation |
| Direct resolver contract | `OpenBaoSecretResolver.resolve(logical_name, ConnectorContext)` with non-empty correlation ID | Verified |
| Backup unit | `/etc/systemd/system/jason-openbao-backup.service` | Installed; governed manual execution completed successfully on 2026-08-06 |
| Backup schedule | `/etc/systemd/system/jason-openbao-backup.timer`, daily at 02:30 | Installed and active when last inspected |
| Backup destination | `/opt/jason/backups/openbao` | Verified |
| Existing Raft snapshots | Multiple mode-`0600` snapshots and SHA-256 sidecars | Verified inventory |
| Last successful automated backup | 2026-08-06 09:05 EDT; checksum verified | Verified |
| Last successful restore test | 2026-08-06; isolated governed restore matched the live source contract | Verified |
| Operational owner | AOT Infrastructure Owner | Approved governance role |
| Escalation contact | AOT Security Escalation | Approved governance role |

## Logical secret mappings

| Logical name | Provider reference | Required fields | Runtime identity | Status |
|---|---|---|---|---|
| `jason.contract-test` | `secret/data/jason/contract-test` | contract value | Historical commissioning/general wrapper | Verified commissioning contract only |
| `autotask.readonly` | `secret/data/connectors/autotask/production/read-only` | `username`, `secret`, `integration_code` | `autotask-read-approle` | Verified canonical read-only contract |
| `it_glue.readonly` | `secret/data/connectors/it-glue/production/read-only` | `api_key` | `itglue-read-approle` | Verified AppRole resolution and bounded live read on 2026-08-10 |
| `datto_rmm.readonly` | `secret/data/connectors/datto-rmm/production/read-only` | `api_url`, `api_key`, `api_secret` | `datto-rmm-read-approle` | Verified AppRole resolution and bounded live read on 2026-08-10 |

## 2026-08-10 live provider validation

The physical Jason host validation proved the canonical provider runtime rather than the historical wrapper path.

Verified non-secret facts:

- OpenBao listened on `127.0.0.1:8200`, was initialized, unsealed, and active.
- Provider-specific AppRole artifact directories existed for IT Glue and Datto RMM.
- Canonical OpenBao resolver tests passed in the repository-local `.venv`.
- Provider secret architecture tests passed.
- IT Glue and Datto RMM credential-safe provisioning preflights passed without network contact or secret entry.
- Live AppRole resolution succeeded for `it_glue.readonly` and `datto_rmm.readonly`.
- Temporary service-token self-revocation completed and secret values were suppressed.
- A bounded governed IT Glue live read succeeded with one Organization record and sanitized output only.
- A bounded governed Datto RMM live read succeeded with one device record, runtime-only OAuth access token, and sanitized output only.
- Bounded provider discovery tools returned only approved identity metadata and stable external identifiers.
- No RoleID, SecretID, OpenBao token, provider credential, OAuth bearer token, or raw provider payload was printed or persisted as evidence.

### Historical wrapper finding

During this validation, `jason-secret --health` and `jason-secret --contract-test` returned:

`DENIED: OpenBao token file is not configured.`

This did **not** indicate production provider failure. The production provider runtime uses provider-specific AppRole identities. Operators must not create or restore a persistent provider token merely to satisfy the historical wrapper health path.

## Governed evidence references

Existing protected/non-secret evidence references include:

- Deployment verification JSON: `/home/al/Jason-Evidence/OpenBao/openbao-verification-20260805T133421Z.json`
- Deployment verification Markdown: `/home/al/Jason-Evidence/OpenBao/openbao-verification-20260805T133421Z.md`
- Recovery fingerprint: `/home/al/Jason-Evidence/OpenBao/openbao-recovery-fingerprint-20260806T113030Z.json`
- Authenticated commissioning contract evidence: `/home/al/Jason-Evidence/Secret-Provider/openbao-contract-test-20260806T114905Z.json`
- Bootstrap retirement evidence: `/home/al/Jason-Evidence/Secret-Provider/openbao-bootstrap-retirement-20260806T120329Z.json`
- Verified Raft backup and SHA-256 sidecar under `/opt/jason/backups/openbao/`
- Governed isolated restore evidence: `/home/al/Jason-Evidence/OpenBao/openbao-raft-restore-test-20260806T150504Z.json`
- Repository host-proof record: `08-Session-Records/IT-Glue-Datto-Host-Operational-Proof-2026-08-10.md`

The evidence must never contain tokens, passwords, unseal shares, recovery keys, API credentials, RoleIDs, SecretIDs, OAuth bearer tokens, or secret values.

## Readiness decision

The OpenBao runtime foundation, provider-specific AppRole architecture, automated backup workflow, isolated restore workflow, and governed read-only Autotask, IT Glue, and Datto RMM provider bindings are approved for the current single-host pilot scope.

The 2026-08-10 live proof authorizes continued **observe-only, bounded, registered** provider validation. It does not authorize arbitrary provider enumeration, write capabilities, canonical relationship promotion, or remote/multi-host OpenBao use without the required TLS and architecture review.

For RMM-managed devices, ADR-004 establishes Datto RMM as the authoritative external provider for managed-device existence and operational identity. IT Glue remains a documentation observation. Jason retains provider-independent canonical identity and cross-provider mapping authority.

## Change rule

Any change to the provider runtime, endpoint, wrapper, authentication method, AppRole policy, logical mappings, storage backend, audit device, backup process, recovery method, token lifecycle, ownership, escalation path, or readiness gates must update this record in the same governed change.
