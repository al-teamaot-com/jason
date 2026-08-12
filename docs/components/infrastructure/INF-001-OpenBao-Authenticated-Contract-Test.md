# INF-001 OpenBao Authenticated Contract Test

## Status

Foundation implementation. Live execution requires explicit operator preparation and review.

## Purpose

This increment proves the complete `jason-secret` path against a dedicated non-production OpenBao secret without enabling Autotask access.

## Scope

The governed provisioning command:

- creates the `jason-contract-test` ACL policy;
- limits that policy to read access on `secret/data/jason/contract-test`;
- writes one non-production contract-test value supplied through a protected local file;
- issues a dedicated renewable token with a 24-hour TTL;
- stores the dedicated token at `/etc/jason/openbao.token` with mode `0600`;
- runs wrapper health validation;
- runs `jason-secret --contract-test jason.contract-test`;
- emits non-secret evidence only.

## Required protected inputs

The operator must create these files outside the repository:

- `/etc/jason/openbao-bootstrap.token` — an existing OpenBao identity authorized to create the policy, test secret, and dedicated token;
- `/etc/jason/openbao-contract-test.value` — a non-production test value.

Both files must be owned appropriately and use mode `0600`. Their contents must never be copied into the repository, terminal transcript, evidence, or deployment record.

## Safety boundaries

The command will not:

- use the OpenBao root token unless the operator deliberately supplies it as the bootstrap identity;
- print the bootstrap token, dedicated token, or contract value;
- add any Autotask logical mapping;
- authorize CAP-001 live execution;
- overwrite an existing `/etc/jason/openbao.token`;
- approve the deployment record automatically.

## Check-only mode

```bash
.venv-test/bin/python tools/provision_openbao_contract_test.py --check-only
```

Check-only mode performs no file changes and makes no OpenBao request.

## Governed live command

```bash
sudo .venv-test/bin/python tools/provision_openbao_contract_test.py \
  --evidence-output "$HOME/Jason-Evidence/Secret-Provider/openbao-contract-test-<timestamp>.json"
```

The evidence report may contain paths, policy name, contract path, token mode, and pass/fail states. It must not contain token or secret values.

## Completion evidence

This increment is complete only when:

- focused and regression tests pass;
- protected input permissions are verified;
- wrapper health returns `healthy`;
- contract-test mode returns exactly `contract-ok`;
- the dedicated token is mode `0600`;
- evidence contains no secret values;
- the canonical deployment record is updated through a separate governed review.
