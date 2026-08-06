# ADR-003: Converge Autotask Live Reads on the Canonical Connector

**Status:** Proposed
**Decision owner:** Jason Architecture Authority

## Context

Jason currently contains two Autotask read paths:

1. the original CAP-001 live-read stack, which resolves three independent secret references through an external command and performs exact ticket validation; and
2. the connector framework, which resolves the single logical secret contract `autotask.readonly`, enforces registered read-only capabilities, and uses the dedicated Autotask AppRole.

Keeping both paths would preserve competing credential, transport, authorization, and audit architectures. Adding aliases for the legacy `autotask.api.*` references would make the immediate workflow run but would not remove that architectural split.

The original operator boundary also required the technician to supply an Autotask company ID even though Autotask ticket numbers are unique and the ticket record already contains the authoritative company boundary. Requiring both values creates unnecessary operator work and invites inconsistent duplicate input.

## Decision

The connector framework is the canonical Autotask execution path.

CAP-001's stronger controls must be preserved on that path:

- explicit live-read acknowledgement;
- unique ticket-number lookup that must return exactly one ticket;
- provider-derived company boundary from the returned ticket;
- requested-scope and allowed-scope equality;
- identity-first execution using principal, organization, and correlation context;
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

## Provider-identifier boundary

Operator interfaces expose business identifiers, not provider implementation identifiers, whenever the provider can resolve them deterministically.

For CAP-001, the technician supplies the unique Autotask ticket number. The connector:

1. queries by that ticket number only;
2. requires exactly one result;
3. verifies the returned ticket number;
4. derives `companyID` from the returned ticket;
5. records the discovered company boundary and its source in non-secret evidence; and
6. requires any subsequent ticket-related operation to remain bound to that discovered company context.

The operator is not required to locate or enter `--company-id`.

## Canonical operator boundary

The supported operator command is `tools/autotask_live_read.py`. It accepts business identity, scope, target, evidence, and explicit authorization parameters only. It does not accept:

- `--company-id`;
- `--username-reference`;
- `--secret-reference`;
- `--integration-code-reference`;
- `--secret-command`.

The production-readiness closeout command invokes this same canonical operator boundary and records `autotask.readonly` as the credential contract and `autotask-ticket` as the company-boundary source.

## Migration sequence

1. Add a governed live-read service that composes the canonical `AutotaskConnector`.
2. Prove parity with the original CAP-001 safeguards through focused tests.
3. Bind the operator command and production-readiness workflow to the canonical service.
4. Remove provider-specific company-ID input and derive the boundary from the unique ticket.
5. Perform one authorized non-client live validation and retain non-secret evidence.
6. Remove the legacy command secret broker, legacy transport, production transport, and `autotask.api.*` references after equivalence is proven.
7. Add regression tests that deny reintroduction of legacy Autotask secret references or company-ID input.

## Consequences

- Jason has one Autotask secret contract and one read-only connector boundary.
- CAP-001 retains its stronger validation and evidence semantics.
- Provider authentication, zone discovery, capability authorization, and secret resolution are not duplicated.
- Production readiness and direct operator use share the same execution path.
- Technicians provide only the ticket number and do not need an internal Autotask company ID.
- The provider remains the single source of truth for ticket ownership.
- Future Autotask capabilities build on the connector framework rather than creating capability-specific transports.

## Retirement criteria

The legacy CAP-001 Autotask transport may be removed only after:

- the canonical focused tests pass;
- the complete connector, CAP-001, release, and Kernel suites pass;
- check-only proves no secret or network activity;
- one governed live read succeeds through `autotask.readonly` using ticket-number-only input;
- generated evidence contains no title, description, credential, token, or provider response body;
- generated evidence records the provider-derived company boundary;
- production readiness invokes only the canonical path.
