# Jason Bootstrap and Secrets-Management Runbook

## Decision

Jason shall use a governed bootstrap process and an external secrets service. The current pilot default is **OpenBao**, an open-source, self-hosted secrets and encryption management system.

Jason application code, GitHub, configuration files, container images, logs, test fixtures, and documentation shall never contain live credentials.

## Canonical deployment record

Architecture and bootstrap intentions are not sufficient operational documentation.

Every deployed Jason environment must maintain a concrete, verified secret-provider deployment record at:

`07-Operations/Jason-Secret-Provider-Deployment-Record.md`

That record is the source of truth for the actual runtime type, service or container name, listener, TLS mode, executable and wrapper paths, configuration, storage, authentication, logical-name mappings, audit status, backup and restore status, ownership, and health commands.

A capability or runbook must not ask an operator to discover or invent any of those values. If a required value is absent or marked `UNVERIFIED`, dependent live execution is blocked until the deployment record is completed through a governed change.

The presence of a service file, backup timer, container, process, or configuration fragment does not by itself prove that the Secrets Broker is operationally ready.

## Bootstrap behavior

`bootstrap/bootstrap.sh` is idempotent and supports three explicit modes:

- `--check`: inspect prerequisites without changing the host.
- `--install-missing`: install approved Ubuntu/Debian prerequisites. This requires explicit operator intent and elevated privileges.
- `--start`: validate prerequisites and start the managed OpenBao container.

The bootstrap must never:

- initialize OpenBao automatically;
- auto-unseal OpenBao with material stored beside the service;
- generate or display production root tokens in unattended output;
- write vendor credentials;
- weaken host security to make installation succeed;
- expose OpenBao beyond loopback in the pilot profile.

## Pilot commands

```bash
./bootstrap/bootstrap.sh --check
sudo ./bootstrap/bootstrap.sh --install-missing
./bootstrap/bootstrap.sh --start
```

The intended pilot listener is `127.0.0.1:8200`. TLS may be disabled only when the verified deployed listener is loopback-only. The actual value must be recorded in the canonical deployment record. Any remote, multi-host, or production deployment requires TLS, a trusted certificate, backup and recovery design, monitored audit logging, and an approved unseal method.

## Initialization ceremony

Initialization is a separate human-authorized operation. At least two authorized AOT administrators should participate.

Required controls:

1. Confirm the host, storage, backups, firewall, and time synchronization.
2. Initialize with an approved recovery/share design.
3. Distribute recovery material to separate authorized custodians.
4. Store no recovery share or initial root token in the Jason repository, shell history, ticket notes, chat, or ordinary password files.
5. Enable an audit device before adding vendor credentials.
6. Revoke the initial root token after administrative policies and named administrator access are configured.
7. Record the ceremony and approvals without recording the secret values.
8. Update the canonical deployment record with verified non-secret facts and evidence references.

## Secret namespace

Capabilities use logical secret names rather than provider paths:

```text
autotask.readonly
datto_rmm.readonly
it_glue.readonly
```

Provider-specific paths are maintained only in the approved Secrets Broker mapping and the canonical deployment record where appropriate.

Each integration receives its own policy and application identity. CAP-001 receives read-only access only to the logical secrets needed by its configured providers.

## Canonical secret command

The intended operator and connector interface is:

```text
jason-secret <logical-secret-name>
```

The approved executable path must be recorded in the canonical deployment record. Until that path is verified, installed, and contract-tested, provider-dependent live operations remain blocked.

A runbook must never prompt for an "approved secret command path" or other infrastructure value that should already exist in the deployment record.

## Autotask credential fields

The `autotask.readonly` secret contract contains:

```text
username
secret
integration_code
```

Autotask zone discovery occurs at runtime from the API username. A static `zone_url` is not part of the canonical secret contract unless a future approved contract version explicitly adds it.

The values are entered only after the read-only API user and security level have been approved. They must not be passed as command-line arguments because command lines may be logged or exposed through process inspection.

## Readiness verification

Before a capability performs a live provider read, verify all of the following from repository-controlled documentation and automated checks:

1. The canonical deployment record exists and has no blocking `UNVERIFIED` fields required by the operation.
2. The canonical secret wrapper exists at the documented path.
3. A no-value health check succeeds.
4. The requested logical secret mapping exists.
5. Provider authentication and policy are approved.
6. Audit logging is enabled or covered by an approved, time-bounded exception.
7. Backup and restore evidence is current for self-hosted providers.
8. The dependent capability uses logical secret names only.
9. The operator command contains exact values from approved configuration and does not require infrastructure discovery.

## Failure behavior

If OpenBao is unavailable, sealed, unauthorized, undocumented, or returns an unexpected secret version, Jason must fail closed. It must not fall back to environment files containing live production credentials.

If deployment facts are absent, Jason must identify the missing deployment-record fields and stop. It must not ask the operator to guess.

A local `.env` file may be used only for non-sensitive development settings. Live secrets remain in OpenBao.

## Future profiles

The bootstrap framework may later add:

- `development`: disposable local dependencies and synthetic credentials only;
- `pilot`: single-host, loopback-bound services and sanitized or read-only integrations;
- `production`: TLS, high availability, durable backups, monitored audit logs, formal recovery, and change approval.

Production installation must not be silently inferred from the host. It requires an explicit approved profile and preflight review.
