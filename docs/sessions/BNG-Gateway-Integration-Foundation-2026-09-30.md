# BNG Gateway Integration Foundation — 2026-09-30

## Purpose

Record the initial Project Jason BNG Payment Gateway integration foundation without storing or reproducing any provider secret value.

## Credential foundation

- Lifecycle provider key: `bng_gateway`
- Logical secret: `bng_gateway.runtime`
- OpenBao KV v2 path: `secret/data/connectors/bng-gateway/production/runtime`
- Durable field contract: `api_key`
- Runtime policy/AppRole: `jason-bng-gateway-secret-read`
- Protected AppRole artifacts: `/var/lib/jason/runtime-secrets/openbao/bng-gateway-approle/`

The BNG credential was provisioned through Jason's canonical `tools/provider_secret.py` lifecycle. The successful create operation wrote KV version 1, created the dedicated AppRole identity, persisted no runtime token, printed no secret value, and revoked the temporary administrative token.

The subsequent canonical `verify bng_gateway` operation returned `status=pass`, `field_contract_valid=true`, `runtime_access_active=true`, `runtime_token_persisted=false`, and `secret_values_printed=false`.

An earlier create attempt failed closed at OpenBao administrative userpass authentication with HTTP 400. No BNG API key prompt or KV write occurred on that failed attempt.

## Provider documentation discovery

Jason's host successfully retrieved the public BNG Payment Gateway Integration Portal at `https://secure.bngpaymentgateway.com/merchants/resources/integration/integration_portal.php` with HTTP 200.

The portal documents at least the following integration surfaces relevant to Jason:

- Payment API, with documented POST URL `https://secure.bngpaymentgateway.com/api/transact.php`
- Query API, including methodology, variables, example response, examples, and downloadable documentation
- Customer Vault operations
- recurring billing operations
- invoicing operations
- transaction operations including capture, void, refund, and update
- rate-limit behavior

The Payment API documentation states that `security_key` is an API Security Key assigned to a merchant account and that new keys can be generated in the merchant control panel under `Settings > Security Keys`.

## Current operational boundary

Only the credential foundation is live. No `provider.bng-gateway` System Registry provider entity or Jason BNG execution capability should be declared operational until a connector is implemented and provider-backed validation succeeds.

The preferred first implementation is the BNG Query API as a non-mutating evidence plane. Payment, refund, void, recurring-billing, Customer Vault, and other write-capable operations should be registered later as separate governed capabilities with exact payload/target binding and post-action verification.
