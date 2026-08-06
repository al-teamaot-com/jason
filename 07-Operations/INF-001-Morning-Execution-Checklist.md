# INF-001 Morning Execution Checklist

## Purpose

This checklist provides a single restart point for completing INF-001 production readiness and the first controlled CAP-001 Autotask read after the repository-side closeout foundation has passed validation.

## Repository preparation

1. Connect to the Jason host.
2. Change to `/tmp/jason-github`.
3. Check out `feature/inf-001-production-readiness-closeout`.
4. Pull the branch using fast-forward only.
5. Confirm the working tree is clean.
6. Run the focused closeout tests.
7. Run the no-network closeout check.

## Protected input preparation

The following values must be prepared on the Jason host without printing them, copying them into the repository, or placing them in command history:

- OpenBao bootstrap credential in its approved protected file;
- non-production contract-test value in its approved protected file;
- Autotask API username;
- Autotask API secret;
- Autotask integration code.

All protected files must be owned by the approved operating identity and must not grant group or other access.

## Approved pilot identifiers

Record these non-secret values before execution:

- approved ticket number;
- approved company ID;
- approved scope name;
- contract-test evidence destination;
- Autotask evidence destination.

Evidence paths must not already exist.

## Execution stages

### Stage 1: OpenBao contract test

Run the authenticated OpenBao contract-test workflow. Confirm:

- the least-privilege policy is created;
- the non-production contract secret is written;
- the dedicated token file is created with private permissions;
- `jason-secret --health` returns `healthy`;
- the contract test returns `contract-ok`;
- the evidence report contains no secret value.

Stop immediately if this stage fails. Do not continue to Autotask.

### Stage 2: Deployment record and readiness

Update the canonical deployment record using only verified facts from the evidence. Then run the deployment readiness gate.

The Autotask stage remains denied until the readiness gate reports approved.

### Stage 3: Autotask logical mappings

Create the approved logical mappings for:

- `autotask.api.username`;
- `autotask.api.secret`;
- `autotask.api.integration-code`.

The mapping file may contain paths and field names only. It must not contain credential values.

### Stage 4: CAP-001 configuration check

Run CAP-001 in check-only mode. Confirm:

- no secret is resolved;
- no Autotask request is made;
- no evidence file is written;
- scope and evidence-path validation pass.

### Stage 5: First controlled live read

Run one explicitly acknowledged read-only request against the approved ticket and company. Confirm:

- exactly one approved ticket is requested;
- no write method is available or invoked;
- the returned company context matches the approved company;
- evidence is written once and does not contain credentials;
- failures suppress protected subprocess output.

## Final validation

After the controlled live read:

1. Run the complete release test suite.
2. Run the complete CAP-001 test suite.
3. Run the full Kernel test suite.
4. Run complete release validation.
5. Assemble documentation.
6. Build documentation in strict mode.
7. Run the whitespace check.
8. Confirm the branch is clean.
9. Review the generated evidence.
10. Mark the pull request ready only after every required stage passes.

## Stop conditions

Stop and preserve evidence without continuing when any of the following occurs:

- a protected file has broad permissions;
- an expected evidence path already exists;
- OpenBao health or contract validation fails;
- the deployment readiness gate remains denied;
- logical mappings are missing;
- requested and authorized scopes differ;
- the ticket and company relationship cannot be confirmed;
- a secret value appears in output or evidence;
- any request attempts a write operation.
