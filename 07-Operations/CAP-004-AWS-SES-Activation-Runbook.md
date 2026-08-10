# CAP-004 AWS SES Activation Runbook

## Status

Pre-production activation procedure. This runbook does not authorize production email sending by itself.

## Objective

Activate Jason's provider-neutral `communication.email.send` capability using AWS SES as the initial governed execution provider while preserving Jason's identity, approval, policy, audit, and secret boundaries.

## Preconditions

Do not proceed with a live send unless:

- CAP-004 implementation validation is green;
- the Central Orchestrator and governed capability resolution path are operational;
- JKD-003 Secrets Broker is operational;
- INF-001 secret-provider readiness is green;
- INF-004 AWS SES Secret Onboarding is satisfied;
- an approved AWS SES region is documented;
- an approved sender identity is verified in SES;
- the operator has explicit authority for the live test;
- the test recipient is a controlled TeamAOT mailbox.

## Phase 1 — Kernel registration

Register the capability using the canonical capability identity:

```text
communication.email.send
```

Register the initial execution provider:

```text
aws-ses
```

The capability must not hard-code provider selection. Governed resolution must select `aws-ses` before the CAP-004 invoker executes.

Initial policy should be conservative:

- TeamAOT internal recipient only for the first live test;
- one approved default sender;
- BCC disabled;
- external/client recipients approval-required;
- bulk or campaign behavior denied;
- recipient count bounded;
- no provider credentials in arguments.

## Phase 2 — Secret onboarding

Canonical logical secret:

```text
aws_ses.sendmail
```

Approved OpenBao provider path:

```text
secret/data/connectors/aws-ses/production/sendmail
```

Required secret fields:

```text
access_key_id
secret_access_key
```

Optional:

```text
session_token
```

Credential values must be entered through the standard `provider_secret.py` lifecycle after the generalized provider catalog supports `aws_ses`.

Do not create a separate SES provisioning script.

Expected lifecycle shape once catalog support is merged:

```bash
python3 tools/provider_secret.py status aws_ses
python3 tools/provider_secret.py create aws_ses
python3 tools/provider_secret.py verify aws_ses
```

The create command must prompt securely for credential values and must not echo them. Verification must report metadata/result only.

## Phase 3 — Non-secret provider configuration

Configure outside OpenBao:

```text
provider_id = aws-ses
region = <approved AWS region>
default_sender = <approved verified sender>
```

Do not put the region or sender address into the credential payload solely for convenience.

## Phase 4 — Check-only validation

Run CAP-004 through the Central Orchestrator in check-only mode with a controlled synthetic request.

Expected result:

- authority context validated;
- capability resolves;
- provider resolves to `aws-ses`;
- policy decision is visible;
- no AWS network call occurs;
- no secret is resolved;
- no message is sent.

Any secret access during check-only is a defect and blocks activation.

## Phase 5 — Controlled live send

Use one explicitly approved internal TeamAOT recipient and a benign test message.

Example canonical arguments:

```json
{
  "to": ["<controlled TeamAOT mailbox>"],
  "subject": "Jason CAP-004 governed email test",
  "text_body": "This is an authorized CAP-004 delivery test."
}
```

Do not include access keys, region, provider ID, endpoint, vault path, or secret name in user-controlled message arguments.

Expected result:

- orchestrator authorizes execution;
- governed resolution selects `aws-ses`;
- CAP-004 validates the message and sender policy;
- JKD-003 resolves `aws_ses.sendmail` only after authorization;
- SES accepts the message;
- CAP-004 returns an SES message ID and recipient count;
- the secret lease is revoked;
- the controlled mailbox receives the message.

Provider acceptance is not equivalent to final delivery. Delivery/bounce telemetry is a separate capability concern and should not be silently inferred by CAP-004.

## Phase 6 — Audit inspection

Inspect the resulting audit/evidence records.

Allowed metadata includes:

- execution ID;
- correlation ID;
- principal ID;
- organization/client scope;
- capability name;
- provider ID;
- recipient count;
- subject digest;
- SES message ID;
- result/error code;
- attempts and timestamps.

The following must not appear:

- AWS access key value;
- AWS secret key value;
- session token;
- OpenBao token;
- AppRole SecretID;
- full email body;
- hidden credential-bearing exception text.

If any secret value is exposed, stop CAP-004 activation, deactivate the runtime credential, rotate affected credentials, preserve safe evidence, and remediate before retrying.

## Phase 7 — Activation decision

After successful controlled validation, record:

- approver;
- date/time;
- tested sender;
- tested recipient class;
- SES region;
- provider message ID;
- audit evidence references;
- known limitations;
- credential rotation interval;
- next review date.

Production scope must remain no broader than the approved policy.

## Current blocker

The CAP-004 implementation and no-network tests exist, but live secret provisioning should not proceed until the existing generalized `provider_secret.py` lifecycle catalog is extended to support `aws_ses` through the same canonical operator interface used by other providers.

This is intentional: introducing a separate `sendmail` or SES credential script would violate Jason's capability/resource-driven architecture and JKD-003 lifecycle invariant.
