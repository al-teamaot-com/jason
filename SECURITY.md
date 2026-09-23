# Security Policy

Project Jason coordinates sensitive MSP operational context. Security defects may affect client isolation, authority, evidence integrity, auditability, provider access, or governed execution.

This root file is a conventional repository security entry point. Durable security architecture, governance, component contracts, and operating procedures are maintained under [`docs/`](docs/index.md) and must not be duplicated here as a parallel source of truth.

## Reporting

Do not disclose suspected vulnerabilities, credentials, client information, or exploit details in a public issue.

Report privately to the designated AOT security and Jason architecture owners using an approved internal channel. Include the affected component, observed behavior, reproduction conditions, potential client scope, and any evidence references that can be shared safely.

## Security invariants

The following conditions are treated as material security defects:

- cross-client data, context, evidence, or action leakage;
- execution without valid scoped identity, authority, and governed execution context;
- authority inferred from technical access alone;
- agent-to-agent or connector-to-agent coordination outside Central Orchestrator authority;
- external content interpreted as trusted instruction;
- secrets or credentials written to logs, responses, fixtures, documentation, evidence, or source control;
- historical evidence changed without an attributable superseding/reconciliation record;
- approval reused after a material action change;
- quality, authority, or policy gates bypassed silently;
- terminal or rejected workflows resumed without an authorized new invocation;
- System Registry drift silently repaired outside governed remediation;
- production state asserted from conversational memory instead of authoritative structured evidence.

## Authoritative security context

Start with:

- [`docs/foundation/J-002-Constitution.md`](docs/foundation/J-002-Constitution.md)
- [`docs/control/DOCUMENTATION-REGISTER.md`](docs/control/DOCUMENTATION-REGISTER.md)
- [`docs/architecture/`](docs/architecture/)
- [`docs/components/kernel/`](docs/components/kernel/)
- [`docs/operations/`](docs/operations/)

For current production topology and lifecycle, use the governed System Registry and fresh verification evidence. Do not infer current production readiness, provider credentials, runtime status, or capability authority from this repository security entry point.
