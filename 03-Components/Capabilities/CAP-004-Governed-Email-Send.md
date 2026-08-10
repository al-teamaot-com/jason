# CAP-004 — Governed Email Send

**Version:** 0.1
**Status:** Foundation implementation
**Owner:** Jason Architecture Authority
**Primary provider:** AWS SES
**Review interval:** Quarterly and before any production mail-policy change
**Retirement criteria:** Replaced only by an approved provider-neutral communication capability with equivalent or stronger governance, audit, identity, and secret controls

## Purpose

CAP-004 gives Jason a provider-neutral capability for sending email after the Central Orchestrator has established authority, policy, scope, and any required approval.

The capability is intentionally named by business operation rather than provider:

```text
communication.email.send
```

AWS SES is the initial execution provider. It is not part of the constitutional capability contract and may be replaced without changing the capability name or caller contract.

## Constitutional boundaries

CAP-004 SHALL NOT:

- authorize its own execution;
- bypass the Central Orchestrator;
- select an execution provider independently;
- retrieve credentials before governed resolution succeeds;
- place credentials in request arguments, prompts, logs, evidence, memory, or audit payloads;
- allow an agent to invoke another agent directly;
- silently change sender identity, recipients, subject, or message body;
- treat successful provider submission as proof of recipient delivery;
- silently fall back to SMTP, Microsoft Graph, local sendmail, environment variables, or files when the approved provider fails.

CAP-004 SHALL:

- execute only after governed capability/provider resolution;
- request credentials through JKD-003 Secrets Broker using a logical secret name;
- validate a narrow canonical message contract;
- fail closed on malformed addresses, missing sender policy, provider mismatch, or secret-resolution failure;
- return only non-secret provider metadata;
- generate durable audit-safe execution metadata through the orchestrator boundary;
- preserve exact organization/client and correlation context;
- support check-only validation without sending mail or resolving secrets.

## Canonical request contract

The capability accepts the following arguments:

```text
to             required list of recipient addresses
subject        required non-empty subject
text_body      optional text body
html_body      optional HTML body
cc             optional list of addresses
bcc            optional list of addresses
reply_to       optional list of addresses
from_address   optional only when policy explicitly permits caller selection
```

At least one of `text_body` or `html_body` is required.

Provider credentials, AWS region, secret paths, access keys, secret keys, session tokens, provider endpoints, and SDK configuration are prohibited request fields.

## Sender authority

The default sender is deployment policy, not caller input. Initial AOT deployments should configure one approved Jason sender identity and may later add narrowly scoped sender profiles.

If `from_address` is supplied, the execution binding must verify that the requested sender is explicitly allowed by policy for the principal, organization/client scope, and capability invocation. Caller-supplied sender values are never authoritative by themselves.

## Recipient governance

Recipient authorization belongs to Jason policy and approval, not to the SES adapter.

Recommended initial policy posture:

- internal TeamAOT recipients: permitted only for principals already authorized for CAP-004;
- client or external recipients: approval-required until a narrower governed policy is deliberately adopted;
- bulk or broadcast mail: denied in Version 0.1;
- BCC: permitted only when explicitly allowed by policy;
- automated loops, repeated retries, or campaign behavior: denied unless separately designed and approved.

## Secrets contract

CAP-004 requests the stable logical secret name:

```text
aws_ses.sendmail
```

For the initial OpenBao-backed deployment the secret payload contains only credential material:

```text
access_key_id
secret_access_key
session_token   optional
```

AWS region, default sender address, provider ID, endpoint selection, and other non-secret deployment settings remain provider configuration and MUST NOT be stored in the secret payload merely for convenience.

The secret SHALL be provisioned and operated through the existing JKD-003 lifecycle and canonical OpenBao AppRole pattern. CAP-004 never knows the OpenBao path.

Long-lived static AWS credentials are an initial compatibility mechanism, not a constitutional dependency. Workload identity or short-lived AWS credentials SHOULD replace them when the deployment platform supports that safely. Rotation and retirement criteria are mandatory.

## Provider contract

Initial provider ID:

```text
aws-ses
```

The provider receives an already authorized canonical email message plus a short-lived secret lease. It returns only:

```text
provider
message_id
accepted
```

Provider response data must not include credentials or full message bodies in audit metadata.

## Failure model

CAP-004 fails closed when:

- governed resolution is not `resolved`;
- the resolved provider is not the provider bound to the invoker;
- no recipient is present;
- the subject is empty;
- neither text nor HTML body is present;
- a recipient or sender address is malformed;
- a prohibited request field is supplied;
- the sender is outside the configured allow-list;
- secret resolution fails or returns an invalid schema;
- the provider call fails.

Failures expose stable safe error codes, not credential values or provider exception text that may contain sensitive material.

## Audit events

The Central Orchestrator remains the primary audit boundary. CAP-004/provider-specific audit metadata may include:

- execution ID;
- correlation ID;
- principal ID;
- organization/client context;
- capability name/version;
- resolved provider ID;
- sender profile identifier;
- recipient count;
- subject SHA-256 digest or redacted subject classification when needed;
- provider message ID;
- success/failure code;
- attempts;
- timestamp.

Message bodies and secret values are not audit payloads by default.

## Initial implementation

The reference implementation lives under:

```text
implementation/cap-004/
```

It contains:

- provider-neutral message validation;
- a Secrets Broker resolver protocol;
- an AWS SES transport adapter;
- an orchestrator-compatible capability invoker;
- no-network tests using synthetic secret and transport implementations.

The AWS SDK is loaded only by the production SES transport. Tests do not require network access or AWS credentials.

## Production activation gate

CAP-004 is not production-ready merely because the code exists. Production activation requires:

1. Register `communication.email.send` in JKD-006 Capability Registry.
2. Register `aws-ses` in JKD-005 Execution Provider Registry.
3. Add execution policy for sender, recipient scope, risk, and approval requirements.
4. Provision `aws_ses.sendmail` through JKD-003/OpenBao without exposing values.
5. Verify the SES sending identity and deployment region.
6. Bind the CAP-004 invoker in the Central Orchestrator.
7. Run check-only tests.
8. Run one explicitly approved live test to a controlled TeamAOT mailbox.
9. Confirm audit records contain no body or secret material.
10. Document rotation, disablement, and provider-credential retirement procedures.

## Definition of Done

CAP-004 Version 0.1 is complete when:

- the provider-neutral capability contract is approved;
- no caller or agent can supply provider credentials;
- secret resolution uses only `aws_ses.sendmail` through JKD-003;
- AWS SES is an execution provider, not capability logic;
- malformed or unauthorized messages fail closed;
- check-only performs no secret access and no provider call;
- no-network unit tests pass;
- the capability is registered through the governed Kernel path;
- a controlled live-send test succeeds only after explicit approval;
- secret values and message bodies are absent from normal audit output;
- credential rotation and disablement are tested.
