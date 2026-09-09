# CAP-007 — Governed Email Send

**Version:** 0.1
**Status:** Pilot validated end-to-end
**Owner:** Jason Architecture Authority
**Canonical capability:** `communication.email.send`
**Initial provider:** `aws-ses`
**Review interval:** Quarterly and before any production mail-policy change

## Purpose

CAP-007 gives Jason one reusable, provider-neutral capability for sending email after the Central Orchestrator has established authority, policy, scope, and required approval. It replaces the mistaken CAP-004 identifier used during the initial implementation; CAP-004 remains reserved in the Capability Register for Backup Failure Investigation.

## Constitutional boundaries

CAP-007 may execute only through governed capability/provider resolution. It may not authorize itself, select its own provider, retrieve credentials before authorization, expose credentials in arguments/logs/prompts/evidence, invoke another agent directly, silently alter message content, or fall back to another transport.

The initial pilot is deliberately approval-required for every send. Broader policy may later distinguish internal and external recipients only after evidence supports that change.

## Canonical request

Accepted message fields are `to`, `subject`, optional `text_body`, `html_body`, `cc`, `bcc`, `reply_to`, and policy-controlled `from_address`. At least one body form is required. Provider credentials, region, provider endpoints, secret paths, and SDK configuration are prohibited request fields.

`OrchestrationRequest` carries an `idempotency_key`. CAP-007 requires a non-empty key before provider resolution. Version 0.1 enforces key presence and one execution attempt; it does not yet provide a durable duplicate-suppression store keyed by the value.

## Secret boundary

CAP-007 requests only the JKD-003 logical secret:

```text
aws_ses.sendmail
```

Approved fields are `access_key_id`, `secret_access_key`, and optional `session_token`. The capability does not know the OpenBao path. The runtime uses a dedicated AWS SES AppRole identity. The OpenBao resolver authenticates with that identity, reads the allow-listed KV v2 secret, revokes its short-lived OpenBao service token before returning, and exposes only the approved provider fields to CAP-007.

## Provider boundary

AWS SES is registered as the replaceable pilot provider `aws-ses`. The provider receives an already-authorized canonical email plus runtime-only credentials and returns non-secret provider metadata such as the SES message ID.

The pilot runtime configuration is:

```text
region = us-east-1
default_sender = jason@teamaot.com
provider = aws-ses
```

The AWS IAM identity is dedicated to the capability and limited to SES send authority for the approved TeamAOT sender identity.

## Runtime composition

The production runtime composition registers CAP-007 with the Kernel capability/provider registries, binds `communication.email.send` through `CapabilityInvokerRegistry`, uses `JKD001OrchestrationContextEnforcer` for real authority-context validation, resolves `aws_ses.sendmail` through `Cap007OpenBaoSecretBroker`, sends through `AwsSesTransport`, and records CAP-007 events through `Cap007EventAudit` into the durable orchestration event store.

The runtime container mounts the dedicated SES AppRole RoleID and SecretID read-only and runs under the existing non-root, read-only, no-new-privileges deployment boundary.

## Authorization and approval

The live pilot established a scoped JKD-001 authority grant for:

```text
subject = person-al
organization = aot
capability = communication.email.send
permission = execute
approval_required = true
status = active
```

Every pilot send still requires a formal approval that matches the request, requester, organization/client scope, capability, and validity window. A short-lived execution context is minted only after authority and approval validation.

## Auditability

CAP-007 emits audit-safe `email.send.attempted`, `email.send.completed`, and `email.send.failed` events. `Cap007EventAudit` translates CAP-007 metadata into the canonical ORCH-001 event-store contract without adding message content.

Allowed metadata includes execution/correlation identity, principal, organization/client scope, sender, recipient count, subject SHA-256, selected provider, provider message ID, and safe result/error codes.

Email bodies, recipient addresses, clear-text subjects, AWS credentials, OpenBao tokens, and AppRole secret material are prohibited from normal audit payloads. Runtime and CI validation confirmed those fields were absent from the successful live pilot evidence.

AWS SES provider exceptions are reduced to a bounded allow-list of safe error codes such as `EMAIL_SES_ACCESS_DENIED` or `EMAIL_SES_MESSAGE_REJECTED`; provider error message text is not persisted.

## Failure and retry behavior

CAP-007 is non-idempotent, requires an idempotency key at the governed capability contract, permits one execution attempt in Version 0.1, and fails closed. Automatic transport fallback and automatic retry are prohibited.

The first controlled live execution on 2026-08-11 failed before SES because the manual activation harness supplied AppRole file paths as strings instead of `Path` objects. The governed path recorded one failed attempt and did not retry. A no-send diagnostic then proved OpenBao resolution and AWS credential authentication. The corrected second execution used a new request, approval, execution context, correlation ID, and idempotency key and succeeded.

## Kernel registration

The reference registration is in:

```text
implementation/cap-007/src/jason_cap_007/kernel_registration.py
```

The capability and provider are both registered as pilot records. Resolution therefore requires explicit pilot authority, explicit capability approval, eligible provider resolution, a required idempotency key, and an auditable execution plan before invocation.

## Live pilot result — 2026-08-11

The controlled TeamAOT pilot completed successfully through the governed path:

- JKD-001 scoped authority and explicit per-request approval validated;
- a short-lived execution context was issued;
- Kernel resolution selected only `aws-ses`;
- JKD-003 resolved the dedicated SES credentials after authorization;
- AWS SES accepted exactly one message;
- SES returned message ID `0100019ff0656115-4a3b6d32-f1f5-4b7d-8e8a-31d6ea827ce2-000000`;
- the controlled mailbox received the message with subject `Jason CAP-007 Governed Email Pilot` at 06:37 America/New_York;
- durable audit contained the expected orchestration and CAP-007 completion events;
- audit verification found no recipient-bearing fields, clear subject, body, or credential-bearing fields.

The evidence record is `07-Operations/CAP-007-Live-Pilot-Proof-2026-08-11.md`.

## Teams integration status

CAP-007 itself is operational, but the Teams conversational path does not yet translate a user request such as "send me an email" into a governed `communication.email.send` orchestration request. Teams intent recognition, recipient resolution, approval interaction, request construction, and return-path messaging are the next integration workstream. This is an interface/orchestration gap, not an SES capability failure.

## Production activation gate

The controlled live-send and audit-inspection portions of the Version 0.1 activation gate were satisfied on 2026-08-11. Pilot scope remains conservative: explicit approval per send, approved sender only, bounded recipients, one attempt, no automatic retry, and no provider fallback.

Any expansion of production scope requires normal governance review and must not be inferred from the successful pilot alone.

## Definition of Done

CAP-007 Version 0.1 capability/provider activation is complete when the governed Kernel path resolves correctly, unauthorized and non-pilot requests fail closed, secret lifecycle validation is green, audit/redaction tests are green, a controlled live send succeeds under explicit approval, and the activation evidence is recorded.

The remaining work to make email available from Teams is tracked separately as conversational ingress/orchestration integration and does not change the validated CAP-007 provider boundary.
