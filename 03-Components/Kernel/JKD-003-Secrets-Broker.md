# JKD-003 — Secrets Broker

**Version:** 0.3
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
11. Production OpenBao provider connectors use provider-specific least-privilege AppRoles for runtime secret resolution unless the Architecture Authority explicitly approves a replacement design.
12. A shared persistent provider runtime token, shared orphan token, or provider-wide reusable bearer token is prohibited.
13. Provisioning authority and runtime resolution authority must remain separate. A provisioning login may create/update the approved secret record and AppRole configuration, but its administrative token must not become runtime state.
14. Runtime OpenBao service tokens must be short-lived, narrowly scoped, and explicitly revoked after the bounded secret read. The current production baseline is a five-minute maximum lifetime and two-use limit.
15. New provider integrations must reuse the canonical JKD-003 resolver and onboarding pattern before introducing provider-specific secret-authentication code.
16. A second production secret-authentication pattern requires documented business justification, security review, migration/retirement criteria, and normal governance approval before implementation.

## Production OpenBao identity invariant

For the current OpenBao deployment, the canonical production provider flow is:

```text
Provisioning ceremony
  ↓
OpenBao userpass administrative login
  ↓
Temporary administrative token
  ↓
Provider-specific read-only policy + AppRole + secret record
  ↓
Administrative token revoked

Authorized runtime connector
  ↓
Provider-specific protected RoleID + SecretID
  ↓
OpenBao AppRole login
  ↓
Short-lived provider-specific service token
  ↓
One allow-listed KV v2 read
  ↓
Service token revoked
```

The RoleID and SecretID are bootstrap/runtime identity artifacts and require restricted storage plus governed rotation. The service token is ephemeral and must not be written to disk.

`/etc/jason/openbao.token` is not a production provider runtime identity. A file such as `/etc/jason/openbao-provider.token` must not be introduced as a shared provider credential.

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
    autotask.readonly: secret/data/connectors/autotask/production/read-only
    datto_rmm.readonly: secret/data/connectors/datto-rmm/production/read-only
    it_glue.readonly: secret/data/connectors/it-glue/production/read-only
```

A different deployment may map the same logical names to Azure Key Vault secret names, AWS ARNs, or another platform without changing capability code.

## Security controls

- Redact values by type, not by string matching alone.
- Keep secret leases out of persisted case packages.
- Permit only named fields expected by the consuming adapter.
- Validate secret schema before use.
- Record access metadata without values.
- Enforce client and capability boundaries before resolution.
- Use least privilege and separate read-only runtime authority from write-capable provisioning authority.
- Use a provider-specific runtime identity rather than a shared provider identity.
- Keep service tokens ephemeral and revoke them after use.
- Protect RoleID and SecretID artifacts as root-owned bootstrap/runtime identity material.
- Support dual-secret rotation where the provider permits it.
- CI must enforce the production identity invariant and reject known persistent-token regressions.

## Initial logical secret contracts

### `autotask.readonly`

Expected fields:

- `username`
- `secret`
- `integration_code`

The Autotask connector discovers the appropriate REST API zone at runtime using the unauthenticated `zoneInformation` endpoint and the API username.

### `datto_rmm.readonly`

Approved provider path:

`secret/data/connectors/datto-rmm/production/read-only`

Expected fields:

- `api_url`
- `api_key`
- `api_secret`

Runtime policy and AppRole are provider-specific and read-only. The Datto bearer access token derived from these values is runtime-only and must not be persisted.

### `it_glue.readonly`

Approved provider path:

`secret/data/connectors/it-glue/production/read-only`

Expected fields:

- `api_key`

The secret must contain only the provider API key. The IT Glue API base URL is non-secret provider configuration and must not be stored in OpenBao.

## Provider onboarding definition of done

A new production provider is not complete until:

- a stable logical secret contract exists;
- a canonical provider secret path exists;
- exact allowed fields are documented and tested;
- a provider-specific read-only policy exists;
- a provider-specific AppRole exists;
- protected RoleID and SecretID storage plus rotation metadata exist;
- the canonical resolver can authenticate, read the allow-listed fields, and revoke its temporary token;
- credential-safe preflight succeeds without network or secret entry;
- CI enforces absence of the persistent-token regression;
- live provider validation runs only through the authorized connector path.

## Definition of Done

JKD-003 Version 0.3 is complete when:

- a provider-neutral protocol exists;
- an in-memory synthetic provider passes contract tests;
- at least one real provider adapter passes the same tests;
- production OpenBao providers conform to the AppRole runtime invariant;
- CAP-001 consumes only logical secret names;
- secret values are absent from audit, memory, exceptions, and test snapshots;
- switching providers requires configuration only;
- CI prevents reintroduction of persistent shared provider runtime tokens.
