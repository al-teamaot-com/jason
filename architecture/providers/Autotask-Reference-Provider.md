# Autotask Reference Provider

**Status:** Production validated  
**Role:** JIS reference provider

## Purpose

The Autotask provider demonstrates:

- OpenBao-backed logical secret resolution;
- dedicated read identity provisioning;
- runtime zone discovery;
- shared `ConnectorBase` lifecycle;
- declarative operation registry;
- governed generic entity access;
- installable CLI access;
- human-readable and JSON output.

## Logical Secret

`autotask.readonly`

Approved fields:

- `username`
- `secret`
- `integration_code`

## Provider-Specific Behavior

Autotask discovers the correct REST API zone at runtime using the zone-information endpoint.

## Generic Capabilities

- `autotask.entity.describe`
- `autotask.entity.get`
- `autotask.entity.query`

## Approved Entities

The implementation contains the authoritative approved entity allow-list.

## Production Validation

Production validation confirmed:

- secret resolution;
- AppRole authentication;
- zone discovery;
- known ticket retrieval;
- ticket-number query;
- CLI compact output;
- complete JSON output.

## Limitations

Provider API permissions remain dependent on the configured Autotask API user.

Write support requires a separate governed mutation phase and identity.
