# CAP-001 — Autotask Read Adapter Foundation

**Version:** 0.1
**Status:** Foundation in progress
**Owner:** Jason Architecture Authority
**Applies to:** CAP-001 provider-backed pilot preparation

## 1. Purpose

This component implements the first concrete provider behind the CAP-001 provider-neutral `TicketProvider` boundary.

It reads one exact Autotask ticket for one already-authorized client and normalizes the result for the CAP-001 evidence collector.

The adapter is intentionally read-only and contains no provider credentials, HTTP client, retry policy, write operation, or live-client configuration.

## 2. Authority Boundary

The adapter does not establish authority. It receives an authorized `client_id` from the orchestrated CAP-001 execution context and must preserve that boundary.

It must:

1. query by exact ticket number and authorized company identity;
2. require exactly one result;
3. verify the returned ticket number independently;
4. verify the returned company identity independently;
5. reject cross-client, ambiguous, missing, or malformed results;
6. return only the normalized provider-neutral ticket fields.

## 3. Read-Only Transport Contract

The adapter depends on a minimal transport capability:

```python
query_tickets(
    *,
    ticket_number: str,
    company_id: str,
) -> list[dict[str, Any]]
```

The transport is responsible for approved authentication, Autotask zone selection, API communication, timeouts, retries, and secret retrieval.

The transport contract exposes no create, update, delete, note, attachment, status, queue, or assignment method.

## 4. Normalization Contract

The adapter maps the following Autotask fields:

| Autotask field | Provider-neutral field | Requirement |
|---|---|---|
| `ticketNumber` | `external_id` | Required |
| `companyID` | `client_id` | Required |
| `title` | `title` | Required |
| `description` | `description` | Required |
| `createDate` | `created_at` | Required |
| `lastActivityDate` | `updated_at` | Optional |
| `configurationItemID` | `configuration_item_id` | Optional |
| `contactID` | `requester_identity_id` | Optional |

The provider-neutral evidence collector subsequently creates deterministic, SHA-256-backed evidence and marks ticket content as untrusted as instruction.

## 5. Failure Behavior

The adapter fails closed when:

- the requested ticket or client identity is blank;
- Autotask returns zero or multiple tickets;
- the returned ticket identity differs;
- the returned company identity differs;
- any required field is missing or empty.

A returned company mismatch is treated as a client-boundary violation and raises `PermissionError`.

## 6. Deferred Scope

This foundation does not yet include:

- a live Autotask HTTP transport;
- OpenBao or other credential retrieval;
- zone discovery;
- attachments or ticket notes;
- company, contact, asset, service, agreement, or queue enrichment;
- Datto RMM or IT Glue evidence;
- provider writes;
- automatic remediation;
- live-client pilot approval.

Each deferred capability requires its own governed increment and tests.

## 7. Acceptance Criteria

The foundation is complete when:

1. one exact ticket is normalized through the provider-neutral contract;
2. queries include both ticket and authorized client identities;
3. returned identities are independently verified;
4. ambiguous and cross-client results fail closed;
5. required fields are enforced;
6. optional fields remain optional;
7. focused, CAP-001, Kernel, release, and strict documentation tests pass.

## 8. References

- `03-Components/Capabilities/CAP-001-Professional-Ticket-Investigation.md`
- `03-Components/Capabilities/CAP-001-Provider-Pilot-Foundation.md`
- `implementation/cap-001/src/jason_cap_001/adapters.py`
- `implementation/cap-001/src/jason_cap_001/provider_evidence.py`
