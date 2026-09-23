# Governed Provider Secret Lifecycle

## Purpose

Project Jason separates provider-secret provisioning authority from normal runtime secret resolution. This document is the canonical production lifecycle for provider secrets. New providers must reuse this pattern unless the Jason Architecture Authority explicitly approves a replacement under JKD-003.

Operators and automation use one supported command surface:

```bash
python3 tools/provider_secret.py <action> <provider>
```

The low-level provisioning and KV helpers are implementation details. They are not separate operator workflows.

## Canonical production invariant

Production provider connectors use provider-specific OpenBao AppRoles for runtime secret resolution. A shared persistent provider runtime token is prohibited.

The invariant is:

1. provisioning/lifecycle administration uses the governed OpenBao `userpass` administrative identity only for the bounded ceremony;
2. the temporary administrative token is revoked when the lifecycle operation completes;
3. each provider credential class has its own least-privilege runtime policy and AppRole;
4. AppRole RoleID and SecretID artifacts are stored root-owned under `/opt/jason/bootstrap/secrets/openbao/<provider>-approle/`;
5. runtime AppRole login issues a short-lived service token with a five-minute maximum lifetime and two-use limit;
6. the runtime policy can read exactly the provider credential's own secret path and can `update` only `auth/token/revoke-self` so the ephemeral token can destroy itself;
7. the resolver reads exactly one approved provider secret record and revokes the service token immediately afterward;
8. provider credentials and temporary tokens never enter Git, chat, prompts, normal logs, evidence, or persistent runtime token files;
9. KV v2 create/update operations use compare-and-set (CAS), never blind overwrite;
10. lifecycle state transitions are explicit: create, update, verify, rotate-identity, deactivate, reactivate, and status.

Do not create `/etc/jason/openbao-provider.token`, a shared orphan token, or another persistent provider runtime token. Do not broaden `/etc/jason/openbao.token`; that file belongs to the historical contract-test boundary and is not the provider runtime identity.

## Canonical lifecycle commands

Credential-safe inspection:

```bash
python3 tools/provider_secret.py status datto_rmm --check-only
python3 tools/provider_secret.py create it_glue --check-only
python3 tools/provider_secret.py create autotask_write --check-only
```

Live operations run as root and prompt locally for the OpenBao administrative password when administrative authority is required:

```bash
sudo python3 tools/provider_secret.py status datto_rmm
sudo python3 tools/provider_secret.py create it_glue
sudo python3 tools/provider_secret.py create autotask_write
sudo python3 tools/provider_secret.py update datto_rmm
sudo python3 tools/provider_secret.py verify datto_rmm
sudo python3 tools/provider_secret.py rotate-identity datto_rmm
sudo python3 tools/provider_secret.py deactivate datto_rmm
sudo python3 tools/provider_secret.py reactivate datto_rmm
```

### `create`

Use only when no KV secret exists. The command:

1. authenticates the bounded administrative identity;
2. installs/reasserts the provider-specific runtime policy and AppRole;
3. creates protected RoleID/SecretID artifacts;
4. prompts locally for provider credential values;
5. writes KV v2 version 1 using CAS `0`;
6. clears entered values and revokes the administrative token.

If the secret already exists, `create` fails closed and instructs the operator to use `update`.

### `update`

Use for provider credential rotation or replacement. The command reads only KV metadata/current version, prompts for the replacement fields, and performs a CAS-guarded write. It never retrieves or prints the previous secret value.

If the secret does not exist, `update` fails closed and instructs the operator to use `create`.

### `verify`

`verify` uses the provider-specific AppRole and canonical JKD-003 resolver. It validates the allow-listed field contract without printing values. The short-lived runtime service token self-revokes in the normal resolver cleanup path.

### `rotate-identity`

This rotates the OpenBao AppRole SecretID without changing the provider API credential. The new SecretID is installed before the previous SecretID accessor is revoked. Provider KV data is not rewritten.

RoleID/SecretID material remains root-owned and mode `0600`. Rotation metadata is refreshed with a new 90-day review/expiry point.

### `deactivate`

Deactivation is intentionally reversible. It:

- revokes the current AppRole SecretID when possible;
- deletes the provider AppRole so new runtime logins fail closed;
- removes the local protected AppRole artifacts;
- preserves the encrypted KV v2 secret history;
- does not contact or deactivate the credential at the external provider.

Deactivation is **not** permanent secret destruction. Permanent provider-side credential revocation and irreversible KV destruction require a separate governed retirement procedure.

### `reactivate`

Reactivation requires an existing KV secret. It recreates the canonical provider-specific AppRole and new protected runtime identity without requiring the provider API credential to be re-entered.

If the KV secret no longer exists, reactivation fails closed and the operator must use `create`.

### `status`

Status reports metadata only: logical name, KV current version/presence, AppRole artifact completeness, runtime active/inactive state, and identity expiration metadata. It never reads or displays provider secret values.

## Runtime boundary

Runtime resolution uses `implementation/connectors/core/openbao_secrets.py` and provider-specific AppRole files. The resolver authenticates to `auth/approle/login`, reads the allow-listed KV v2 record, returns only approved fields to the authorized connector execution context, and calls `auth/token/revoke-self` in a `finally` path.

Runtime OpenBao policies contain only:

- `read` on the credential's exact secret path; and
- `update` on `auth/token/revoke-self`.

They must not include provider-secret `create`, `update`, `delete`, `sudo`, broad prefixes, or another provider credential's secret path. A provider credential that can perform external mutations still receives only **read** access to its own encrypted OpenBao record; external provider authority and OpenBao secret-store authority are separate concerns.

## Standard provider onboarding

A new provider credential class is not considered integrated with JKD-003 until all of the following are defined and tested:

- stable logical secret name;
- canonical OpenBao KV v2 path under an approved provider-specific production namespace;
- exact allow-listed secret fields;
- provider-specific least-privilege OpenBao policy name;
- provider-specific AppRole name;
- protected AppRole credential directory;
- short-lived service-token settings;
- resolver mapping and field contract;
- credential-safe lifecycle `--check-only` support;
- CI invariants preventing persistent-token or blind-write regressions;
- identity rotation metadata;
- deactivate/reactivate behavior;
- provider-side credential retirement criteria.

Adding a different secret authentication mechanism requires architecture review before implementation. Convenience is not sufficient justification for creating a second runtime secret pattern.

## Datto RMM contract

Logical secret: `datto_rmm.readonly`

Approved provider path:

`secret/data/connectors/datto-rmm/production/read-only`

Durable OpenBao fields:

- `api_url`
- `api_key`
- `api_secret`

Runtime identity:

- policy: `jason-datto-rmm-read`
- AppRole: `jason-datto-rmm-read`
- protected artifacts: `/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/`

The Datto bearer access token derived from these credentials is runtime-only and must never be persisted in OpenBao, Git, chat, normal logs, or evidence.

## Datto EDR/AV contract

Logical secret: `datto_edr.readonly`

Approved provider path:

`secret/data/connectors/datto-edr/production/read-only`

Durable OpenBao fields:

- `api_url`
- `api_token`

Runtime identity:

- policy: `jason-datto-edr-read`
- AppRole: `jason-datto-edr-read`
- protected artifacts: `/opt/jason/bootstrap/secrets/openbao/datto-edr-read-approle/`

The provider-generated Datto EDR API token is durable only inside OpenBao. The
runtime receives it only after a short-lived AppRole login and must not print,
persist, log, or copy it into evidence. The tenant API currently authenticates
this token through LoopBack's `access_token` request parameter. Jason audit
records contain only the provider operation/path and never the token-bearing
query string.

The Datto EDR runtime policy is read-only at the Jason capability layer.
Provider mutation routes such as scan, quarantine, restore, isolation, archive,
and response are not registered by the read connector even if the associated
provider user/token could technically access them.

## IT Glue contract

Logical secret: `it_glue.readonly`

Approved provider path:

`secret/data/connectors/it-glue/production/read-only`

Durable OpenBao field:

- `api_key`

Runtime identity:

- policy: `jason-itglue-read`
- AppRole: `jason-itglue-read`
- protected artifacts: `/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/`

IT Glue uses the same production AppRole lifecycle and no longer requires a provider-specific secret-management procedure.

## Autotask governed write contract

Lifecycle provider key: `autotask_write`

Logical secret: `autotask.write`

Approved provider path:

`secret/data/connectors/autotask/production/write`

Durable OpenBao fields:

- `username`
- `secret`
- `integration_code`

Runtime identity:

- policy: `jason-autotask-write-secret-read`
- AppRole: `jason-autotask-write-secret-read`
- protected artifacts: `/opt/jason/bootstrap/secrets/openbao/autotask-write-approle/`

The word `write` describes the external Autotask execution credential's potential provider authority; the OpenBao runtime identity still has only read access to this one encrypted secret record plus self-revocation.

This credential is intentionally separate from `autotask.readonly`. It is reserved for the governed Ticket/TicketNote mutation path, must be backed by a dedicated minimum-permission Autotask API-only user/security profile, and must never become a general read credential. Provider-native requester impersonation remains mandatory for every mutation, so the external execution identity does not replace requester authority.

Provisioning this secret does not activate Autotask writes. Connector source, Central Orchestrator authorization, runtime write enablement, requester impersonation acceptance, and explicit production activation remain separate gates.

## Kyocera Fleet Services contract

Logical secret: `kyocera_kfs.readonly`

Approved provider path:

`secret/data/connectors/kyocera-kfs/production/read-only`

Durable OpenBao fields:

- `api_url`
- `access_id`
- `access_password`
- `request_from`
- `request_to`
- `authorization`
- `kfs_username`
- `kfs_password`
- `headers_json`
- `operations_json`

Runtime identity:

- policy: `jason-kyocera-kfs-read`
- AppRole: `jason-kyocera-kfs-read`
- protected artifacts: `/opt/jason/bootstrap/secrets/openbao/kyocera-kfs-read-approle/`

The production API host is restricted to `https://api.kyods.com`. KFS is read-only in this foundation and live selection also requires `JASON_KFS_ENABLED=true`.

## UniView / Backup.net Public API contract

Logical secret: `backup_net.readonly`

Approved provider path:

`secret/data/connectors/backup-net/production/read-only`

Durable OpenBao fields:

- `client_id`
- `client_secret`

Runtime identity:

- policy: `jason-backup-net-read`
- AppRole: `jason-backup-net-read`
- protected artifacts: `/opt/jason/bootstrap/secrets/openbao/backup-net-read-approle/`

Provision with the normal lifecycle command:

`python3 tools/provider_secret.py create backup_net`

The credential is created in UniView under **Settings -> Public APIs -> New** and is used only with the OAuth 2.0 client-credentials flow. The connector fixes authentication to `https://login.backup.net/connect/token` and API reads to `https://public-api.backup.net`; those hosts are not secret-configurable.

Live selection also requires `JASON_BACKUP_NET_ENABLED=true` and a validated Jason client-boundary record mapping the exact Autotask company ID to the Backup.net customer UUID. Provider `customer_id` is never accepted from the caller. The connector injects the mapped UUID and verifies every returned record proves the same customer.

For the controlled acceptance case, Autotask company search independently resolved **Deborah Gittens Virtuol Designs LLC** to company ID **1627**. Ticket `T20260922.0063` itself currently reports `companyID=0`, so the ticket field must not be used as the Backup.net boundary source.

## Safety and failure rules

- Never paste provider credentials into chat, Git, command arguments, normal logs, or evidence.
- Never create a persistent shared provider runtime token.
- Never use the historical contract-test token as a provider identity.
- Never give a provider runtime policy write access to provider KV data.
- Never expose another provider credential's secret path through the same AppRole policy.
- Never silently fall back to environment variables or unmanaged files.
- Never blind-overwrite KV v2 data; use CAS.
- Never treat `deactivate` as provider-side API-key revocation or irreversible secret destruction.
- A failed lifecycle or resolution operation must fail closed without exposing credential values.
- Provider network validation occurs only after secret provisioning and normal JKD-001, governance, and Central Orchestrator checks.

## CI invariants

The provider-secret workflow must fail when a change:

- reintroduces a persistent/shared provider runtime token;
- introduces orphan or periodic provider runtime tokens;
- bypasses KV v2 CAS for operator create/update;
- removes `auth/token/revoke-self` from the canonical runtime policy;
- merges provider secret paths into a shared AppRole;
- removes lifecycle check-only coverage;
- changes the canonical lifecycle documentation without running the provider-secret tests.

The goal is operationally simple: adding the next provider credential should require defining its logical contract and then using the same lifecycle command, not rediscovering OpenBao behavior.
