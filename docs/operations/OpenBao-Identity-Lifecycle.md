# Governed OpenBao Provider Identity Lifecycle

## Purpose

This control lets Jason recover provider-specific OpenBao AppRole identities without changing provider API credentials and without granting arbitrary OpenBao administration to the runtime.

It covers the current production recovery profiles:

- `autotask_read` — the legacy Autotask read AppRole staged into the non-root runtime credential area;
- `dnsfilter` — the DNSFilter read AppRole mounted from the production runtime-secret area.

## Authority separation

The lifecycle path has three distinct authorities:

1. **Provider runtime identity** — existing provider-specific RoleID/SecretID used only to resolve that provider's secret.
2. **Identity-lifecycle authority** — a dedicated least-privilege AppRole that may create, look up, and revoke SecretIDs for only the exact discovered provider AppRoles. It cannot read or write provider KV records.
3. **One-time bootstrap authority** — an OpenBao administrative identity used only to discover the exact provider role names, create the lifecycle ACL/AppRole, and then retire the bootstrap credential.

The lifecycle policy contains only exact `auth/approle/role/<role>/secret-id`, `secret-id/lookup`, `secret-id-accessor/destroy`, and `auth/token/revoke-self` paths. It contains no `secret/data/...` or KV write capability.

## One-time bootstrap

Preferred operator bootstrap remains the canonical local administrative login:

```bash
sudo python3 tools/openbao_identity_lifecycle.py bootstrap
```

For a production recovery where terminal access is unavailable, the installed root worker also supports a tightly bounded `bootstrap_from_init` request. That path is permitted only when:

- the request is owned by the Jason host operator and mode-restricted;
- the request is bound to the exact `/opt/jason/current` source SHA;
- the same exact release record is `production_control_core` and contains the lifecycle implementation files;
- the release has authenticated Teams Owner approval whose candidate SHA matches the request;
- the protected initialization artifact is root-owned and mode `0600`;
- the protected initialization artifact still contains a usable initial administrative token.

The protected token never enters request/result JSON, logs, evidence, prompts, or chat. On successful lifecycle bootstrap the initial token is revoked, then removed from the protected initialization artifact. If it is absent or unusable and the lifecycle role is not already established, bootstrap fails closed.

Installed request command:

```bash
jason-openbao-identity-bootstrap
```

The command itself does not contain or accept a password/token. It only creates the bounded root-worker request. The root worker independently validates the Teams-approved release record before reading protected bootstrap material.

## Routine rotation

After bootstrap, a bounded provider rotation is requested with:

```bash
jason-openbao-identity-rotate autotask_read --reason "<incident/recovery reason>"
jason-openbao-identity-rotate dnsfilter --reason "<incident/recovery reason>"
```

Rotation sequence:

1. validate exact current production source SHA;
2. authenticate with the dedicated lifecycle AppRole;
3. look up the existing SecretID accessor without exposing the SecretID;
4. create a replacement SecretID for the exact approved provider AppRole;
5. atomically install the replacement protected SecretID;
6. update the Autotask staged runtime copy when applicable;
7. revoke the previous SecretID accessor;
8. revoke the short-lived lifecycle service token;
9. write sanitized evidence only.

The replacement is installed before the previous identity is revoked. Provider API credentials and OpenBao KV data are unchanged.

## Runtime refresh

Current provider credentials are individual Docker bind-mounted files. Atomic replacement of a host SecretID can leave a running container bound to the previous inode. Every successful identity rotation therefore reports `runtime_refresh_required=true`.

Rotation alone does not restart `jason-runtime`. Runtime recreation remains a separately governed production action/release step. After recreation, provider-backed verification must prove the new identity works before the incident is closed.

## Root worker boundary

The root worker accepts only the fixed request fields:

- request ID;
- action (`rotate` or the Teams-bound one-time bootstrap action);
- approved provider/sentinel;
- bounded reason;
- exact current source SHA;
- release ID.

The caller cannot supply a shell command, filesystem path, AppRole role name, policy text, SecretID, RoleID, token, or provider credential.

Requests/results are mode `0600`; request/result directories are owned by the Jason host operator; the worker lock and lifecycle state remain root-owned. Stale source revisions are rejected.

## Completion criteria

A provider identity incident is not complete until:

- the lifecycle operation reports success without secret exposure;
- the appropriate runtime credential source/staged copy is updated;
- `jason-runtime` is recreated through the governed production path when refresh is required;
- provider-backed read/reconciliation succeeds;
- runtime health is healthy;
- production drift no longer contains the provider-related failure;
- no provider API credential or KV value was changed by the identity repair.
