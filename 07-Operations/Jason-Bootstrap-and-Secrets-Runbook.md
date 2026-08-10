# Jason Bootstrap and Secrets-Management Runbook

## Decision

Jason shall use a governed bootstrap process and an external secrets service. The current pilot default is **OpenBao**, an open-source, self-hosted secrets and encryption management system.

Jason application code, GitHub, configuration files, container images, logs, test fixtures, chat, and documentation shall never contain live credentials.

## Canonical deployment record

Architecture and bootstrap intentions are not sufficient operational documentation.

Every deployed Jason environment must maintain a concrete, verified secret-provider deployment record at:

`07-Operations/Jason-Secret-Provider-Deployment-Record.md`

That record is the source of truth for the actual runtime type, service or container name, listener, TLS mode, executable and wrapper paths, configuration, storage, authentication, logical-name mappings, audit status, backup and restore status, ownership, and health commands.

A capability or runbook must not ask an operator to discover or invent any of those values. If a required value is absent or marked `UNVERIFIED`, dependent live execution is blocked until the deployment record is completed through a governed change.

The presence of a service file, backup timer, container, process, configuration fragment, RoleID file, or SecretID file does not by itself prove that the Secrets Broker is operationally ready.

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

Each provider receives its own policy and runtime identity. Provider runtimes receive read access only to the one logical secret required by that provider plus the minimum token self-revocation capability.

## Canonical production provider runtime

Production provider integrations use **provider-specific OpenBao AppRoles through JKD-003**. This is the canonical runtime contract for Autotask, IT Glue, and Datto RMM on the Jason pilot host.

The runtime sequence is:

1. read the provider-specific RoleID and SecretID from the protected host bootstrap directory;
2. authenticate to OpenBao through AppRole;
3. receive a short-lived service token;
4. read exactly one allow-listed KV v2 provider secret;
5. revoke the temporary token through `auth/token/revoke-self`;
6. keep provider access tokens, OAuth bearer tokens, and secret values runtime-only.

Provider runtime AppRole artifacts are stored under:

```text
/opt/jason/bootstrap/secrets/openbao/<provider>-read-approle/role-id
/opt/jason/bootstrap/secrets/openbao/<provider>-read-approle/secret-id
```

The concrete paths, owners, modes, policies, and logical mappings are maintained in the deployment record.

Shared persistent provider runtime tokens are prohibited.

## Historical `jason-secret` wrapper distinction

`/usr/local/bin/jason-secret` remains a governed commissioning/general secret-wrapper boundary, but its historical token-file health and contract-test path is **not the canonical production provider runtime**.

Commands such as:

```text
jason-secret --health
jason-secret --contract-test <logical-name>
```

may return:

```text
DENIED: OpenBao token file is not configured.
```

when the production provider-specific AppRole runtime is healthy.

Operators must **not** create, restore, copy, broaden, or persist a provider runtime token merely to make the historical wrapper health check pass. Production provider readiness must instead be validated through the provider-specific AppRole resolver, its bounded contract tests, and a governed provider live-read preflight.

The wrapper remains useful only where a runbook explicitly identifies the wrapper contract as the intended boundary. Runbooks must not assume wrapper health proves production provider readiness.

## Direct resolver validation contract

`OpenBaoSecretResolver.resolve()` requires both:

- the governed logical secret name; and
- a `ConnectorContext` with a non-empty correlation ID and the active organization/capability context.

Direct validation examples must use the actual contract. Validation output may report success/failure and approved field names, but must never print RoleIDs, SecretIDs, temporary OpenBao tokens, provider credentials, OAuth bearer tokens, or resolved values.

## Host Python validation environment

Host-side development and operational validation uses a project-local virtual environment. System Python must not be assumed to contain Jason test dependencies.

Canonical bootstrap from the repository root:

```bash
cd ~/projects/jason
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e './implementation[dev]'
.venv/bin/python --version
.venv/bin/python -m pytest --version
```

Reusing `.venv` is permitted when it was built from the current checkout and remains healthy.

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

Before a production provider capability performs a live read, verify all of the following from repository-controlled documentation and automated checks:

1. The canonical deployment record exists and has no blocking `UNVERIFIED` fields required by the operation.
2. OpenBao is reachable at the documented listener, initialized, unsealed, and active.
3. The provider-specific RoleID and SecretID artifacts exist at the documented protected paths.
4. The canonical AppRole resolver tests pass in the project `.venv`.
5. The requested logical secret mapping exists and resolves through the provider-specific AppRole without printing values.
6. The provider policy permits only the provider secret read plus required self-revocation behavior.
7. Provider authentication and capability policy are approved.
8. Audit logging is enabled or covered by an approved, time-bounded exception.
9. Backup and restore evidence is current for self-hosted providers.
10. The dependent capability uses logical secret names only.
11. The provider live-read tool performs a credential-safe preflight before network contact.
12. The operator command contains exact values from approved configuration and does not require infrastructure discovery.

## Failure behavior

If OpenBao is unavailable, sealed, unauthorized, undocumented, or returns an unexpected secret version, Jason must fail closed. It must not fall back to environment files containing live production credentials.

If a provider AppRole cannot authenticate, cannot read exactly its approved secret, or cannot revoke its temporary token, provider execution is blocked.

If deployment facts are absent, Jason must identify the missing deployment-record fields and stop. It must not ask the operator to guess.

A local `.env` file may be used only for non-sensitive development settings. Live secrets remain in OpenBao.

## 2026-08-10 host validation lesson

The first physical host validation exposed an important operational ambiguity: the historical wrapper emitted `DENIED: OpenBao token file is not configured` while the production provider AppRole runtime was healthy. The investigation also found that system Python did not include `pytest` and that direct resolver examples must pass `ConnectorContext`.

These are now documented as explicit contracts rather than tribal knowledge. Future host validation must begin from this runbook and the deployment record instead of rediscovering those requirements interactively.

## Future profiles

The bootstrap framework may later add:

- `development`: disposable local dependencies and synthetic credentials only;
- `pilot`: single-host, loopback-bound services and sanitized or read-only integrations;
- `production`: TLS, high availability, durable backups, monitored audit logs, formal recovery, and change approval.

Production installation must not be silently inferred from the host. It requires an explicit approved profile and preflight review.
