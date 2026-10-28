# P0: Autotask dynamic ActionTypes native ID zero and governed live read acceptance

## Observed release outcome (2026-10-28)

The v13 Autotask metadata-driven generic reader first reached production in
controlled release `release-bc2dcaff25c60535`. It did not close: the native
Production Manager automatically returned all affected surfaces to the
independently verified v10 last-known-good revision
`8559cbb84aba2d9acb636ac57fbdab9f00dbda78`, with
`rollback_verified=true` and no rollback errors. The one-time owner freeze
exception was restored.

The original Microsoft-authenticated, same-human receipt set contained all
five v11 acceptance classes: ticket count 72, page 1 of 50, cursor page 2 of
22, exact ticket ID read and generic Projects read. The v13-specific
`ActionTypes` query did not produce a passing dynamic-schema receipt.

The Autotask `ActionTypes` resource has a legitimate enum-like record with
`id: 0`. The former v13 acceptance code erroneously reused the strictly
positive ID validator for ordinary ticket/Projects records on this distinct
enum-like resource. This would reject even a real authorized
`service.entity.search` returning `[{"id":0,"name":"..."}]`.
The canary's generic failure message obscured which of its six classes failed.

## Scoped correction

For **only** the mandatory source-bound `service.entity.search` request
`{"entity":"ActionTypes","page_size":1,"select":["id","name"]}`,
both the MCP one-call verification and metadata-only acceptance receipt now
allow `id=0` but require:

- one row maximum;
- exact `id` and `name` keys and no extra provider fields;
- an integer ID (not boolean) greater than or equal to zero;
- a nonempty string `name` (never included in the acceptance receipt);
- the existing successful, authenticated, approved source-bound read and
  same-human, exact-SHA/nonce/time/profile release binding.

No ticket or Projects ID permission is weakened: both still require strictly
positive exact IDs. Denied, malformed, wrong-entity, wrong-shape and excessive
responses fail closed. No provider API mutations or unfiltered data release.

## Verification and deployment conditions

The correction has independent unit tests for actual zero-ID dynamic evidence
and MCP one-call canary acceptance plus negative tests for negative IDs,
boolean/non-integer IDs, missing names, unrequested fields and denied results.
Run the established native release, source-bound profile v13, exact SHA,
CCC review, concurrent-work review and rollback prerequisites without
changing or disabling any of those gates.

**Release may close only on a real connected AOT human's successful v13
canary**, including ticket count, exact 50+cursor pagination, exact ID,
Projects and a genuine selected ActionTypes read. If the record query fails
or the metadata receipt is absent, rollback is mandatory. The source tests
are not substituted for live read acceptance.
