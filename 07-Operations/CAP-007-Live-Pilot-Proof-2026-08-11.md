# CAP-007 Live Pilot Proof — 2026-08-11

## Purpose

This record preserves the evidence for the first successful end-to-end governed live pilot of Jason capability `communication.email.send` using provider `aws-ses`.

## Scope

The pilot was intentionally narrow:

- one controlled TeamAOT mailbox;
- sender `jason@teamaot.com`;
- AWS SES region `us-east-1`;
- explicit approval required;
- scoped JKD-001 execute authority;
- one provider attempt;
- no automatic retry;
- no provider fallback;
- idempotency key required;
- durable safe audit required.

## Preconditions validated

Before the successful live execution, the following were validated:

- CAP-007 and runtime tests were green;
- the runtime container was rebuilt with the current CAP-007 implementation;
- `OrchestrationRequest` contained `idempotency_key` support;
- Kernel resolution required an idempotency key for CAP-007;
- CAP-007 was registered in the runtime capability/provider registries;
- the runtime used `JKD001OrchestrationContextEnforcer` with real execution-context validation;
- a scoped JKD-001 grant existed for `person-al`, organization `aot`, capability `communication.email.send`, permission `execute`, with approval required;
- the dedicated SES OpenBao AppRole files were mounted read-only and readable by the non-root runtime identity;
- `Cap007EventAudit` was active and tested;
- AWS SES safe provider-error mapping was active and tested;
- TeamAOT SES sending identity was verified in `us-east-1`;
- the SES account was production-enabled;
- the dedicated IAM user `jason-ses-sendmail` and least-privilege SES send policy were configured;
- the logical secret `aws_ses.sendmail` was provisioned and verified through the canonical provider-secret lifecycle.

## First controlled execution

The first live activation execution did not reach AWS SES. The manual activation harness supplied the AppRole RoleID/SecretID file paths as strings rather than `pathlib.Path` objects. CAP-007 recorded one failed attempt and the orchestrator did not retry.

This was a harness defect, not an OpenBao or SES credential failure.

## No-send provider-boundary diagnostic

Before any second live execution, a diagnostic was run that did not invoke SES `SendEmail`.

Observed result:

```text
OPENBAO SECRET RESOLUTION
PASS: OpenBao secret resolved.
fields_present: access_key_id,secret_access_key
required_fields_present: True
unexpected_fields: none

AWS CREDENTIAL AUTHENTICATION
PASS: AWS credentials authenticated.
account: 887670144825
arn: arn:aws:iam::887670144825:user/jason-ses-sendmail

PASS: Diagnostic completed without calling SES SendEmail.
```

This established that the JKD-003/OpenBao boundary and stored AWS credential were healthy before another live attempt was authorized.

## Successful governed execution

The corrected execution used a new request, approval, execution context, correlation ID, and idempotency key. It was not a retry of the failed execution.

Observed result:

```text
status: succeeded
stage: completed
provider: aws-ses
attempts: 1
reason_codes: capability_completed
error_code: None
accepted: True
recipient_count: 1
message_id: 0100019ff0656115-4a3b6d32-f1f5-4b7d-8e8a-31d6ea827ce2-000000
```

AWS SES therefore accepted exactly one governed message during the successful execution.

## Durable audit evidence

The successful execution ID was:

```text
cap007-pilot-exec-e5639f4c90c34fcd93f3023e28800ea5
```

The durable event sequence was:

```text
orchestration.request.received | stage=received
orchestration.capability.resolved | stage=policy_decided
orchestration.capability.invoking | stage=invoking
email.send.attempted | stage=invoking
email.send.completed | stage=completed
orchestration.capability.completed | stage=completed
```

Post-send audit verification passed:

```text
PASS: No recipient-bearing fields persisted.
PASS: No clear subject persisted.
PASS: No message body persisted.
PASS: No credential-bearing fields persisted.
PASS: Sender metadata is permitted.
PASS: Successful CAP-007 completion evidence exists.
```

The literal sender address may appear in audit metadata because sender is explicitly allowed. Recipient-bearing fields and message content remain prohibited.

## Mailbox delivery proof

The controlled mailbox showed the received message:

```text
From: jason@teamaot.com
Subject: Jason CAP-007 Governed Email Pilot
Received: 06:37 America/New_York
```

The operator supplied the received Outlook message as external mailbox evidence named:

```text
Jason CAP-007 Governed Email Pilot.msg
```

SHA-256 of the supplied evidence file:

```text
0cb33d65656b265c26cff4ee9fc52699dc58385896dd734d888fdd32ad4a04f5
```

The binary message file is not stored in this repository by this record; the digest allows later integrity comparison against the operator-retained evidence.

## Activation conclusion

CAP-007 Version 0.1 successfully completed the controlled end-to-end live pilot on 2026-08-11:

1. operator identity and scoped authority existed;
2. explicit per-request approval was recorded;
3. a short-lived JKD-001 execution context was issued;
4. governed Kernel resolution selected `aws-ses`;
5. the required idempotency key was present;
6. JKD-003 resolved the dedicated SES credential only after authorization;
7. AWS SES accepted one message;
8. the durable audit trail recorded attempted/completed execution without prohibited message or credential data;
9. the controlled mailbox received the message.

CAP-007 is therefore operational for its approved pilot scope.

## Known remaining integration gap

The Teams conversational interface is not yet connected to CAP-007. Asking Jason in Teams to send email does not currently result in a governed `communication.email.send` orchestration request.

This is the next workstream. The implementation must route Teams intent through the Central Orchestrator and existing CAP-007 capability. It must not create a direct Teams-to-SES path or a workflow-specific sendmail script.
