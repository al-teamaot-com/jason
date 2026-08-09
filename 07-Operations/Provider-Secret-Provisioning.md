# Governed Provider Secret Provisioning

## Purpose

Project Jason separates provider-secret provisioning authority from normal runtime secret resolution. Runtime identities remain read-only. Provisioning is an explicit, root-governed operation that uses a temporary or separately governed OpenBao administrative identity and never prints provider credential values.

## Runtime boundary

The runtime policy is `jason-provider-readonly`. It grants only `read` capability to approved provider secret paths:

- `secret/data/jason/providers/datto_rmm/readonly`
- `secret/data/jason/providers/it_glue/readonly`

The runtime token is stored at `/etc/jason/openbao-provider.token` with mode `0600` and must not have provider-secret write authority.

## Provisioning boundary

`tools/provider_secret_provision.py` requires root for live provisioning and requires a protected `--admin-token-file`. The administrative token is not copied into Jason runtime state and is used only to:

1. install/update the narrow read-only runtime policy;
2. create the provider runtime orphan token if it does not already exist;
3. write one approved provider record;
4. update the logical field mappings.

The tool does not print provider credential values. Sensitive fields use hidden prompts.

## Datto RMM contract

Durable OpenBao record fields:

- `api_url`
- `api_key`
- `api_secret`

The Datto bearer access token is runtime-only and must never be persisted in OpenBao, Git, chat, normal logs, or evidence.

Because the existing `jason-secret` wrapper intentionally resolves one value at a time, the durable Datto record is exposed through field-scoped logical mappings:

- `datto_rmm.readonly.api_url`
- `datto_rmm.readonly.api_key`
- `datto_rmm.readonly.api_secret`

This preserves the value-only stdout contract while keeping one structured provider record in OpenBao.

## IT Glue contract

Durable OpenBao record field:

- `api_key`

Logical mapping:

- `it_glue.readonly.api_key`

## Safety rules

- Never broaden `/etc/jason/openbao.token` or the historical contract-test policy for provider writes.
- Never paste provider credentials into chat, Git, command arguments, normal logs, or evidence.
- Administrative provisioning material must be supplied through a protected file with owner-only permissions.
- The runtime identity must remain read-only.
- Provider network validation occurs only after secret provisioning and normal JKD-001/governance/Central Orchestrator checks.
- A failed provisioning operation must not expose credential values.

## Check-only validation

Run:

```bash
python3 tools/provider_secret_provision.py datto_rmm --check-only
```

The result must report `network_contacted=false` and `secret_entered=false`.
