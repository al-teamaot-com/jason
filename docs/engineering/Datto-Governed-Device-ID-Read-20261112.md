# Datto RMM governed numeric device-ID read — preproduction

Date: 2026-11-12
Status: Developer change only. No production deployment authorization.

## Problem
The J-Assist Chrome extension observes URLs like
`https://vidal.rmm.datto.com/web-remote/1717088`; the Datto RMM
REST `GET /v2/device/{uid}` uses a separate provider-issued UUID.
A production governed read of `endpoint.device.read(resource_id=1717088)`
returned HTTP 404. The same workstation was found through an exact
hostname search as `Al-Samsung`, native UID
`710e63d6-caca-d830-697a-81250b0a8321`, AOT site UID
`9bb56523-cade-4ffb-bc34-696e788f0f4c`.
A hostname match is not authoritative proof that the URL's numeric ID
corresponds to that UUID.

## Isolated read-only change
Retain the single existing governed `endpoint.device.read` capability
and read-only provider identity/tenant boundaries. When its exact
`resource_id` is a positive ASCII decimal Datto device ID, the Datto
connector uses the documented alternate **GET
`/api/v2/device/id/{deviceId}`**. UUID selectors retain existing
`GET /api/v2/device/{deviceUid}` behavior.

On a numeric lookup, require the provider's returned `id` or `deviceId`
to match the requested decimal selector *exactly*, and require a
provider-issued durable UUID. A mismatch, incomplete, ambiguous, malformed
or unavailable response fails closed. The bounded MCP read projection exposes
`provider_device_id` **separately** from native `resource_id`, along
with ordinary device/site fields. A sibling isolated J-Assist authorizer
requires both independently provided identifiers and a fresh matching
AOT site, online/nondeleted/nonsuspended device check on each operation.

## Verification and boundaries
- Existing Datto connector regression tests, new exact routing and
  mismatched-ID tests; MCP projection tests for flat and nested responses
- Separate draft PR with no automations/endpoint commands, ticket core or
  production mutating capabilities modified
- Provider-specific actual numeric ID endpoint behavior must still be
  tested through governed read after separately authorized release;
  synthetic tests cannot prove external provider schema
- The Owner approved a bounded **nonproduction** J-Assist screenshot pilot,
  not deployment of this connector change to production. Do not merge or
  promote until current protected-main CI, review, exact-SHA release
  authorization and rollback are independently satisfied.
