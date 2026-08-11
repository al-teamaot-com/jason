# CAP-007 — Governed Email Send

**Version:** 0.1
**Status:** Pilot foundation
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

## Secret boundary

CAP-007 requests only the JKD-003 logical secret:

```text
aws_ses.sendmail
```

Approved fields are `access_key_id`, `secret_access_key`, and optional `session_token`. The capability does not know the OpenBao path. Secret leases are runtime-only and revoked after use.

## Provider boundary

AWS SES is registered as the replaceable pilot provider `aws-ses`. The provider receives an already-authorized canonical email plus a short-lived secret lease and returns non-secret provider metadata such as the SES message ID.

## Auditability

CAP-007 emits audit-safe `email.send.attempted`, `email.send.completed`, and `email.send.failed` events. Allowed metadata includes execution/correlation identity, principal, organization/client scope, sender, recipient count, subject SHA-256, selected provider, provider message ID, and safe result/error codes.

Email bodies, recipient addresses, clear-text subjects, AWS credentials, OpenBao tokens, and AppRole secret material are prohibited from normal audit payloads. CI tests enforce these redaction invariants.

## Failure and retry behavior

CAP-007 is non-idempotent, requires an idempotency key at the governed capability contract, permits one execution attempt in Version 0.1, and fails closed. Automatic transport fallback and automatic retry are prohibited.

## Kernel registration

The reference registration is in:

```text
implementation/cap-007/src/jason_cap_007/kernel_registration.py
```

The capability and provider are both registered as pilot records. Resolution therefore requires explicit pilot authority, explicit capability approval, eligible provider resolution, and an auditable execution plan before invocation.

## Production activation gate

Production activation requires green CI, approved Kernel registration/policy, verified SES sender and region, `aws_ses.sendmail` provisioned through the canonical JKD-003 lifecycle, controlled check-only validation, one explicitly approved internal TeamAOT test send, and post-send audit inspection proving no secret or body leakage.

## Definition of Done

CAP-007 Version 0.1 is complete when the governed Kernel path resolves correctly, unauthorized and non-pilot requests fail closed, secret lifecycle validation is green, audit/redaction tests are green, a controlled live send succeeds under explicit approval, and credential rotation/deactivation has been verified.
