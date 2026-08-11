# CAP-007 AWS SES Activation Runbook

## Status

Pre-production activation procedure. This runbook does not authorize production email sending by itself.

## Objective

Activate Jason's provider-neutral `communication.email.send` capability using AWS SES as the initial governed execution provider while preserving Jason's identity, approval, policy, audit, and secret boundaries.

## Preconditions

Do not proceed with a live send unless:

- CAP-007 implementation validation is green;
- the Central Orchestrator and governed capability resolution path are operational;
- JKD-003 Secrets Broker is operational;
- INF-001 secret-provider readiness is green;
- INF-004 AWS SES Secret Onboarding is satisfied;
- an approved AWS SES region is documented;
- an approved sender identity is verified in SES;
- the operator has explicit authority for the live test;
- the test recipient is a controlled TeamAOT mailbox.

## Phase 1 — Kernel registration

Register `communication.email.send` and the pilot provider `aws-ses` through the canonical Kernel registry services. The reference registration is `implementation/cap-007/src/jason_cap_007/kernel_registration.py`.

Version 0.1 pilot policy is deliberately conservative:

- explicit pilot authority required;
- explicit approval required for every send;
- one approved default sender;
- BCC disabled unless policy explicitly changes;
- bulk or campaign behavior denied;
- recipient count bounded;
- idempotency key required;
- maximum one provider attempt;
- no automatic retry or provider fallback;
- no provider credentials in arguments.

A future policy may permit low-risk internal mail without per-message approval only after operating evidence supports the change.

## Phase 2 — Secret onboarding

Canonical logical secret:

```text
aws_ses.sendmail
```

Approved OpenBao provider path:

```text
secret/data/connectors/aws-ses/production/sendmail
```

Required fields are `access_key_id` and `secret_access_key`; `session_token` is optional.

Use only the standard provider-secret lifecycle:

```bash
python3 tools/provider_secret.py status aws_ses
python3 tools/provider_secret.py create aws_ses
python3 tools/provider_secret.py verify aws_ses
```

Do not create a separate SES/sendmail provisioning script. Credential values must not be echoed or placed in command arguments.

## Phase 3 — Non-secret provider configuration

Configure outside OpenBao:

```text
provider_id = aws-ses
region = <approved AWS region>
default_sender = <approved verified sender>
```

The region and sender are configuration, not credential material.

## Phase 4 — Check-only validation

Run CAP-007 through the Central Orchestrator in check-only mode with a controlled synthetic request.

Expected result:

- authority context validates;
- pilot capability is explicitly allowed;
- required approval state is visible;
- `aws-ses` is the only eligible provider;
- an auditable execution plan is produced when approved;
- no AWS network call occurs;
- no secret is resolved;
- no message is sent.

Any secret access or provider call during check-only blocks activation.

## Phase 5 — Controlled live send

Use one explicitly approved internal TeamAOT recipient and a benign test message. Do not include access keys, region, provider ID, endpoint, vault path, or secret name in message arguments.

Expected result:

- orchestrator authorizes execution;
- governed resolution selects `aws-ses`;
- CAP-007 validates sender/message policy;
- JKD-003 resolves `aws_ses.sendmail` only after authorization;
- SES accepts the message;
- CAP-007 returns a provider message ID and recipient count;
- the secret lease is revoked;
- the controlled mailbox receives the message.

SES acceptance is not proof of final delivery. Bounce/delivery telemetry is a separate capability concern.

## Phase 6 — Audit inspection

Allowed audit metadata includes execution ID, correlation ID, principal, organization/client scope, capability, provider, approved sender, recipient count, subject digest, provider message ID, safe result/error code, attempts, and timestamp.

The following must not appear: recipient addresses, clear-text subject, email body, AWS credential values, OpenBao token, AppRole SecretID, or credential-bearing provider exception text.

If any prohibited material appears, stop activation, deactivate runtime access, rotate affected credentials, preserve safe evidence, and remediate before retrying.

## Phase 7 — Activation decision

Record approver, date/time, tested sender, tested recipient class, SES region, provider message ID, audit evidence references, known limitations, credential rotation interval, and next review date.

Production scope must remain no broader than the approved policy.
