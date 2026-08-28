# INF-015 — AWS Provider Deployment Checklist

## Credential-safe phase

- [ ] `implementation/connectors/aws/` compiles.
- [ ] AWS service catalog tests pass.
- [ ] Account ID, organization ID, and regional-scope validation tests pass.
- [ ] Uncatalogued and mutation actions fail closed.
- [ ] STS `AssumeRole` is rejected as an ordinary provider capability.
- [ ] `tools/aws_provider_foundation_check.py` reports `credential_boundary_reached`.
- [ ] No AWS network request is made.
- [ ] No AWS credential is resolved.

## Controlled live-role preparation

- [ ] Select a controlled AWS test account.
- [ ] Confirm its AWS Organizations organization ID and 12-digit account ID.
- [ ] Create a dedicated least-privilege/read-only IAM role for Jason.
- [ ] Use an external ID where appropriate for the trust relationship.
- [ ] Store only governed role/bootstrap references through Jason/OpenBao.
- [ ] Do not store temporary STS access key, secret key, or session token durably.
- [ ] Explicitly document allowed regions.
- [ ] Confirm SCPs/resource policies do not unintentionally expand or bypass Jason governance.

## First live validation

- [ ] Resolve the role through the Jason secret/credential broker.
- [ ] Assume the role and keep returned STS credentials runtime-only.
- [ ] Call STS `GetCallerIdentity`; verify the expected account.
- [ ] If authorized as management/delegated administrator, perform bounded Organizations discovery.
- [ ] Use Organizations `State`, not the retiring `Status` field, in normalized account records.
- [ ] Follow `NextToken` pagination until complete only when complete account enumeration is required.
- [ ] Perform one explicitly regional read such as EC2 `DescribeInstances` in the controlled account.
- [ ] Normalize the provider response; do not persist raw credentials or unnecessary raw payloads.
- [ ] Execute the live read through the Central Orchestrator with a valid JKD-001 authority context.
- [ ] Capture sanitized authority, provider, audit, and evidence records.

## Stop conditions

Stop and fail closed if:

- the assumed account does not match the expected account;
- account or region scope is ambiguous;
- a requested action is not in the governed catalog;
- a write/mutation is attempted;
- temporary credentials would be written to durable state/logs/evidence;
- OpenBao/credential-broker resolution is bypassed;
- an agent or OpenClaw attempts direct AWS execution;
- Central Orchestrator or JKD-001 authority context is absent;
- provider output cannot be safely normalized.

## Expansion after first proof

Only after the first governed read proof should Jason evaluate additional AWS reads across IAM, Config, Security Hub, GuardDuty, CloudTrail, S3, RDS, Backup, and Systems Manager. Mutation capabilities require separate explicit design, governance, approval, rollback, and evidence work; INF-015 does not authorize them.
