# INF-001 — OpenBao Deployment Verification

**Status:** Foundation
**Owner:** Jason Architecture Authority

## Purpose

This increment adds the governed host-side verification command used to collect non-secret facts about the Jason pilot OpenBao deployment.

The command exists so an operator is never asked to discover infrastructure interactively. It performs bounded, read-only probes and produces evidence outside the repository for governed review.

## Command

```bash
.venv-test/bin/python tools/openbao_deployment_verification.py \
  --json-output "$HOME/Jason-Evidence/OpenBao/openbao-verification.json" \
  --markdown-output "$HOME/Jason-Evidence/OpenBao/openbao-verification.md"
```

The output paths must not already exist and must be outside the repository.

## Collected facts

The command checks only non-secret deployment metadata:

- systemd metadata for OpenBao, Vault, and Jason backup units;
- Docker and Podman container names, images, status, and published ports;
- process command metadata;
- existence, size, and SHA-256 hashes of canonical unit, configuration, and wrapper files;
- collection timestamp and host name.

Every subprocess has a bounded timeout. A slow or unavailable system service is recorded as a timeout rather than blocking the operator session.

## Prohibited collection

The command does not:

- use `sudo`;
- initialize, unseal, authenticate to, or query OpenBao;
- read secret payloads;
- print tokens, passwords, recovery shares, unseal keys, or client secrets;
- modify services, containers, files, firewall rules, or repository documentation;
- approve the deployment automatically.

Lines containing sensitive markers are replaced with a redaction marker. Configuration and unit files are hashed rather than copied into evidence.

## Evidence workflow

1. Run the command from a clean governed branch.
2. Review the JSON and Markdown evidence for accidental sensitive content.
3. Map supported facts into `07-Operations/Jason-Secret-Provider-Deployment-Record.md`.
4. Leave unsupported facts as `UNVERIFIED` or `NOT IMPLEMENTED`.
5. Commit the deployment-record changes through normal review.
6. Run the INF-001 readiness gate.

Generated evidence is not committed to Git and is not itself an approval.

## Failure behavior

- Missing tools are recorded as `not_available`.
- Missing files are recorded as `not_found`.
- Failed commands are recorded with a nonzero status without exposing stderr details that match sensitive markers.
- Timed-out probes are recorded as `timeout`.
- Existing output files are never overwritten.
- Repository-local output paths are denied.

## Definition of Done

This verification foundation is complete when:

- the bounded collector and redaction tests pass;
- evidence is written outside the repository;
- no secret or provider write operation is possible through the command;
- the operator runbook contains the exact command;
- collected evidence can support a governed deployment-record update without guesswork.
