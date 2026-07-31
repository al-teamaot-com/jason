# Jason OpenBao Secret Layout

## Purpose

This document defines the approved namespace for secrets stored in the
Jason OpenBao deployment.

All secrets are stored in the KV v2 engine mounted at:

    secret/

## Approved top-level paths

### secret/platform/

Credentials and cryptographic material used internally by Jason.

Examples:

    secret/platform/orchestrator/
    secret/platform/secrets-broker/
    secret/platform/monitoring/

### secret/infrastructure/

Credentials for infrastructure supporting Jason.

Examples:

    secret/infrastructure/database/
    secret/infrastructure/docker/
    secret/infrastructure/backup/
    secret/infrastructure/network/

### secret/connectors/

Credentials assigned to governed connector identities that communicate with
external platforms.

Connectors are Jason's credential-brokering and external-system execution
boundary.

Required format:

    secret/connectors/<platform>/<environment>/<identity-or-purpose>

Examples:

    secret/connectors/autotask/production/read-only
    secret/connectors/autotask/production/ticket-write
    secret/connectors/datto-rmm/production/read-only
    secret/connectors/it-glue/production/documentation-write
    secret/connectors/microsoft/production/directory-read
    secret/connectors/duo/production/status-read
    secret/connectors/aws/production/automation

### secret/clients/

Client-specific credentials and secrets.

Required format:

    secret/clients/<client-identifier>/<system-or-purpose>/

Rules:

1. Each client must use a unique, stable client identifier.
2. Client secrets must never be stored in another client's path.
3. Cross-client access is prohibited unless explicitly approved and documented.
4. Policies should be scoped to the smallest required client path.
5. Client names should not be used when they are likely to change.

### secret/shared/

Secrets intentionally shared by more than one governed Jason component.

Use of this path requires:

1. documented business justification;
2. named owner;
3. approved consumers;
4. rotation interval;
5. retirement criteria.

## Naming rules

Use:

- lowercase letters;
- numbers where necessary;
- hyphens between words;
- stable system or purpose names.

Do not use:

- spaces;
- personal names unless the secret belongs to an individual account;
- temporary project names;
- client secrets outside secret/clients/;
- secret values in path names.

## Required secret metadata

Where practical, each managed secret record should include non-secret fields
describing:

- owner;
- purpose;
- source system;
- environment;
- created date;
- review date;
- rotation interval;
- retirement criteria.

Metadata fields must not contain passwords, tokens, private keys, or other
secret values.

## Access model

Human administrators:

    jason-admin

Daily secret operators:

    jason-secrets-manager

Automated services:

Automated services must receive separate least-privilege policies. They must
not use human accounts or administrator policies.

Agents must not access OpenBao directly. Secret requests must pass through
Jason's central orchestration and secrets-broker controls.

## Destructive operations

The jason-secrets-manager policy does not permit:

- permanent version destruction;
- complete metadata deletion;
- OpenBao system administration.

Permanent destruction requires a separate approval-gated administrative
procedure.

## Manual Shamir custody

OpenBao currently uses manual Shamir unsealing.

Before production use:

1. distribute the five unseal keys through separate secure custody;
2. confirm that any three authorized shares can complete recovery;
3. remove the server-resident copy after verified distribution;
4. document emergency access and custody replacement procedures;
5. test recovery at least annually.

Cloud KMS auto-unseal remains a future evaluation item and is not currently
enabled.
