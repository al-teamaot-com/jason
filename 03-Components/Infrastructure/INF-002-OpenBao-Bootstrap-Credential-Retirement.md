# INF-002 OpenBao Bootstrap Credential Retirement

## Status

Foundation implementation. Production-readiness enforcement remains a separate governed increment.

## Purpose

This control retires the temporary OpenBao bootstrap identity after the dedicated `jason-secret` runtime identity has been provisioned and verified.

A bootstrap credential is commissioning material. It must not remain on the host indefinitely merely because it was once required to create a policy, contract-test value, or dedicated token.

## Lifecycle

The governed lifecycle is:

1. create or obtain a time-bounded bootstrap identity;
2. provision the dedicated runtime identity;
3. verify `jason-secret --health`;
4. verify `jason-secret --contract-test jason.contract-test`;
5. revoke the bootstrap token;
6. remove the bootstrap token file;
7. remove the temporary contract-test input file;
8. preserve non-secret retirement evidence.

The runtime identity remains at `/etc/jason/openbao.token`. The retired inputs are:

- `/etc/jason/openbao-bootstrap.token`;
- `/etc/jason/openbao-contract-test.value`.

## Command

Configuration-only validation:

```bash
sudo .venv-test/bin/python tools/retire_openbao_bootstrap.py \
  --evidence-output /home/al/Jason-Evidence/Secret-Provider/bootstrap-retirement-check.json \
  --check-only
```

Governed retirement:

```bash
sudo .venv-test/bin/python tools/retire_openbao_bootstrap.py \
  --evidence-output /home/al/Jason-Evidence/Secret-Provider/openbao-bootstrap-retirement-<UTC>.json
```

The evidence path must not already exist.

## Fail-closed behavior

Retirement is denied before revocation when:

- the command is not running as root;
- a protected input is missing, empty, or readable by group or world;
- the dedicated runtime token is missing or insufficiently protected;
- the canonical wrapper is absent or not executable;
- runtime health does not return exactly `healthy`;
- the authenticated contract test does not return exactly `contract-ok`;
- the evidence destination already exists or cannot be prepared.

A failed OpenBao revocation stops the command and leaves the protected input files in place for governed review.

## Evidence

The retirement evidence records only:

- schema and evidence type;
- UTC collection time and host;
- OpenBao address;
- dedicated runtime token path;
- runtime health and contract-test status;
- bootstrap-token revocation status;
- bootstrap and contract-input removal status;
- an explicit assertion that protected values were not exposed.

The evidence must not contain any token, password, contract value, unseal share, or other secret material. It is created with mode `0600`.

## Completion criteria

This increment is complete when:

- focused and regression tests pass;
- check-only performs no protected read, OpenBao request, or file change;
- the dedicated runtime identity passes both wrapper validations;
- the bootstrap token is revoked;
- temporary protected inputs are absent;
- non-secret evidence exists with restrictive permissions;
- complete release, CAP-001, Kernel, documentation, and whitespace validation passes.

## Deferred enforcement

A subsequent increment will make the presence of a bootstrap-token file a production-readiness blocker except during an explicitly declared commissioning window. Emergency or maintenance elevation must use a separate governed break-glass procedure and must end with this retirement control.
