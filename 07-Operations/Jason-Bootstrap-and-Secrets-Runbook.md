# Jason Bootstrap and Secrets-Management Runbook

## Decision

Jason shall use a governed bootstrap process and an external secrets service. The current pilot default is **OpenBao**, an open-source, self-hosted secrets and encryption management system.

Jason application code, GitHub, configuration files, container images, logs, test fixtures, and documentation shall never contain live credentials.

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

The pilot listener is bound to `127.0.0.1:8200`. TLS is disabled only because the listener is loopback-only. Any remote, multi-host, or production deployment requires TLS, a trusted certificate, backup and recovery design, monitored audit logging, and an approved unseal method.

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

## Secret namespace

Initial logical paths:

```text
secret/jason/pilot/autotask
secret/jason/pilot/datto-rmm
secret/jason/pilot/it-glue
secret/jason/pilot/database
```

Each integration receives its own policy and application identity. CAP-001 receives read-only access only to the secret paths needed by its configured providers.

## Autotask credential fields

The Autotask secret should contain fields such as:

```text
username
secret
integration_code
zone_url
```

The values are entered only after the read-only API user and security level have been approved. They must not be passed as command-line arguments because command lines may be logged or exposed through process inspection.

## Failure behavior

If OpenBao is unavailable, sealed, unauthorized, or returns an unexpected secret version, Jason must fail closed. It must not fall back to environment files containing live production credentials.

A local `.env` file may be used only for non-sensitive development settings. Live secrets remain in OpenBao.

## Future profiles

The bootstrap framework may later add:

- `development`: disposable local dependencies and synthetic credentials only;
- `pilot`: single-host, loopback-bound services and sanitized or read-only integrations;
- `production`: TLS, high availability, durable backups, monitored audit logs, formal recovery, and change approval.

Production installation must not be silently inferred from the host. It requires an explicit approved profile and preflight review.
