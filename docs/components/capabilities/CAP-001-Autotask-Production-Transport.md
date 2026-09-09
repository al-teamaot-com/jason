# CAP-001 — Autotask Production Transport Binding

**Version:** 0.1  
**Status:** Building  
**Capability Stage:** Recommend  
**Owner:** Jason Architecture Authority

## Purpose

This increment binds the CAP-001 Autotask read adapter to a concrete HTTPS JSON client and Autotask zone discovery while preserving the existing recommendation-only and read-only safety boundary.

## Delivered behavior

- HTTPS-only JSON requests.
- Standard-library production HTTP client.
- Bounded retries for transient network failures and retryable HTTP conditions.
- Bounded request timeouts.
- Brokered Autotask username, secret, and integration-code references.
- In-memory construction of authentication headers.
- Autotask zone discovery using the brokered username.
- Validation that discovered API URLs use HTTPS.
- Exact ticket-number and company-ID query execution through the existing transport.
- Redacted terminal network failures.
- Deterministic mocked tests with no live network access.

## Authority boundary

The production binding may retrieve one exact Autotask ticket through the previously defined provider-neutral and client-scoped boundaries. It does not grant broader authority.

The caller must already possess an authorized client identity. The downstream adapter independently confirms the returned Autotask company identity and ticket identity before CAP-001 evidence is produced.

## Secrets handling

Credentials are represented only by secret references. The transport obtains values through the `SecretBroker` boundary at request time.

The implementation does not:

- read credentials from source files;
- embed credentials in configuration;
- write credentials to logs;
- expose underlying transport exceptions;
- persist constructed request headers.

A production Secrets Broker implementation remains responsible for enforcing caller identity, capability scope, audit logging, expiry, and revocation.

## Retry and failure behavior

Retries are bounded and apply only to transient network failures and retryable HTTP conditions. Permanent client errors are not retried indefinitely.

Terminal failures return a generic transport error that does not include URLs containing query data, headers, credentials, or raw provider response bodies.

## Deferred scope

This increment does not include:

- live credentials;
- live-client testing;
- Autotask write operations;
- attachment retrieval;
- ticket-note retrieval;
- automatic remediation;
- unrestricted provider search;
- direct environment-variable credential loading;
- provider-specific secrets storage implementation.

## Validation standard

Before merge, this increment requires:

1. focused production transport tests;
2. existing Autotask HTTP transport and adapter tests;
3. complete CAP-001 tests;
4. complete Kernel tests;
5. full release validation;
6. strict documentation build;
7. whitespace validation;
8. a clean tracked branch.
