# INF-015 — AWS Provider Platform Foundation

## Purpose

Establish AWS as a governed provider family inside Jason without introducing ad hoc SDK access, durable runtime credentials, provider-specific authority bypasses, or direct agent-to-provider execution.

## Architectural position

AWS is a provider behind Jason's existing identity, authority, policy, orchestration, secret-broker, audit, and evidence boundaries.

OpenClaw and agents do not call AWS directly. A request must enter through the Central Orchestrator as a named capability, carry a valid JKD-001 authority context, pass applicable governance gates, and resolve through the provider/capability registry.

## Initial operating mode

The first AWS foundation is read-only. `read` and `recommend` modes may resolve only catalogued non-mutating operations. Write-with-approval and bounded automation are not enabled by INF-015.

STS `AssumeRole` is not exposed as an ordinary capability. It is reserved for the Jason secret/credential broker boundary.

## Identity and scope

Every AWS provider request is scoped by:

- Jason organization/client identity;
- AWS Organizations organization ID;
- AWS account ID;
- AWS region when the service is regional;
- named service and action;
- requested Jason operation mode;
- authority context/correlation ID supplied by the orchestrator.

Account IDs are treated as canonical 12-digit identifiers. Organization IDs use the AWS Organizations `o-...` identifier.

For Organizations account normalization, use the current `State` field. Do not build new logic around the retiring `Status` field.

## Credential model

Durable configuration may contain only identifiers/references required to obtain temporary credentials, such as:

- AWS account ID;
- organization ID;
- role ARN;
- home/default region;
- logical secret/broker references;
- optional external-ID secret reference.

Runtime-only STS material includes:

- access key ID;
- secret access key;
- session token;
- credential expiration.

Runtime STS credentials must not be written to Git, chat, audit payloads, evidence artifacts, ordinary logs, durable connector configuration, or provider-normalized resource objects.

## Initial service catalog

The initial review/read family includes:

- STS — `GetCallerIdentity` only as a provider read; `AssumeRole` remains broker-only;
- Organizations — organization/account/OU discovery;
- IAM — account summary, roles, policies, aliases;
- Config — discovered resources and recorder state;
- Security Hub — hub/standards/findings reads;
- GuardDuty — detector/findings reads;
- CloudTrail — trail status and event lookup;
- EC2 — instances, volumes, VPCs, security groups;
- S3 — buckets/location/versioning/public-access-block reads;
- RDS — instances, clusters, snapshots;
- Backup — vaults, recovery points, plans;
- Systems Manager — managed-instance/compliance reads.

This catalog is a governance allow-list, not a promise that every action is available in every AWS account. Account type, delegated-administrator status, region, service enablement, IAM policy, SCPs, and resource policies may further restrict execution.

## Provider normalization

Provider payloads must be normalized before durable persistence. Prefer Jason canonical resource identity such as:

- provider = `aws`;
- organization ID;
- account ID;
- region/global scope;
- service;
- resource type;
- provider resource ID/ARN;
- display name;
- lifecycle/state;
- selected security/configuration attributes;
- evidence references.

Do not persist raw AWS API responses solely for convenience.

## Governance rules

- no agent may invoke AWS directly;
- no arbitrary AWS action name supplied by a caller is trusted unless present in the governed service catalog;
- regional services require explicit region scope;
- first live validation uses a dedicated least-privilege/read-only role in a controlled account;
- Organizations discovery must tolerate pagination and use `NextToken` until exhausted when a complete result is required;
- live reads require the Central Orchestrator and JKD-001 authority context;
- provider failures must be normalized and audited without secrets;
- no write permission is implied by successful read-only live validation.

## Credential-safe completion boundary

INF-015 can be developed and validated through the credential-safe preflight without AWS credentials. The live boundary is reached when Jason requires a governed role binding and temporary STS session.

Run:

```bash
python3 tools/aws_provider_foundation_check.py
```

A healthy credential-safe result reports `credential_boundary_reached`, `network_contacted=false`, and `credential_resolved=false`.

## Live validation sequence

1. provision a dedicated least-privilege role in a controlled AWS account;
2. bind the role through Jason's secret/credential broker;
3. obtain temporary credentials using STS at runtime only;
4. call `GetCallerIdentity` and verify the expected account identity;
5. perform bounded Organizations discovery only if the account has the required management/delegated-admin rights;
6. perform one regional read such as EC2 inventory in an explicitly scoped region;
7. inspect only normalized/sanitized response fields;
8. run the provider read through the Central Orchestrator and capture authority/audit/evidence records;
9. stop before any mutation capability.

## Integrate before innovate

Prefer AWS-native capabilities for organization/account inventory, IAM identity/role control, CloudTrail audit, Config inventory/compliance, Security Hub aggregation, GuardDuty detection, Backup, and Systems Manager instead of rebuilding those systems inside Jason.
