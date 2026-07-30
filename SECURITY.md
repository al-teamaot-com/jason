# Security Policy

Project Jason coordinates sensitive MSP operational context. Security defects may affect client isolation, authority, evidence integrity, auditability, or provider access.

## Reporting

Do not disclose suspected vulnerabilities, credentials, client information, or exploit details in a public issue.

Report privately to the designated AOT security and Jason architecture owners using an approved internal channel. Include the affected component, observed behavior, reproduction conditions, potential client scope, and any evidence references that can be shared safely.

## Security invariants

The following conditions are treated as material security defects:

- cross-client data, context, evidence, or action leakage;
- execution without a valid scoped execution context;
- authority inferred from technical access alone;
- agent-to-agent invocation outside central orchestration;
- external content interpreted as trusted instruction;
- secrets or credentials written to logs, responses, fixtures, or source control;
- historical evidence changed without an attributable superseding record;
- approval reused after a material action change;
- quality or policy gates bypassed silently;
- terminal or rejected workflows resumed without an authorized new invocation.

## Supported phase

CAP-001 Version 0.1 is a pre-pilot reference implementation. It is read-only and recommendation-only. It must not be connected to production provider credentials until identity validation, secret handling, persisted audit, deployment isolation, and operational approval requirements are implemented and reviewed.
