# INF-001 Jason Secret Wrapper

## Status

Foundation implementation. Production installation and authentication remain governed deployment work.

## Purpose

`jason-secret` is the canonical command boundary between Jason capabilities and the selected secret provider. Capabilities request a logical name; they never embed provider paths, authentication details, or secret values.

## Command contract

Resolve one logical secret:

```text
jason-secret <logical-name>
```

On success, stdout contains exactly one secret value followed by a newline. Diagnostics are written only to stderr. No provider token, mapping content, or secret value may appear in diagnostics.

Health check:

```text
jason-secret --health
```

A successful health check prints `healthy`. It does not resolve a secret.

Contract test:

```text
jason-secret --contract-test <logical-name>
```

A successful contract test proves that the mapping, authentication, provider request, and field extraction work while printing only `contract-ok`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `2` | Command usage failure |
| `10` | Provider unavailable |
| `11` | Authentication unavailable or unauthorized |
| `12` | Logical name, provider path, or field not found |
| `13` | Mapping or provider response malformed |
| `14` | Other backend failure |

## Configuration

The wrapper reads no credentials from command-line arguments.

| Setting | Purpose |
|---|---|
| `JASON_SECRET_BACKEND` | `openbao` or deterministic `test-file` backend |
| `JASON_OPENBAO_ADDR` | OpenBao address; pilot default is `http://127.0.0.1:8200` |
| `JASON_OPENBAO_TOKEN_FILE` | External token file used by the deployed identity |
| `JASON_SECRET_TEST_VALUES_FILE` | Test-only values file for deterministic tests |
| `/etc/jason/secret-mappings.json` | Canonical logical-name mapping file |

The production authentication method and token-file lifecycle must be approved and documented before installation is marked ready.

## Mapping format

```json
{
  "autotask.readonly.username": {
    "path": "secret/data/connectors/autotask/production/read-only",
    "field": "username"
  }
}
```

Mappings contain references only. Secret values must never be stored in the mapping file or repository.

## Installation

Validate installation inputs without changing the host:

```bash
python tools/install_jason_secret.py --check-only
```

Governed installation writes:

- `/opt/jason/lib/jason_secret.py`
- `/usr/local/bin/jason-secret`

Host installation requires normal change approval and must be followed by health and contract tests.

## Safety requirements

- Authentication material is supplied externally.
- Secret values are emitted only for direct resolution mode.
- Health and contract-test modes never print values.
- CAP-001 continues to require the INF-001 readiness gate before live execution.
- The deployment record remains blocked until installation, authentication, mappings, health, and contract testing are verified.
