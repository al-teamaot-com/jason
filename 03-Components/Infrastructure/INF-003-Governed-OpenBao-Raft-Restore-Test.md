# INF-003 Governed OpenBao Raft Restore Test

## Purpose

This capability verifies that a protected OpenBao Raft snapshot can be restored without modifying the live OpenBao container, live Raft data, live Docker network, or live listener.

The test is a governed operational capability rather than an ad hoc shell procedure.

## Isolation boundary

The restore test must use:

- container name `openbao-restore-test`;
- Docker network `jason-restore-test`;
- loopback-only host port `127.0.0.1:8300`;
- temporary configuration, data, audit, log, and snapshot directories under `/tmp`;
- no attachment to `jason-core`;
- automatic container, network, and temporary-directory cleanup on success or failure.

The command must reject the live container name, live Docker network, or identical live and test addresses.

## Inputs

The governed test uses:

- the newest `*.snap` in `/opt/jason/backups/openbao`;
- its required `.sha256` sidecar;
- protected initialization material at `/opt/jason/bootstrap/secrets/openbao/init.json`;
- the dedicated runtime token at `/etc/jason/openbao.token`;
- the canonical wrapper at `/usr/local/bin/jason-secret`.

Protected values must never be printed or written to evidence.

## Check-only mode

```bash
sudo .venv-test/bin/python tools/openbao_raft_restore_test.py \
  --evidence-output /home/al/Jason-Evidence/OpenBao/restore-check.json \
  --check-only
```

Check-only validates configuration and isolation declarations. It makes no Docker or OpenBao request, reads no protected material, and writes no evidence.

## Governed live test

```bash
sudo .venv-test/bin/python tools/openbao_raft_restore_test.py \
  --evidence-output /home/al/Jason-Evidence/OpenBao/openbao-raft-restore-test-<UTC>.json
```

The command:

1. verifies the latest snapshot checksum;
2. verifies the live cluster is initialized, unsealed, and contract-capable;
3. removes stale test container or network state;
4. creates isolated temporary storage and a dedicated bridge network;
5. starts a fresh OpenBao instance on loopback port `8300`;
6. initializes and temporarily unseals the restore target;
7. restores the verified snapshot with OpenBao's forced restore operation;
8. unseals the restored instance with the protected threshold material;
9. verifies the restored cluster ID matches the source cluster;
10. verifies the authenticated `jason.contract-test` contract against the restored instance;
11. revalidates the live instance;
12. writes mode-`0600` non-secret evidence;
13. removes the isolated container, network, and temporary storage.

## Evidence

Approved evidence may contain:

- UTC timestamp and host;
- snapshot path, size, and SHA-256;
- isolated container, network, and loopback port;
- live and restored cluster IDs;
- cluster identity comparison result;
- restored initialization, seal, and contract status;
- live-service post-test status;
- assertions that live data was not modified and protected values were not exposed.

Evidence must not contain tokens, root credentials, unseal shares, passwords, secret IDs, API credentials, or secret values.

## Fail-closed behavior

The test is denied when:

- it is not run as root outside check-only mode;
- protected files are missing or broadly readable;
- no snapshot or checksum sidecar exists;
- checksum verification fails;
- the live cluster is unavailable, sealed, or missing its cluster ID;
- stale test state cannot be removed;
- the isolated target cannot start;
- restore or threshold unseal fails;
- restored and source cluster IDs differ;
- restored or live wrapper validation fails;
- the evidence path already exists.

Cleanup is attempted in a `finally` boundary even when the test fails.

## Completion criteria

INF-003 is complete when focused tests, governed check-only validation, a successful isolated live restore, evidence inspection, complete release validation, and strict documentation validation all pass.