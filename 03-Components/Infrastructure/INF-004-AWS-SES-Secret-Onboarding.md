# INF-004 — AWS SES Secret Onboarding

**Status:** Foundation
**Owner:** Jason Architecture Authority
**Consumes:** JKD-003 Secrets Broker, INF-001 Secret Provider Foundation
**Supports:** CAP-004 Governed Email Send

## Purpose

INF-004 defines the approved secret-provider onboarding contract for the initial AWS SES execution provider used by `communication.email.send`.

AWS SES credentials are operational provider credentials. They are not capability configuration, request arguments, prompt content, environment variables, repository secrets, or orchestration metadata.

## Logical secret

CAP-004 requests only this provider-neutral logical name:

```text
aws_ses.sendmail
```

The capability must never request or know the OpenBao storage path.

## Initial OpenBao binding

For the current production OpenBao deployment, the approved provider path is:

```text
secret/data/connectors/aws-ses/production/sendmail
```

The runtime provider identity is dedicated to AWS SES sendmail and must not share a persistent provider-wide token with other connectors.

Recommended identifiers:

```text
policy_name: jason-aws-ses-sendmail
role_name: jason-aws-ses-sendmail
connector_identity: aws-ses-sendmail
credential_dir: /opt/jason/bootstrap/secrets/openbao/aws-ses-sendmail-approle
```

## Secret schema

Required fields:

```text
access_key_id
secret_access_key
```

Optional field:

```text
session_token
```

No other fields are permitted by CAP-004 Version 0.1.

AWS region, default sender address, SES endpoint behavior, provider ID, sender policy, and recipient policy are non-secret configuration and must remain outside the secret payload.

## Runtime invariant

The normal runtime path is:

```text
Authorized CAP-004 execution
  -> JKD-003 Secrets Broker
  -> logical secret aws_ses.sendmail
  -> provider-specific OpenBao AppRole
  -> short-lived OpenBao service token
  -> one allow-listed KV v2 read
  -> SES transport receives only approved secret fields
  -> provider send attempt
  -> secret lease/service token revoked
```

The Central Orchestrator must never receive or persist the SES credential values.

## AWS credential authority

The AWS identity represented by this secret must be dedicated to Jason email delivery and limited to the minimum SES send permissions required by the approved deployment.

It must not receive unrelated AWS administrative authority.

Static AWS access credentials are permitted only as the initial compatibility mechanism. The deployment should prefer workload identity or short-lived AWS credentials when the hosting environment supports them safely. Static credentials require documented rotation and retirement criteria.

## Provisioning rules

1. Credential values are entered only through the governed secret lifecycle ceremony.
2. Values must never be pasted into GitHub, documentation, tickets, chat, command history, or CAP-004 arguments.
3. The provider lifecycle must use the canonical JKD-003 create/update/verify/rotate/deactivate/reactivate model.
4. KV v2 create/update must use compare-and-set semantics.
5. Verification must confirm field presence and runtime resolution without printing values.
6. Runtime identity and AWS API credential rotation are separate operations and must not be conflated.
7. Deactivation of the OpenBao runtime identity does not claim to revoke the AWS credential itself.

## Readiness gate

CAP-004 live execution remains blocked until all of the following are verified:

- `aws_ses.sendmail` is represented in the canonical provider-secret lifecycle catalog;
- the OpenBao path exists through governed provisioning;
- the dedicated AppRole/policy is present;
- the canonical resolver returns only the approved fields;
- the SES AWS identity has least-privilege send authority;
- the configured SES region is known and non-secret;
- the configured sender identity is approved and verified with SES;
- CAP-004 check-only succeeds without secret resolution;
- audit validation confirms no credential values or message bodies are persisted.

## Definition of Done

INF-004 is complete when the standard `provider_secret.py` lifecycle supports `aws_ses` without introducing a provider-specific operator script, runtime resolution succeeds through JKD-003, safe verification prints no values, and credential disablement/rotation procedures are tested.
