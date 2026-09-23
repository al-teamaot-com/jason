# ADR-003: Converge Autotask Live Reads on the Canonical Connector

**Status:** Accepted and implemented
**Decision owner:** Jason Architecture Authority
**Implemented:** 2026-08-06

## Context

Jason contained two Autotask read paths:

1. the original CAP-001 live-read stack, which resolved three independent secret references through an external command and performed exact ticket validation; and
2. the connector framework, which resolves the single logical secret contract `autotask.readonly`, enforces registered read-only capabilities, and uses the dedicated Autotask AppRole.

Keeping both paths would preserve competing credential, transport, authorization, and audit architectures. Adding aliases for the legacy `autotask.api.*` references would make the immediate workflow run but would not remove that architectural split.

The original operator boundary also required the technician to supply an Autotask company ID even though Autotask ticket numbers are unique and the ticket record already contains the authoritative company boundary. Requiring both values created unnecessary operator work and invited inconsistent duplicate input.

## Decision

The connector framework is the canonical Autotask execution path.

CAP-001's stronger controls are preserved on that path:

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

## Implementation result

The migration sequence was completed:

1. A governed live-read service was added around the canonical `AutotaskConnector`.
2. Focused tests proved parity with the original CAP-001 safeguards.
3. The operator command and production-readiness workflow were bound to the canonical service.
4. Provider-specific company-ID input was removed.
5. A governed live validation succeeded on 2026-08-06 using ticket `T20260805.0064`.
6. Redacted mode-`0600` evidence was retained at `/home/al/Jason-Evidence/Autotask/autotask-live-read-T20260805.0064-20260806T162842Z.json`.
7. The legacy command secret broker, HTTP transport, production transport, ticket provider, validation path, and their legacy-only tests were removed.
8. Regression tests deny reintroduction of the retired operator options.

All connector, CAP-001, release, and Kernel suites passed after retirement. Release validation and strict documentation builds were approved.

## Consequences

- Jason has one Autotask secret contract and one read-only connector boundary.
- CAP-001 retains its stronger validation and evidence semantics.
- Provider authentication, zone discovery, capability authorization, and secret resolution are not duplicated.
- Production readiness and direct operator use share the same execution path.
- Technicians provide only the ticket number and do not need an internal Autotask company ID.
- The provider remains the single source of truth for ticket ownership.
- Future Autotask capabilities build on the connector framework rather than creating capability-specific transports.

## Constitutional interpretation

This decision implements the principle "do not put a band-aid on it; fix it." Jason did not add compatibility aliases or preserve two permanent execution paths. The replacement was built, tested, validated live under governance, and then the obsolete implementation was retired.

## Reintroduction rule

The retired CAP-001 transport, secret-command interface, field-level Autotask secret aliases, and company-ID operator input must not be reintroduced. Any future need not supported by the canonical connector must be addressed by extending the connector and capability registry under normal governance.
