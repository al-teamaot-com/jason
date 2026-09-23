# CAP-001 Autotask Live-Read Validation

**Status:** Foundation
**Owner:** Jason Architecture Authority

## Purpose

This component defines the controlled validation harness used before any CAP-001 Autotask provider is permitted to read production-shaped data.

The harness performs one exact, client-scoped, read-only ticket retrieval and creates a redacted evidence artifact outside the repository.

## Required safeguards

A validation request must include:

- an explicit live-read acknowledgement;
- one exact ticket number;
- one exact company identifier;
- one authorized validation scope;
- one new evidence output path outside the repository.

The harness fails before contacting Autotask when acknowledgement, identity, scope, or output requirements are not satisfied.

## Read-only boundary

The harness receives an `AutotaskTicketProvider`. That provider exposes ticket retrieval only. The validation layer defines no create, update, delete, attachment, note, time-entry, remediation, or workflow-transition operation.

## Evidence minimization

The generated JSON artifact records:

- provider and validation scope;
- ticket and company identities;
- retrieval timestamp;
- normalized configuration and requester references when present;
- source creation and update timestamps;
- SHA-256 hashes of title and description;
- a deterministic evidence hash;
- final validation status.

Ticket title and description content are never written to the evidence artifact.

## Fail-closed behavior

Validation is denied when:

- live-read acknowledgement is absent;
- the requested scope differs from the configured validation scope;
- ticket or company identity is blank;
- the output path is inside the repository;
- the output artifact already exists;
- the provider returns an ambiguous, malformed, mismatched, or cross-company ticket.

## Current limits

This foundation uses fixture-driven tests only. It does not include:

- live credentials;
- a command-line secret provider;
- live Autotask calls;
- client-production authorization;
- writes of any kind;
- attachment retrieval;
- ticket description output.

A separate governed increment must bind this harness to an approved Secrets Broker implementation and a designated non-client validation ticket before the first live read.
