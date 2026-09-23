# CAP-001 Canonical Autotask Live-Read Command

**Status:** Operational pilot
**Owner:** Jason Architecture Authority

## Purpose

This component provides the governed operator boundary for one read-only Autotask ticket lookup through the canonical connector framework.

The supported command is:

```text
tools/autotask_live_read.py
```

It uses the single logical secret contract `autotask.readonly`. Capability code and operator input do not contain OpenBao paths, raw credentials, field-level secret aliases, or alternate secret-broker commands.

## Operator boundary

The command requires:

- one unique Autotask ticket number;
- the requested scope and separately authorized scope;
- principal, organization, and correlation identity context;
- an evidence path outside the repository;
- either `--check-only` or explicit `--live-read` authorization.

The technician does not provide an Autotask company ID. The connector derives the authoritative company boundary from the unique ticket returned by Autotask.

## Canonical credential contract

```text
autotask.readonly
  -> secret/data/connectors/autotask/production/read-only
  -> username, secret, integration_code
```

The connector authenticates to OpenBao using the dedicated protected Autotask read-only AppRole files. Those files remain `root:root` with mode `0600`, so governed live execution requires the appropriate privileged runtime identity. Protected values must never be displayed, logged, or stored in evidence.

## Configuration check

`--check-only` validates required business identifiers, identity context, scope alignment, deployment readiness, and the evidence destination.

It does not:

- read AppRole material;
- resolve the logical secret;
- contact OpenBao;
- perform Autotask zone discovery;
- contact Autotask;
- create an evidence artifact.

## Live-read safeguards

A live request is denied unless `--live-read` is present. The canonical service additionally enforces:

- deployment-readiness approval;
- exact lookup by the supplied unique ticket number;
- exactly one provider result;
- returned ticket-number equality;
- provider-derived company boundary;
- requested-scope and allowed-scope equality;
- identity-first principal, organization, and correlation context;
- evidence output outside the repository;
- evidence overwrite denial;
- redacted, hash-backed evidence;
- safe failures that exclude provider response bodies and protected values.

## Evidence

Approved evidence may include non-secret metadata such as:

- ticket number;
- provider-derived company ID;
- timestamps;
- logical secret name;
- capability name;
- hashes of title and description;
- evidence integrity hash;
- protected-value exposure status.

Evidence must not contain raw title, description, username, API secret, integration code, token, password, AppRole value, or provider response body.

## Read-only authority

The command invokes only the registered `autotask.ticket.search` capability. It defines no create, update, delete, attachment, note, time-entry, remediation, or workflow-transition operation.

## Verified pilot execution

The first governed canonical live read completed successfully on 2026-08-06 using ticket `T20260805.0064`.

Evidence:

```text
/home/al/Jason-Evidence/Autotask/autotask-live-read-T20260805.0064-20260806T162842Z.json
```

The execution used `autotask.readonly`, derived the company boundary from Autotask, generated mode-`0600` redacted evidence, and left OpenBao healthy.

## Retired architecture

The former CAP-001-specific HTTP transport, ticket provider, production transport, command secret broker, field-level secret references, and company-ID operator input are retired. They must not be reintroduced as compatibility paths.
