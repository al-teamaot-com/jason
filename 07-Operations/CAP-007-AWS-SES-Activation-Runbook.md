# CAP-007 AWS SES Activation Runbook

## Status

Controlled live pilot completed successfully on 2026-08-11. Teams conversational integration also completed successfully for the approved pilot scope on 2026-08-11. This runbook does not authorize broader production email sending by itself.

## Objective

Activate Jason's provider-neutral `communication.email.send` capability using AWS SES as the initial governed execution provider while preserving Jason's identity, approval, policy, audit, orchestration, and secret boundaries.

## Preconditions

Do not proceed with a live send unless:

- CAP-007 implementation validation is green;
- the Central Orchestrator and governed capability resolution path are operational;
- JKD-003 Secrets Broker is operational;
- the secret-provider readiness record is green;
- the AWS SES secret onboarding is satisfied;
- an approved AWS SES region is documented;
- an approved sender identity is verified in SES;
- the operator has explicit authority for the live test;
- the test recipient is controlled and appropriate for the approved pilot scope;
- if invoked through Teams, the Teams identity and Microsoft directory-enrichment path have passed a no-send validation first.

These preconditions were satisfied for the 2026-08-11 controlled pilot and subsequent Teams conversational proof.

## Phase 1 — Kernel registration

Register `communication.email.send` and the pilot provider `aws-ses` through the canonical Kernel registry services. The reference registration is `implementation/cap-007/src/jason_cap_007/kernel_registration.py`.

Version 0.1 pilot policy is deliberately conservative:

- explicit pilot authority required;
- explicit approval evidence required for every send;
- one approved default sender;
- BCC disabled unless policy explicitly changes;
- bulk or campaign behavior denied;
- recipient count bounded;
- idempotency key required;
- maximum one provider attempt;
- no automatic retry or provider fallback;
- no provider credentials in arguments.

A future policy may permit low-risk internal mail without per-message approval only after operating evidence and governance review support that change.

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

Use one explicitly approved controlled recipient and a benign test message. Do not include access keys, region, provider ID, endpoint, vault path, or secret name in message arguments.

Expected result:

- orchestrator authorizes execution;
- governed resolution selects `aws-ses`;
- CAP-007 validates sender/message policy;
- JKD-003 resolves `aws_ses.sendmail` only after authorization;
- SES accepts the message;
- CAP-007 returns safe provider-result metadata;
- the runtime OpenBao token is revoked after the secret read;
- the controlled mailbox receives the message.

SES acceptance is not proof of final delivery. Mailbox receipt, bounce telemetry, or delivery telemetry are separate evidence concerns.

### 2026-08-11 first pilot execution

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

## Phase 7 — Teams conversational identity validation

Before using Teams as the front door for a consequential send, prove the identity path without sending email.

Required path:

```text
Authenticated Teams tenant/object
-> Jason identity binding
-> validated Microsoft client boundary
-> JKD-003/OpenBao Microsoft certificate credential
-> MSAL application token
-> Microsoft Graph exact-user lookup
-> resolved mailbox on bound Jason principal
```

Requirements:

- `me` means the currently authenticated Microsoft user;
- transport-supplied email must not override governed directory resolution;
- a static stored email must not silently override a configured live directory reader;
- Graph failure must fail closed;
- Microsoft access token must remain in memory and must not be printed or persisted;
- the Graph lookup must be read-only and exact to the authenticated object;
- no downstream consequential provider may be invoked during this validation.

### 2026-08-11 pilot evidence

The running `jason-runtime` container resolved:

```text
tenant_id: f7054323-d52b-4863-8c2f-1898f0b6077c
object_id: bee80bdc-ffb0-4c50-b453-c09d4d411f5f
resolved_email: al@teamaot.com
```

The proof confirmed the validated boundary and OpenBao credential path and explicitly confirmed that no email was sent.

## Phase 8 — Teams conversational send

Only after the no-send identity proof is green may the approved pilot perform a live Teams conversational send.

The allowed architecture is:

```text
Teams
-> OpenClaw transport
-> Jason trusted ingress
-> governed identity binding
-> governed conversation action intent
-> JKD-001 authority and per-request pilot approval evidence
-> Central Orchestrator
-> CAP-007
-> JKD-003/OpenBao
-> AWS SES
-> deterministic Teams response
```

No direct Teams-to-SES path is permitted. No workflow-specific sendmail script is permitted. OpenClaw may transport the request but does not authorize or execute the capability directly.

### 2026-08-11 live proof

The authenticated operator sent:

```text
send me an email
```

Jason resolved the authenticated principal to `al@teamaot.com`, completed the governed send, and returned success after execution. The mailbox then showed receipt with subject:

```text
Test email from Jason
```

Operator-retained mailbox evidence:

```text
File: Test email from Jason.msg
SHA-256: be2b2239dd5449f0ee085fb007bf3fb921f885e46a9b51b7a416b7ad9cef9c53
Size: 113664 bytes
Observed receipt: approximately 08:31 America/New_York on 2026-08-11
```

The binary `.msg` is not stored in Git.

## Phase 9 — Activation decision

**Activation date:** 2026-08-11

**Decision:** CAP-007 Version 0.1 and the Teams conversational integration are validated for the controlled pilot scope.

**Approved pilot scope:**

- capability `communication.email.send`;
- provider `aws-ses`;
- region `us-east-1`;
- default sender `jason@teamaot.com`;
- explicit authority required;
- per-request approval evidence required;
- pilot authenticated-imperative self-approval policy only as currently documented;
- idempotency key required;
- maximum one provider attempt;
- no automatic retry;
- no provider fallback;
- bounded recipient count;
- BCC disabled;
- durable safe audit required;
- Teams may act as authenticated conversational ingress but not execution authority;
- `me` is resolved from the authenticated Microsoft identity through the governed directory boundary.

**Evidence records:**

- `07-Operations/CAP-007-Live-Pilot-Proof-2026-08-11.md`
- `08-Session-Records/Teams-CAP-007-End-to-End-Operational-Proof-2026-08-11.md`

Production scope must remain no broader than the approved policy.

## Pilot governance limitation

The pilot may materialize an authenticated Teams imperative as explicit per-request JKD-001 approval evidence for the same authenticated principal. This is formal self-approval evidence for the approved pilot. It is not an independent approver class, not a bypass of the approval system, and not authorization to generalize self-approval to higher-risk capabilities.

Any broader approval model requires normal governance review.

## Recovery and failure rules

- If Teams identity cannot be authenticated or bound, deny the action.
- If the Microsoft boundary is absent or not validated, deny the action.
- If Graph lookup fails, deny the action; do not use stale or invented email.
- If OpenBao secret resolution fails, deny the action; do not fall back to environment/file/provider credentials.
- If CAP-007 fails after invocation, do not blindly retry the non-idempotent send.
- A later send requires a fresh governed execution unless approved replay semantics are explicitly implemented.
- If the deployed OpenClaw bridge differs from the repository version, reconcile the deployment before consequential testing.

## Constitutional alignment

This runbook preserves the Jason Constitution by maintaining human governance, provider-neutral capability abstraction, integration-before-innovation, separation of responsibilities, explainability, auditability, institutional memory, reversibility, and living documentation.

The full constitutional review for the live conversational proof is recorded in:

`08-Session-Records/Teams-CAP-007-End-to-End-Operational-Proof-2026-08-11.md`.
