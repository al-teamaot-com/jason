# Jason Audience and Communication Policy Engine

This module is the deterministic gate between generated or human-authored content and every outbound communication connector.

## Responsibilities

- classify and normalize recipient audiences;
- enforce organization and client isolation;
- validate permitted channels;
- prevent disclosure of internal notes and raw diagnostics;
- flag sensitive information;
- require audience- and purpose-specific approvals;
- identify mixed-audience messages that should be separated;
- support optional rewriting without making AI authoritative.

## Decision flow

```text
Communication draft
    -> recipient and scope validation
    -> audience profile selection
    -> channel and disclosure policy
    -> sensitive-content checks
    -> approval evaluation
    -> allow / revise / approve / block
    -> optional transformation
    -> full review repeated
    -> communication connector
```

## Important rule

An AI transformer may rewrite a message, but it cannot approve delivery, relax policy, add commitments, or bypass client isolation. Every transformed message must be submitted to `AudiencePolicyEngine.review()` again.

## Initial capabilities

- `communication.audience.classify`
- `communication.content.review`
- `communication.content.transform`
- `communication.recipient.validate`
- `communication.approval.evaluate`

## Planned integrations

- Microsoft Graph email;
- Teams messaging and approvals;
- SMS/MMS;
- voice notifications;
- Telegram;
- client portal messaging;
- Autotask correspondence synchronization.

## Production work still required

- authoritative contact and organization resolution;
- configurable client-specific audience profiles;
- DLP and attachment inspection provider;
- jurisdiction-aware voice and recording rules;
- approved sender identity registry;
- mass-communication controls;
- persistent communication and approval records;
- policy versioning and audit integration.
