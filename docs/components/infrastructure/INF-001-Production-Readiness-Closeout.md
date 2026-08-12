# INF-001 Production Readiness Closeout

## Purpose

This increment combines the remaining INF-001 authenticated contract test and the first governed CAP-001 Autotask validation into one controlled closeout sequence. It reduces branch and pull-request overhead without weakening identity, evidence, approval, or read-only boundaries.

## Command

`tools/production_readiness_closeout.py` coordinates existing governed commands. It does not implement a new secret backend or Autotask transport.

The command supports:

- a no-network `--check-only` mode;
- the authenticated OpenBao contract-test provisioning command;
- CAP-001 Autotask configuration validation;
- one explicitly acknowledged read-only live request;
- separate, non-overwriting evidence outputs;
- logical secret references rather than embedded credentials.

## Morning restart point

Use `07-Operations/INF-001-Morning-Execution-Checklist.md` as the canonical restart checklist. It identifies the repository preparation, protected inputs, approved pilot identifiers, execution stages, validation sequence, and mandatory stop conditions.

## Required protected inputs

The authenticated phase still requires protected host files established by the OpenBao contract-test workflow:

- `/etc/jason/openbao-bootstrap.token`
- `/etc/jason/openbao-contract-test.value`

The values must never be committed, printed, or copied into evidence.

## Required pilot inputs

Before a live Autotask read, the operator must provide:

- one approved ticket number;
- the corresponding approved company ID;
- a named authorized scope;
- logical references for the Autotask username, secret, and integration code;
- a deployment record that passes INF-001 readiness enforcement.

## Safety boundaries

The closeout command:

- refuses scope mismatches;
- refuses existing evidence paths;
- refuses a missing canonical secret command;
- refuses a missing deployment record;
- performs no secret resolution or network request in check-only mode;
- does not print subprocess output when a protected stage fails;
- does not bypass the existing deployment readiness gate;
- requires `--live-read` before any Autotask request.

## Completion criteria

INF-001 production readiness closeout is complete only when:

1. the authenticated OpenBao contract test reports approved;
2. the canonical deployment record is updated with verified facts;
3. the readiness gate reports approved;
4. Autotask logical mappings are present in OpenBao and the mapping file;
5. CAP-001 check-only reports approved;
6. one approved live read produces non-secret evidence;
7. release, CAP-001, Kernel, documentation, and whitespace validation pass;
8. the governed closeout change is reviewed and merged.
