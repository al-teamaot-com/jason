# Service-originated release approval: regular Owner Teams identity

**Status:** Proposed V5 source-only policy; **not activated**, no production freeze or V4 policy change. Tracking #2300. This is an architectural design candidate for the Owner to review through the existing governed Teams procedure.

## Verified identity and problem

- Regular working Teams recipient: `al@teamaot.com`, Entra object `bee80bdc-ffb0-4c50-b453-c09d4d411f5f`.
- Separate administrative account: `al_admin@teamaot.com`, Entra object `c848022d-e13b-4457-84b0-e2f5c00dcaf6`.
- Current V4 policy `admin_approver_separated` demands the latter Entra identity for signed privileged release decisions. The admin account's Microsoft Teams Graph `list_chats` call returned a licensing-related 403. This does **not** establish that the admin account should be licensed or that ordinary Teams delivery can substitute for privileged approval.
- Existing V4 policy remains authoritative until an exact-revision, signed, separately governed release activates a new version.

## Narrow V5 proposal

Separate **roles** rather than imposing a Teams license on the administrative account:

1. Jason's independently authenticated release-manager **service identity** requests one exact reviewed release (requester `svc-jason-release-manager`).
2. The specifically bound regular Microsoft Teams identity acts as **human Owner approver** for that release, with original signed challenge and exact SHA/scope/rollback attached. This is NOT authorizing an arbitrary regular technician to approve their own actions. A human-requested client/device operation must still satisfy its separate original technician approval boundary.
3. The administrative Entra account remains separate for identity management and other administrator operations, without automatically gaining or losing provider permissions.
4. A signed Teams card never directly authorizes deployment. The existing release manager independently checks native release eligibility, production freeze exception, candidate SHA, rollback SHA, current source and immutable receipts, then executes a single gated transaction.
5. A versioned V5 policy must be independently reviewed and signed before activation; **do not edit the live V4 0600 policy**, manually forward a privileged card to a regular user, impersonate the admin or forge an approval.

The source-only `service_originated_owner_approval_policy.py` is a validator; it deliberately has **no** Teams sender, callback, identity mutation, live registration, file installer, freeze modifier, or Release Manager invocation. Its success returns `native_mutation_authorized=false`.

## Remaining implementation required before activation

- Connect this policy to the canonical Release Manager's versioned approval issuer, original authenticated Teams callback, exact admin-vs-owner identity check and root-protected policy hash, without weakening V4 or universal approval.
- Define a separately authorized one-time transition from installed V4 to the new version. The transition itself needs a valid owner approval through an existing governed high-risk procedure; source code does not bootstrap authorization.
- Require runtime, MCP, host and mobile card sender all to agree on the version, exact regular Entra object and service requester before sending a card.
- Complete source/regression/host release tests, protected-main PMV3 integration gate, root preproduction release evidence, exact SHA and rollback, signed Teams approval, native one-transaction unfreeze and two independent post-change acceptance cycles.
- Retain the existing engineering Owner pause, global production freeze and automatic promotion hold unless specifically authorized and verified.

## Source tests

`PYTHONPATH=implementation:implementation/runtime_service/src python3 -m pytest -q implementation/runtime_service/tests/test_service_originated_owner_approval_policy.py`

This document makes no assertion that V5 is deployed or that the eventual release is currently eligible.
