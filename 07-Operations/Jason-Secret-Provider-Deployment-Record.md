# Jason Secret Provider Deployment Record

**Environment:** Jason pilot host
**Profile:** Pilot
**Status:** BLOCKED — deployment facts require verification
**Owner:** Jason Architecture Authority
**Last verified:** Not yet verified

## Purpose

This is the canonical operational record for the secret provider used by the Jason pilot environment. Capabilities and operator runbooks must reference this record instead of asking an operator to discover infrastructure details during execution.

`UNVERIFIED` means the repository does not yet contain sufficient approved evidence. It is a blocking state, not an invitation to guess.

## Deployment facts

| Field | Verified value | Status |
|---|---|---|
| Selected provider | OpenBao | Documented architectural decision |
| Runtime type | UNVERIFIED | Blocking |
| Service or container name | UNVERIFIED | Blocking |
| Listener or endpoint | Expected pilot default: `127.0.0.1:8200` | Must be verified against deployed configuration |
| TLS mode | Expected pilot default: loopback-only without TLS | Must be verified against deployed configuration |
| Canonical wrapper | `/usr/local/bin/jason-secret` | NOT IMPLEMENTED |
| OpenBao executable path | UNVERIFIED | Blocking |
| OpenBao configuration path | UNVERIFIED | Blocking |
| Storage path or backend | UNVERIFIED | Blocking |
| Authentication method | UNVERIFIED | Blocking |
| Logical-name mapping location | UNVERIFIED | Blocking |
| Audit device | UNVERIFIED | Blocking |
| Seal status and unseal method | UNVERIFIED | Blocking |
| Backup unit | `jason-openbao-backup.service` observed on host | Configuration not yet verified |
| Backup schedule | `jason-openbao-backup.timer` observed on host | Configuration not yet verified |
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

## Readiness decision

The Jason pilot environment is **not approved for CAP-001 live Autotask reads** until this record is updated with verified deployment facts and the INF-001 readiness gate passes.

The existing CAP-001 fixture, transport, validation, and `--check-only` tests remain valid. Only the live provider binding is blocked.

## Verification evidence required

The verification change must include evidence for:

- exact runtime and version;
- exact service/container configuration;
- exact wrapper installation path;
- provider health without exposing secret values;
- logical-name mapping;
- authentication method;
- audit status;
- backup destination and schedule;
- successful restore test;
- named owner and escalation path.

Evidence may contain paths, unit names, versions, timestamps, hashes, and redacted statuses. It must not contain tokens, passwords, unseal keys, recovery shares, or secret values.

## Change rule

Any change to the provider runtime, endpoint, wrapper, authentication method, mapping location, storage backend, backup process, or recovery method must update this record in the same governed change.
