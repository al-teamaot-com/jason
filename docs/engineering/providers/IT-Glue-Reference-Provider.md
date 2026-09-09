# IT Glue Reference Provider

**Status:** Identity provisioned; production credential validation pending
**Role:** Second JIS reference provider

## Purpose

The IT Glue provider demonstrates that JIS patterns apply beyond Autotask.

It uses:

- shared `ConnectorBase` lifecycle;
- declarative operation registry;
- generic entity gateway;
- explicit resource allow-list;
- OpenBao-backed logical secret resolution;
- dedicated least-privilege AppRole.

## Logical Secret

`it_glue.readonly`

Approved field:

- `api_key`

The API base URL is non-secret provider configuration.

## Generic Capabilities

- `it_glue.entity.get`
- `it_glue.entity.query`

## Approved Entities

- Organizations
- Configurations
- FlexibleAssets
- Documents
- Contacts
- Locations

Passwords and arbitrary provider paths are not approved.

## Production Validation Required

Complete the following before declaring the provider production validated:

- store the approved API key in OpenBao;
- query Organizations;
- retrieve a known approved entity;
- confirm least-privilege access;
- confirm controlled failure behavior;
- confirm no credential disclosure.

## Mutation Boundary

Existing mutation planning does not constitute live write enablement.

Live write support requires a separate governed identity, approval, execution, verification, and rollback phase.
