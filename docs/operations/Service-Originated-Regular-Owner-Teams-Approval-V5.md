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

## 2026-11-09 guarded runtime implementation progress

- An isolated V5 source path now extends the existing `MobileReleasePolicy` schema, exact-requester ID, signed original Teams callback, exact Entra recipient routing in `composition.py` and retention of the one-use card challenge; V4 remains the installed default and a V4 runtime rejects V5 policy.
- Unlike a mere notification redirect, the V5 callback checks the originally signed regular Owner Entra object and its matching active, unscoped Jason identity; the admin account, wrong tenant, disabled identity and client-scoped identity are denied.
- Native V4 separate administrative authorization remains in place even when the Owner signs a V5 release card. Passing callback tests does not grant a release transaction.
- Source-only tests: V5 role guards and signed Teams callback plus V4 original tests and deployment-contract tests pass locally. The first dedicated CI revision omitted canonical runtime dependencies and was corrected; only latest-head CI can be treated as authoritative.
- **Not activated:** current installed V4 root release consumer, host policy, production-bound deployment mode and preproduction/rollback admission are not yet V5-capable. No real Teams card or signed Owner decision has been issued. Further governed source integration and a separate valid V4-to-V5 policy transition are still required.

## V5 candidate and native source review (2026-11-09)

- Reviewed **source-only**, noncanonical policy proposal: `config/mobile-release-approval-policy-v5-candidate.json`, SHA256 `0cac875022375c05550ecb5f313ba59559e3b3b01dbac4870189f58b319cf411`. The currently canonical `config/mobile-release-approval-policy.json` is still V4; root-installed policy is not changed.
- Native host source now has independent V5 mode/schema validation, the exact `svc-jason-release-manager` requester assertion and separate immutable regular/admin Entra bindings. The release consumer requires the original signed Teams card challenge and performs a fresh exact regular Entra binding/identity check **without email fallback**.
- The runtime deployment source recognizes only an explicitly selected reviewed V5 policy. V4 remains default, and V5 callback success by itself carries **no native deployment authority**.
- Original V4 admin-only grant administration remains separated under the V5 runtime configuration; ordinary technician actions do not gain admin rights.
- Native source tests verify invalid policy, untrusted sender, wrong role, revoked/inactive identity, missing one-use challenge, and regression of the original V4 signed-card route. Local focused tests PASS, but these are not proof of live provider-backed approval.
- Remaining release-scope risk: this branch touches shared native release and runtime scripts and MUST be reconciled with active parallel PRs and rerun root rollback/preproduction checks against protected main before release. Protected PMV3 integration remains locked, and no valid signed Teams V5 transition approval exists. **Do not change source policy to V5 merely to trigger issuance.**

## Parallel source integration reconciliation

The V5 source feature additionally touches native Release Manager and deployment files. Reviewed overlapping PRs include #2378 (signed receipt persistence), #2382 (native promotion/rollback safety), #2355 (staff note deployment source), #2279 (superseded signed release decisions), plus #2336, #2384, #2377, #2373, #2282, #2177, #2269, #2392, #2391. The reviewed hunks are separately scoped, but exact protected-main integration must preserve every independent feature and rerun contract tests. This coordination is **not** integration-gate approval or permission to merge while the PMV3 release queue is locked.

## Native V4-to-V5 staged policy transition and rollback regression (2026-11-09)

The existing native `stage_mobile_release_approval_policy`/ `restore_mobile_release_approval_policy` routines already implement atomic private 0600 policy staging, original-byte backup and restoration **inside the governed release manager transaction**. The V5 candidate therefore reuses those routines; it adds no direct production file editing path. New `tools/tests/test_v5_native_policy_transition.py` verifies V4-to-V5 staging, crash retry and byte-identical restore; V4 rollback backup digest conflict; failure after a staged write restores exact V4 bytes; and runtime policy SHA/mode mismatch prevents acceptance.

This test found and fixed an existing retry weakness: a replaced rollback backup matching the candidate could be accepted on replay. The native stage now requires the backup to match the **immutable previously recorded prior-policy digest, candidate digest, candidate mode, and backup path**, failing closed on tampering or absent lineage. This is a source-only correction; no live policy was staged or restored.

The current protected-main V4 test fixture in `test_owner_reviewed_release_activation.py` still asserts the old canonical V2 policy. Its 8 failures when run against current main are stale fixture assumptions, not V5 transition acceptance. The same broader run passed 242 other tests and 5 subtests. Do not describe the whole legacy suite as green until that separate fixture migration is resolved under governance.

**Bootstrap remains blocked:** even with reversible native policy staging, the release manager may stage V5 **only after** a legitimate V4-governed exact-SHA release authorization; the engine may not grant permission to its own transition. The connected admin Teams identity cannot currently receive the privileged signed Teams card, while the regular account does not satisfy V4. No policy transition, Teams decision, production release or frozen-worker restart has occurred.
