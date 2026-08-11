# CAP-007 AWS SES Activation Runbook

## Status

Controlled live pilot completed successfully on 2026-08-11. CAP-007 is validated end-to-end for the approved pilot scope. This runbook does not authorize broader production email sending by itself.

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

These preconditions were satisfied for the 2026-08-11 controlled pilot.

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

A future policy may permit low-risk internal mail without per-message approval only after operating evidence supports that change.

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

Pilot evidence confirmed the dedicated SES AppRole can resolve the logical secret and that the stored credentials authenticate to AWS as the dedicated `jason-ses-sendmail` IAM user. The runtime OpenBao service token is revoked after the allow-listed read.

## Phase 3 — Non-secret provider configuration

Approved pilot configuration:

```text
provider_id = aws-ses
region = us-east-1
default_sender = jason@teamaot.com
```

The region and sender are configuration, not credential material.

The TeamAOT SES domain identity was verified for sending in `us-east-1`, and the SES account was production-enabled at activation time.

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

The pilot implementation was verified to return `check_only_validated` with zero attempts and `provider_invoked=False` before live execution.

## Phase 5 — Controlled live send

Use one explicitly approved internal TeamAOT recipient and a benign test message. Do not include access keys, region, provider ID, endpoint, vault path, or secret name in message arguments.

Expected result:

- orchestrator authorizes execution;
- governed resolution selects `aws-ses`;
- CAP-007 validates sender/message policy;
- JKD-003 resolves `aws_ses.sendmail` only after authorization;
- SES accepts the message;
- CAP-007 returns a provider message ID and recipient count;
- the runtime OpenBao token has already been revoked after the secret read;
- the controlled mailbox receives the message.

SES acceptance is not proof of final delivery. Bounce/delivery telemetry is a separate capability concern.

### 2026-08-11 pilot execution

A scoped JKD-001 authority grant was established for `person-al`, organization `aot`, capability `communication.email.send`, permission `execute`, with `approval_required=true`.

The first controlled execution failed before SES because the manual activation harness supplied AppRole credential-file locations as strings instead of `Path` objects. The governed path recorded one failed attempt and did not retry. A no-send diagnostic then proved:

- OpenBao secret resolution succeeded;
- required secret fields were present;
- no unexpected secret fields were returned;
- the AWS credentials authenticated successfully as `arn:aws:iam::887670144825:user/jason-ses-sendmail`.

The corrected second execution used a new request ID, approval ID, execution context, correlation ID, and idempotency key. It succeeded with:

```text
status = succeeded
stage = completed
provider = aws-ses
attempts = 1
accepted = true
recipient_count = 1
message_id = 0100019ff0656115-4a3b6d32-f1f5-4b7d-8e8a-31d6ea827ce2-000000
```

The controlled mailbox subsequently received the message with subject `Jason CAP-007 Governed Email Pilot` at 06:37 America/New_York.

## Phase 6 — Audit inspection

Allowed audit metadata includes execution ID, correlation ID, principal, organization/client scope, capability, provider, approved sender, recipient count, subject digest, provider message ID, safe result/error code, attempts, and timestamp.

The following must not appear: recipient-bearing fields, clear-text subject, email body, AWS credential values, OpenBao token, AppRole SecretID, or credential-bearing provider exception text.

If any prohibited material appears, stop activation, deactivate runtime access, rotate affected credentials, preserve safe evidence, and remediate before another newly approved execution.

### 2026-08-11 audit result

The successful execution produced the expected event sequence:

```text
orchestration.request.received
orchestration.capability.resolved
orchestration.capability.invoking
email.send.attempted
email.send.completed
orchestration.capability.completed
```

Post-send verification passed:

- no recipient-bearing fields persisted;
- no clear subject persisted;
- no message body persisted;
- no credential-bearing fields persisted;
- sender metadata was present as permitted;
- successful CAP-007 completion evidence existed in the durable event store.

`Cap007EventAudit` is the runtime adapter between CAP-007 audit metadata and the canonical ORCH-001 event-store contract.

AWS SES errors are reduced to bounded safe error codes before durable audit. Provider exception message text is not retained.

## Phase 7 — Activation decision

**Activation date:** 2026-08-11

**Decision:** CAP-007 Version 0.1 is validated for the controlled pilot scope.

**Approved pilot scope:**

- provider `aws-ses`;
- region `us-east-1`;
- default sender `jason@teamaot.com`;
- explicit approval required for every send;
- active JKD-001 execute grant for the approved operator identity;
- idempotency key required;
- maximum one provider attempt;
- no automatic retry;
- no provider fallback;
- bounded recipient count;
- BCC disabled;
- durable safe audit required.

**Evidence record:** `07-Operations/CAP-007-Live-Pilot-Proof-2026-08-11.md`.

Production scope must remain no broader than the approved policy.

## Teams conversational integration

The successful activation proves the governed email capability and provider path, but it does not by itself make email available through Teams conversation ingress. As of the activation record, a Teams request such as "send me an email" is not yet translated into a governed `communication.email.send` request.

The next workstream is to connect Teams conversational intent to the existing CAP-007 capability through the Central Orchestrator. That work must preserve identity binding, recipient resolution, explicit approval, idempotency, policy gates, safe audit, and the existing one-attempt/no-fallback behavior. No direct Teams-to-SES shortcut is permitted.
