# Jason Secret Provider Deployment Record

**Environment:** Jason pilot host
**Profile:** Pilot
**Status:** BLOCKED — deployment partially verified; required operational controls remain incomplete
**Owner:** Jason Architecture Authority
**Last verified:** 2026-08-05T13:34:42.257776+00:00

## Purpose

This is the canonical operational record for the secret provider used by the Jason pilot environment. Capabilities and operator runbooks must reference this record instead of asking an operator to discover infrastructure details during execution.

`UNVERIFIED` means the repository does not yet contain sufficient approved evidence. It is a blocking state, not an invitation to guess.

## Deployment facts

| Field | Verified value | Status |
|---|---|---|
| Selected provider | OpenBao | Documented architectural decision |
| Runtime type | Docker container | Verified |
| Service or container name | `openbao` | Verified |
| Runtime image | `ghcr.io/openbao/openbao:2.6.1` | Verified |
| Listener or endpoint | `127.0.0.1:8200` mapped to container port `8200/tcp` | Verified |
| TLS mode | UNVERIFIED | Blocking |
| Canonical wrapper | `/usr/local/bin/jason-secret` | NOT IMPLEMENTED |
| OpenBao executable path | Container executable `bao` observed; host executable path not applicable to current runtime | Partially verified |
| OpenBao configuration path | Host bind `/opt/jason/infrastructure/openbao/config` mounted at `/openbao/config` | Verified |
| Storage path or backend | Host bind `/opt/jason/infrastructure/openbao/data` mounted at `/openbao/data`; Docker volume mounted at `/openbao/file` | Backend behavior still requires verification |
| Authentication method | UNVERIFIED | Blocking |
| Logical-name mapping location | UNVERIFIED | Blocking |
| Audit device | Host bind `/opt/jason/infrastructure/openbao/audit` mounted at `/openbao/audit` | Audit enablement and status still require verification |
| Log path | Host bind `/opt/jason/infrastructure/openbao/logs` mounted at `/openbao/logs` | Verified |
| Seal status and unseal method | UNVERIFIED | Blocking |
| Backup unit | `/etc/systemd/system/jason-openbao-backup.service`; size `1169` bytes; SHA-256 `45df475a48c215fed26706e411f20b7039cf939fe68297e00129e179ea744a27` | File existence and integrity verified; execution behavior remains unverified |
| Backup schedule | `/etc/systemd/system/jason-openbao-backup.timer`; size `294` bytes; SHA-256 `d7a63a200a0dba3801b2fc4608c095bf4f91b51d4096b81ae69ca5fedf39d138` | File existence and integrity verified; active schedule remains unverified |
| Backup destination | UNVERIFIED | Blocking |
| Last successful backup | UNVERIFIED | Blocking |
| Last successful restore test | UNVERIFIED | Blocking |
| Health-check command | NOT IMPLEMENTED | Blocking |
| Secret-resolution contract test | NOT IMPLEMENTED | Blocking |
| Operational owner | UNVERIFIED | Blocking |
| Escalation contact | UNVERIFIED | Blocking |

## Logical secret mappings

| Logical name | Provider reference | Required fields | Status |
|---|---|---|---|
| `autotask.readonly` | UNVERIFIED | `username`, `secret`, `integration_code` | Blocking |
| `it_glue.readonly` | `secret/data/connectors/it-glue/production/read-only` | `api_key` | Path documented; deployment verification required |
| `datto_rmm.readonly` | UNVERIFIED | Provider-defined read-only fields | Blocking |

## Verified evidence

The following external evidence was collected by the governed OpenBao deployment verification command:

- JSON: `/home/al/Jason-Evidence/OpenBao/openbao-verification-20260805T133421Z.json`
- Markdown: `/home/al/Jason-Evidence/OpenBao/openbao-verification-20260805T133421Z.md`
- Collected at: `2026-08-05T13:34:42.257776+00:00`
- Host: `Jason`

The evidence confirmed the Docker runtime, container identity, image, loopback listener, configuration/data/audit/log mounts, and backup unit file hashes. It did not authenticate to OpenBao, resolve secrets, inspect secret values, modify services, or prove backup execution or restore capability.

## Readiness decision

The Jason pilot environment is **not approved for CAP-001 live Autotask reads** until this record is updated with the remaining verified operational facts and the INF-001 readiness gate passes.

The existing CAP-001 fixture, transport, validation, and `--check-only` tests remain valid. Only the live provider binding is blocked.

## Remaining verification requirements

The next governed changes must provide evidence for:

- TLS mode;
- exact authentication method;
- canonical `jason-secret` wrapper installation and contract;
- logical-name mapping location and Autotask read-only mapping;
- OpenBao health without exposing secret values;
- audit device enablement and status;
- seal status and unseal method;
- backup destination and active schedule;
- last successful backup;
- successful restore test;
- named operational owner and escalation path.

Evidence may contain paths, unit names, versions, timestamps, hashes, and redacted statuses. It must not contain tokens, passwords, unseal keys, recovery shares, or secret values.

## Change rule

Any change to the provider runtime, endpoint, wrapper, authentication method, mapping location, storage backend, backup process, or recovery method must update this record in the same governed change.
