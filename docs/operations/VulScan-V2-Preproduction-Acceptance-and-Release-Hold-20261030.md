# VulScan V2 — Preproduction Acceptance and Release Hold
**Date:** 2026-10-30
**PR:** https://github.com/al-teamaot-com/jason/pull/2178
**Status:** PREPRODUCTION SOURCE ACCEPTED WITH LIVE INTEGRATION HOLDS — NOT PRODUCTION ELIGIBLE

## What is verified
1. Deterministic Day 16 / Day 21 and independently verified urgent-review decisions; no autonomous patch approval or installation.
2. Reuse of Jason's canonical Teams communication service, existing audience policy, durable outbox, idempotency, fresh evidence recheck, unknown-delivery reconciliation and exact owner promotion gate.
3. Microsoft's public release history and exact KB article retrieved through the allowlisted TLS-only reader for one Windows 11, one Windows 10 and one Windows Server KB. In each case the original release date and bounded official article summary were verified. Known issues were not inferred.
4. One real client-managed Datto endpoint was read through active Jason **governed read-only** capabilities `endpoint.device.search`, `endpoint.device.read` and `endpoint.patch.search`; exact KB5127648 returned NOT_APPROVED, with provider release date 2026-10-13, matching Microsoft's release-history date. Verified the live provider response is `evidence.items` and updated the collector accordingly. No provider secrets or identifying device values are retained here.
5. Scoped Datto API read-only surfaces `endpoint.patch.policy.search` and `management.site.patch.search` are implemented on the branch; complete pagination and device/site identity guards have fixture and local regression tests.
6. Dormant shadow workflow composition evaluates verified site scope, Datto patch/policy facts, Microsoft KB metadata and notification eligibility. Mocked Teams and Datto transports prove no direct sends or ticket mutations in shadow. The old ten-day V1 ticket-aging default remains until the V2 supervisor passes the release gate.
7. Isolated worktree acceptance on the Jason development host passed the targeted VulScan, Datto connector, autonomy worker, and canonical Teams tests after resolving live evidence-shape and all-site prevalidation defects. The ordinary production checkout and running services were not modified.

## Unverified and blocking
1. **Live source authority:** Neither `endpoint.patch.policy.search` nor `management.site.patch.search` is presently active in the live Jason MCP read catalog. New code must first pass protected integration and be staged safely through the governed release process. Do not use direct Datto API/shell credentials to bypass that requirement.
2. **Provider payload acceptance:** Actual site-level patch payload and policy-assignment pagination schema must be independently verified through the newly governed capabilities. Fixture-only acceptance is not enough.
3. **Full customer coverage:** The authenticated, complete Datto-site-to-client mapping and any persisted owner decline/defer decisions must be verified for all scoped clients. A partial or ambiguous inventory must fail closed, not be presented as fleet-wide.
4. **Live communications:** Owner recipient identity, exact workflow communication grant, and actual Teams arrival/receipt have not been accepted for this feature. A gateway receipt is not human delivery.
5. **Protected CI:** Every required check must pass on the *exact* eventual release SHA. GitHub overlap acknowledgments have been reviewed for PRs #2164, #2177, #2125, #2128 and #2126; actual integration/merge must preserve their functionality and rerun tests.
6. **Production baseline/breaker:** Unprivileged Production Manager readback shows last-known-good revision `cb76e14f9f42ec4f914b10967db1d408c271c1aa` and circuit-breaker **open** since 2026-10-30T18:34:28Z due to continuous-production-drift/failed-system-unit. A later desired-state drift snapshot reports PASS, but this does not clear the protected breaker. No unapproved reset or service restart is permitted.

## Safe completion sequence
1. Resolve the remaining protected CI and source conflict checks on the reviewed draft PR without changing production.
2. Through Production Manager, reconcile protected main and the exact source SHA, full change inventory, image/runtime/host health, root-protected release breaker and verified last-known-good rollback. An unmerged draft branch is *not* an eligible production candidate.
3. Prepare an isolated read-only preproduction runtime using the governed provider mapping; independently accept the exact site patch payload, policy list, site/client binding, and documented deferrals.
4. Run multiple scheduled shadow cycles in one exact approved scope. Validate Day 15/16/21 results, duplicate and uncertain delivery behavior, policy changes and disappearance of superseded KBs, with zero endpoint, ticket or Teams mutations.
5. Only after source and permission acceptance, present an exact protected-main candidate SHA and freshly verified rollback SHA for owner deployment authorization. Deploy disabled; perform separately authorized owner-only Teams delivery pilot before enabling automatic notification.
6. Stop and fail closed if any audit, authorization, provider source, data completeness, protected CI, or release breaker check fails.

## Release authorization
**NOT GRANTED.** No merge, production deploy, service restart, Datto policy update, ticket mutation, Teams message, breaker reset or autonomous activation is authorized by this document.

## Completion estimate
Source and fixture acceptance are substantially complete; genuine provider-backed acceptance and release authority are still outstanding. Do not report 100% until the complete authoritative workflow is proven.


## Additional read-only development acceptance — 2026-10-30
- Verified source contract corrected: missing/not-up-to-date owner defer/decline evidence now blocks V2 before reading the managed fleet; it cannot be interpreted as `review_pending`. This guard also rejects wrong KB, tenant/client, policy, device UID, partial coverage and decision clock without provenance.
- Authoritative `review_pending` must attest that the separately approved, complete scoped decision source contains **no** current exception; `deferred`, `declined` and `superseded` are each explicit suppressions. Existing queued notifications reread this exact evidence immediately before any send.
- The dormant workflow still has **no configured live signed owner-decision provider**. This is an additional explicit acceptance dependency, not proof of live operational coverage.
- The currently coded Datto device-policy and site-patch URL variants disagree with parts of Datto's own public English/German API references and 15.1 release notes. The public Swagger/OpenAPI document returned HTTP 500. Do not claim a tested live path or switch to guessing a URL. Accept each route and page schema via the approved governed provider in controlled staging before any promotion.
- Targeted negative tests added for missing reader, absent/old/mismatched disposition, no full-scope proof, deferral suppression and queued-event recheck. Production feature activation remains disabled.


## Current additional acceptance gap — policy causation (2026-10-30)

The Datto endpoint's `installStatus=NOT_APPROVED` is an **effective device state**, not a statement that each assigned patch policy disapproved that KB. Global/site policy decisions and device-level overrides may differ. The earlier draft created an incorrect KB x all-assigned-policy cross product. It now requires a second injected, governed, current **per-KB per-policy attribution** source and rejects missing/incomplete/stale/mismatched or unattributable policy evidence before creating a reminder. Exact client, site, device, policy, KB and source provenance are retained to the downstream collector. Existing owner defer/decline attestation remains separately required.

Current official Datto English API v15.2 lists `/v2/device/{deviceUid}/policies/patch-management` and `/v2/site/{siteUid}/patches`. The connector is aligned with those documented paths, but not yet verified against authorized provider responses. Release notes and search-cache variations are NOT proof of a compatible provider response. No Datto credentials or private provider APIs were accessed outside Jason governance.

Required controlled provider acceptance is **not complete**: exact route/paging/auth; device UID in site inventory (or a revised verified enumeration approach); effective status vs KB-specific policy evidence; source of signed Owner exceptions; no cross-client counts; V1 ten-day migration; canonical Teams delivery and independent receipt; exact SHA release eligibility. All must pass before disabled-first deployment. Owner global production freeze and automatic promotion incident hold remain in place.


## Additional preproduction checks — 2026-10-30 (no production changes)

- **Bounded large-site collection:** The generic read adapter caps completed collections at 1,000 rows. The VulScan site inventory contract allows at most 6,000 per run. The new Datto *site-patch read only* branch uses a 6,000-row, maximum-24-page bound, leaving every other provider collection's generic limit unchanged. A simulated 1,100-record site required five complete pages; oversized declared 6,001-row collection was rejected before further provider probes. Focused connector and inventory tests passed. Live site-patch provider-backed acceptance remains unverified.
- **Live exact Datto-to-Autotask company cross-check:** Jason's existing governed `management.site.search` for an authorized Riggins test site returned precisely one complete site record with a durable Autotask company ID. The existing governed `service.company.read` for that ID returned an active company with matching numeric ID and name. This proves the **existing one-site relationship read**, not whole-fleet completeness or the new site-patch/policy capabilities; those remain missing from live MCP. No direct provider API or credentials used.
- **Full runtime suite: 7 Datto component scope/classification failures**, all reproduced against protected-main baseline `b9ded6e242183a18f3299e05e5b517a0d8375ad9` in the same isolated environment. Thus these failures are pre-existing at the feature's base and not demonstrated V2 regressions. They still require independent reconciliation to fully satisfy all-repository CI; do not silently waive them.
- **Protected GitHub CI:** Latest available exact-head workflows were queued; no GitHub Actions success recorded yet. Remote hosted-runner availability is an external CI gate.
- **Owner production freeze and automatic promotion incident hold still active**; no new capabilities activated, no Teams owner notification sent, no merge or deployment performed.


## Exact GitHub change-integration reconciliation — October 30, 2026

The last CI result for SHA `c082a27a83bb1842cd09003bec52a15ab5fa6ba9` had eight successful workflows and one `Validate Jason` repository-hygiene failure. The failure was an explicit change-integration acknowledgment gate, **not** a failed VulScan feature test. Concurrent PR #2175 touches the same Datto RMM validation workflow as this PR #2178.

I reviewed the exact baseline-to-head workflow diffs for both PRs against protected main `b9ded6e242183a18f3299e05e5b517a0d8375ad9`. PR #2175 adds a component-input-contract test path, a component-scope test path, a component-contract compile step, and the matching component-contract test invocation. PR #2178 adds its separate VulScan V2 read-only test path and six focused read-only validation test invocations. These are additive changes in distinct places; neither PR requires removing or overriding the other's tests. Final integration must preserve **both** sets and rerun the normal Datto and runtime suites.

The required `Integration coordination:` line in PR #2178 now names `#2175`. Re-running a failed job against the **old GitHub pull_request event** still fails because `tools/change_integration_gate.py` reads `pull_request.body` from the saved original `GITHUB_EVENT_PATH` payload rather than refetching live PR metadata. This documentation commit intentionally triggers a new `pull_request.synchronize` CI event, with the newly acknowledged PR body, so that the normal gate can verify it. It does not weaken or bypass the gate.

Still **NOT cleared for production**: successful protected CI on the newly committed SHA; active governed patch-policy and site-patch reads; owner review negative-evidence/deferral source; independent exact KB-to-policy attribution; complete provider-backed shadow and Teams acceptance; exact-source Production Manager eligibility and explicit freeze exception.
