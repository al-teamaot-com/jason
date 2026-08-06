# ADR-003: Converge Autotask Live Reads on the Canonical Connector

**Status:** Proposed
**Decision owner:** Jason Architecture Authority

## Context

Jason currently contains two Autotask read paths:

1. the original CAP-001 live-read stack, which resolves three independent secret references through an external command and performs exact ticket validation; and
2. the connector framework, which resolves the single logical secret contract `autotask.readonly`, enforces registered read-only capabilities, and uses the dedicated Autotask AppRole.

Keeping both paths would preserve competing credential, transport, authorization, and audit architectures. Adding aliases for the legacy `autotask.api.*` references would make the immediate workflow run but would not remove that architectural split.

## Decision

The connector framework is the canonical Autotask execution path.

CAP-001's stronger controls must be preserved on that path:

- explicit live-read acknowledgement;
- exact ticket-number and company-boundary validation;
- requested-scope and allowed-scope equality;
- identity-first execution using principal, organization, client, and correlation context;
- deployment-readiness authorization before production use;
- one read-only provider request;
- redacted, hash-backed evidence outside the repository;
- evidence overwrite denial;
- safe failures that do not include provider response bodies or protected values.

The canonical credential contract is:

```text
autotask.readonly
  -> secret/data/connectors/autotask/production/read-only
  -> username, secret, integration_code
```

Capability code must not accept or construct provider paths, raw credentials, separate field-level logical aliases, or an alternate secret-broker command.

## Canonical operator boundary

The supported operator command is `tools/autotask_live_read.py`. It accepts business identity, scope, target, evidence, and explicit authorization parameters only. It does not accept:

- `--username-reference`;
- `--secret-reference`;
- `--integration-code-reference`;
- `--secret-command`.

The production-readiness closeout command invokes this same canonical operator boundary and records `autotask.readonly` as the credential contract.

## Migration sequence

1. Add a governed live-read service that composes the canonical `AutotaskConnector`.
2. Prove parity with the original CAP-001 safeguards through focused tests.
3. Bind the operator command and production-readiness workflow to the canonical service.
4. Perform one authorized non-client live validation and retain non-secret evidence.
5. Remove the legacy command secret broker, legacy transport, production transport, and `autotask.api.*` references after equivalence is proven.
6. Add regression tests that deny reintroduction of legacy Autotask secret references.

## Consequences

- Jason has one Autotask secret contract and one read-only connector boundary.
- CAP-001 retains its stronger validation and evidence semantics.
- Provider authentication, zone discovery, capability authorization, and secret resolution are not duplicated.
- Production readiness and direct operator use share the same execution path.
- Future Autotask capabilities build on the connector framework rather than creating capability-specific transports.

## Retirement criteria

The legacy CAP-001 Autotask transport may be removed only after:

- the canonical focused tests pass;
- the complete connector, CAP-001, release, and Kernel suites pass;
- check-only proves no secret or network activity;
- one governed live read succeeds through `autotask.readonly`;
- generated evidence contains no title, description, credential, token, or provider response body;
- production readiness invokes only the canonical path.
