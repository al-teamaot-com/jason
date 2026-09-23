# CAP-001 — Autotask HTTP Transport

**Version:** 0.1  
**Status:** Building  
**Owner:** Jason Architecture Authority

## Purpose

This component provides the read-only HTTP boundary behind the CAP-001 Autotask ticket provider.

It performs an exact ticket query constrained by the authorized Autotask company identity and returns decoded ticket objects to the provider adapter.

## Allowed behavior

- Resolve credential values through a broker-compatible interface.
- Build request headers in memory.
- Call the Autotask ticket query endpoint over HTTPS.
- Filter by exact ticket number and company ID.
- Enforce a bounded timeout.
- Validate status codes and response shape.

## Prohibited behavior

- No create, update, or delete operations.
- No credentials stored in source files.
- No unbounded searches.
- No credential values in errors or evidence.
- No direct agent-to-agent communication.

## Request contract

The transport calls:

```text
GET {base_url}/v1.0/Tickets/query
```

The query contains both the exact `ticketNumber` and authorized `companyID`. The provider adapter independently verifies the returned identities and requires exactly one result.

## Fail-closed behavior

The transport rejects non-HTTPS endpoints, missing identities, transport exceptions, non-200 responses, malformed response objects, missing item collections, and non-object items.

## Current boundary

The implementation uses injected broker and JSON HTTP client protocols. Tests use deterministic fakes and make no network calls.

Deferred work includes production HTTP binding, Kernel broker binding, zone discovery, bounded transient retry, safe telemetry, sandbox verification, and separately approved live-client testing.
