# Governed Provider Secret Provisioning

## Purpose

Project Jason separates provider-secret provisioning authority from normal runtime secret resolution. This document is the canonical production onboarding pattern for provider secrets. New providers must reuse this pattern unless the Jason Architecture Authority explicitly approves a replacement under JKD-003.

## Canonical production invariant

Production provider connectors use provider-specific OpenBao AppRoles for runtime secret resolution. A shared persistent provider runtime token is prohibited.

The invariant is:

1. provisioning uses the governed OpenBao `userpass` administrative identity only for the provisioning ceremony;
2. the temporary administrative token is revoked when provisioning completes;
3. each provider has its own least-privilege read-only policy and AppRole;
4. AppRole RoleID and SecretID artifacts are stored root-owned under `/opt/jason/bootstrap/secrets/openbao/<provider>-read-approle/`;
5. runtime AppRole login issues a short-lived service token with a five-minute maximum lifetime and two-use limit;
6. the resolver reads exactly one approved provider secret record and revokes the service token immediately afterward;
7. provider credentials and temporary tokens never enter Git, chat, prompts, normal logs, evidence, or persistent runtime token files.

Do not create `/etc/jason/openbao-provider.token`, a shared orphan token, or another persistent provider runtime token. Do not broaden `/etc/jason/openbao.token`; that file belongs to the historical contract-test boundary and is not the provider runtime identity.

## Provisioning boundary

`tools/provider_secret_provision.py` is the standard production provisioning utility. Live provisioning must run as root. It prompts locally for the OpenBao administrative password and provider credential values using hidden input for sensitive fields.

The provisioning sequence is:

1. authenticate `al-admin` through OpenBao `userpass`;
2. obtain a temporary administrative token;
3. install or verify the provider-specific read-only policy;
4. configure the provider-specific AppRole with five-minute/two-use runtime tokens;
5. create protected AppRole artifacts if they do not already exist;
6. write the approved provider secret record;
7. clear entered values from process variables;
8. revoke the temporary administrative token.

The administrative token is never persisted as a provider runtime credential.

## Runtime boundary

Runtime resolution uses `implementation/connectors/core/openbao_secrets.py` and the provider-specific AppRole files. The resolver authenticates to `auth/approle/login`, reads the allow-listed KV v2 record, returns only the approved fields to the authorized connector execution context, and calls `auth/token/revoke-self` in a `finally` path.

Runtime policies contain only `read` for the provider's own secret path. They must not include `create`, `update`, `delete`, `sudo`, broad prefixes, or another provider's path.

## Standard provider onboarding

A new provider is not considered integrated with JKD-003 until all of the following are defined and tested:

- stable logical secret name;
- canonical OpenBao KV v2 path under `secret/data/connectors/<provider>/production/read-only`;
- exact allow-listed secret fields;
- provider-specific read-only policy name;
- provider-specific AppRole name;
- protected AppRole credential directory;
- short-lived service-token settings;
- resolver mapping and field contract;
- credential-safe `--check-only` preflight;
- CI invariants preventing persistent-token regression;
- rotation metadata and retirement criteria.

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

IT Glue already uses this production AppRole pattern and remains the reference alongside Autotask.

## Safety rules

- Never paste provider credentials into chat, Git, command arguments, normal logs, or evidence.
- Never create a persistent shared provider runtime token.
- Never use the historical contract-test token as a provider identity.
- Never give a provider runtime policy write capability.
- Never expose another provider's secret path through the same AppRole policy.
- Never silently fall back to environment variables or unmanaged files.
- Provider network validation occurs only after secret provisioning and normal JKD-001, governance, and Central Orchestrator checks.
- A failed provisioning or resolution operation must fail closed without exposing credential values.

## Credential-safe validation

Before entering a real credential, run:

```bash
python3 tools/provider_secret_provision.py datto_rmm --check-only
```

The result must report:

- `runtime_authentication=approle`;
- `runtime_token_persisted=false`;
- `network_contacted=false`;
- `secret_entered=false`.

CI also validates the AppRole runtime invariant and rejects the known persistent-token regression pattern.
