# INF-001 Operational Verification Checklist

## Purpose

This checklist provides the supported restart point for verifying the OpenBao foundation and performing a governed CAP-001 Autotask read through the canonical connector.

It replaces the former commissioning-era checklist that required bootstrap credentials, field-level Autotask secret aliases, an external secret command, and manual company-ID input.

## Repository preparation

1. Connect to the Jason host.
2. Change to `$HOME/projects/jason`.
3. Check out the approved branch or `main`.
4. Synchronize using fast-forward-only or the approved hard reset to the reviewed remote branch.
5. Confirm the working tree is clean.
6. Run focused tests for the change under review.
7. Run check-only before any live operation.

## Protected runtime inputs

The canonical Autotask connector uses the dedicated protected AppRole files:

```text
/opt/jason/bootstrap/secrets/openbao/autotask-read-approle/role-id
/opt/jason/bootstrap/secrets/openbao/autotask-read-approle/secret-id
```

They must remain owned by `root:root` with mode `0600`. Do not display, copy, rename, weaken, or place their values into shell history, repository files, evidence, or logs.

The approved logical credential contract is:

```text
autotask.readonly
  -> secret/data/connectors/autotask/production/read-only
  -> username, secret, integration_code
```

Do not create field-level aliases or alternate secret-broker commands.

## Approved non-secret inputs

Record these before execution:

- unique Autotask ticket number;
- requested scope name;
- separately authorized scope name;
- principal ID;
- organization ID;
- correlation ID;
- evidence destination outside the repository.

The operator does not supply an Autotask company ID. The connector derives it from the unique returned ticket.

## Execution stages

### Stage 1: Verify OpenBao foundation

Confirm:

- `jason-secret --health` returns `healthy`;
- `jason-secret --contract-test jason.contract-test` returns `contract-ok`;
- the bootstrap credential remains absent;
- the runtime token remains protected;
- a successful governed backup is recorded;
- a successful isolated restore test is recorded.

Stop immediately if this stage fails.

### Stage 2: Verify deployment readiness

Review `07-Operations/Jason-Secret-Provider-Deployment-Record.md` and run the readiness gate.

The Autotask stage remains denied unless the record is ready and contains verified or explicitly approved values for backup, restore, operational ownership, escalation, and the canonical `autotask.readonly` mapping.

### Stage 3: CAP-001 check-only

Run `tools/autotask_live_read.py --check-only` with the required business, identity, scope, and evidence arguments.

Confirm:

- no AppRole material is read;
- no secret is resolved;
- OpenBao is not contacted;
- Autotask is not contacted;
- no evidence file is written;
- scope, identity, readiness, and evidence-path validation pass.

### Stage 4: Governed live read

Run one explicitly acknowledged read-only request with `--live-read` using the privileged runtime identity required to read the protected AppRole files.

Confirm:

- the query uses the unique ticket number only;
- exactly one matching ticket is accepted;
- the returned ticket number matches the request;
- the company boundary is derived from the returned ticket;
- no write capability is available or invoked;
- evidence is written once with mode `0600`;
- evidence contains hashes rather than raw title or description;
- no credential, token, AppRole value, or provider response body is retained.

### Stage 5: Post-operation verification

Confirm:

- OpenBao remains healthy;
- the repository remains clean;
- the evidence artifact exists outside the repository;
- the evidence reports `protected_values_exposed: false`;
- the evidence logical secret is `autotask.readonly`;
- the evidence capability is `autotask.ticket.search`.

## Final validation

After a governed live read or architectural change:

1. Run the connector test suite.
2. Run the CAP-001 test suite.
3. Run the release test suite.
4. Run the Kernel test suite.
5. Run complete release validation.
6. Assemble documentation.
7. Build documentation in strict mode.
8. Run the whitespace check.
9. Confirm the branch is clean.
10. Review retained non-secret evidence.
11. Mark the pull request ready only after every required stage passes.

## Stop conditions

Stop and preserve non-secret diagnostic evidence without continuing when any of the following occurs:

- a protected file has broad permissions;
- an expected evidence path already exists;
- OpenBao health or contract validation fails;
- the deployment readiness gate remains denied;
- the canonical logical mapping is missing;
- requested and authorized scopes differ;
- the ticket lookup returns zero or multiple results;
- the returned ticket identity differs from the request;
- the provider-derived company boundary is absent;
- a secret or raw ticket-content value appears in output or evidence;
- any request attempts a write operation.
