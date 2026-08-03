# JKD-003 — Secrets Broker

**Version:** 0.2
**Status:** Draft for governed review
**Owner:** Jason Architecture Authority

## Purpose

The Secrets Broker gives Jason a provider-neutral way to obtain narrowly scoped secret material at runtime without embedding vendor-specific vault behavior in capabilities, orchestrators, or provider adapters.

OpenBao, HashiCorp Vault, Azure Key Vault, AWS Secrets Manager, 1Password Connect, CyberArk, Kubernetes Secrets, and future platforms are implementations behind this boundary. None is part of Jason's constitutional architecture.

## Architectural boundary

Jason maintains two independent chains that intersect only at the authorized connector execution context.

### Authority chain

```text
Requester
  ↓
Orchestrator
  ↓
Identity and authority evaluation
  ↓
Policy and approval
  ↓
Authorized connector invocation
```

### Secret chain

```text
Authorized connector execution context
  ↓
Secrets Broker
  ↓
Configured secret provider
  ↓
Least-privilege credential
```

The orchestrator authorizes work but must not retrieve, possess, transmit, log, or expose secret values.

The Secrets Broker resolves secret material but must not authorize business operations.

A connector may use secret material only while executing an already authorized operation.

## Governing rules

1. Capabilities request a named secret purpose, never a provider path.
2. The broker resolves the request through configuration and policy.
3. Secrets are returned only to the authorized execution context.
4. Secret values must not enter logs, audit payloads, prompts, case memory, exceptions, or telemetry.
5. Provider authentication must use workload identity or short-lived credentials when available.
6. Static bootstrap credentials require explicit approval, restricted storage, rotation, and retirement criteria.
7. Failure is closed. Jason must not silently fall back to environment variables, files, or another provider.
8. Provider selection is deployment configuration, not capability logic.
9. A provider may be replaced without modifying CAP-001 or any other capability contract.
10. Provider-specific features are optional optimizations and may not become required by the broker contract.

## Canonical request

A secret request contains:

- `secret_name`: stable Jason logical name, such as `autotask.readonly`
- `purpose`: operation requiring the secret
- `execution_context_id`
- `requester_id`
- `client_id` when client scope applies
- `capability`
- `minimum_version` when a version floor is required
- `correlation_id`

The request never contains a vault path, token, password, or provider-specific identifier.

## Canonical response

A successful resolution returns a short-lived secret lease object containing:

- logical secret name
- opaque value mapping
- provider-neutral version identifier
- issued time
- expiry time when applicable
- renewable flag
- lease identifier when applicable
- sensitivity classification

The response must not expose the provider's internal path to capability code.

## Required provider operations

Every provider adapter implements:

- `health()`
- `resolve(request)`
- `renew(lease)` when supported
- `revoke(lease)` when supported
- `metadata(secret_name)` without returning secret values

Unsupported optional operations must return an explicit `not_supported` result rather than silently succeeding.

## Logical-name mapping

Deployment configuration maps logical names to provider-specific references.

Example:

```yaml
secrets:
  provider: openbao
  mappings:
    autotask.readonly: kv/data/jason/providers/autotask/readonly
    datto_rmm.readonly: kv/data/jason/providers/datto-rmm/readonly
```

A different deployment may map the same logical names to Azure Key Vault secret names, AWS ARNs, or another platform without changing Jason code.

## Security controls

- Redact values by type, not by string matching alone.
- Keep secret leases out of persisted case packages.
- Permit only named fields expected by the consuming adapter.
- Validate secret schema before use.
- Record access metadata without values.
- Enforce client and capability boundaries before resolution.
- Use least privilege and separate read-only from write-capable credentials.
- Support dual-secret rotation where the provider permits it.

## Initial logical secret contracts

### `autotask.readonly`

Expected fields:

- `username`
- `secret`
- `integration_code`

The Autotask connector discovers the appropriate REST API zone at runtime
using the unauthenticated `zoneInformation` endpoint and the API username.

### `datto_rmm.readonly`

Expected fields:

- provider-defined read-only API identity fields
- base URL or account endpoint when required

### `it_glue.readonly`

Approved provider path:

`secret/data/connectors/it-glue/production/read-only`

Expected fields:

- `api_key`

The secret must contain only the provider API key.

The IT Glue API base URL is non-secret provider configuration and
must not be stored in OpenBao.

## Definition of Done

JKD-003 Version 0.1 is complete when:

- a provider-neutral protocol exists;
- an in-memory synthetic provider passes contract tests;
- at least one real provider adapter passes the same tests;
- CAP-001 consumes only logical secret names;
- secret values are absent from audit, memory, exceptions, and test snapshots;
- switching providers requires configuration only.
