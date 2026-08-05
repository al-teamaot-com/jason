# CAP-001 Autotask Live-Read Command Binding

**Status:** Foundation
**Owner:** Jason Architecture Authority

## Purpose

This component binds the controlled CAP-001 Autotask live-read validator to the production read-only transport and an external Secrets Broker command.

It provides one operator command for configuration validation and, only after explicit acknowledgement, one exact live ticket read.

## Command boundary

The command requires:

- an exact ticket number;
- an exact company identifier;
- a requested validation scope;
- the separately configured allowed validation scope;
- an evidence path outside the repository;
- three secret references for username, API secret, and integration code;
- one external secret-command path;
- either `--check-only` or explicit `--live-read` authorization.

The command accepts secret references only. It does not accept raw credential values.

## Secret command contract

For each requested secret, Jason executes:

```text
<secret-command> <secret-reference>
```

The command is executed directly without a shell. The secret value must be returned on standard output. Standard output and standard error are never included in failure messages.

The production secret command remains an operator-controlled binding to the approved Secrets Broker implementation.

## Configuration check

`--check-only` validates the command path, required identities, scope alignment, and evidence destination.

It does not:

- resolve any secret;
- perform Autotask zone discovery;
- contact Autotask;
- create an evidence artifact.

## Live-read safeguards

A live request is denied unless `--live-read` is present. The existing live-read validator additionally enforces:

- exact ticket and company matching;
- one authorized validation scope;
- evidence output outside the repository;
- no evidence overwrite;
- redacted, hash-backed evidence;
- no title or description content in the evidence artifact.

## Read-only authority

This command composes only the existing read-only ticket transport and provider. It defines no create, update, delete, attachment, note, time-entry, remediation, or workflow-transition operation.

## First controlled run

Before the first live read, the operator must complete the following in order:

1. configure the approved secret-command implementation;
2. create the three Autotask secret references;
3. designate a non-client validation ticket and company scope;
4. select an evidence destination outside the repository;
5. run `--check-only` and review the result;
6. obtain explicit authorization for one live read;
7. run once with `--live-read`;
8. review and retain the redacted evidence artifact.

No client-production live read is authorized by this foundation.
