# Jason Datto Endpoint Discovery Completeness — 2026-09-18

**Section Goal:** Fix Datto RMM endpoint discovery so Jason can resolve an existing endpoint from hostname/site without pre-supplied Datto UID and so incomplete enumeration cannot be represented as definitive not-found evidence.

**Status:** SOURCE FIX IMPLEMENTED / PRODUCTION DEPLOYMENT PENDING

## Reproduction

Production governed search for `SOSServer2024` at `Star of the Sea Catholic Church` returned zero matches while examining only two provider pages even though Datto reported approximately 749 devices. A governed exact read succeeded immediately when the known Datto UID `52b4f1ad-d834-4c79-4955-8434101ccb7a` was supplied.

Original reported correlations:

- failed discovery: `corr_mcp_c50e0d8bdcc54dfa96a9fbf95e0ad5f2`;
- successful UID read: `corr_mcp_64eaac562aaa4e0c818b2b3988f18752`.

A fresh governed reproduction in this section again returned zero matches with `provider_pages_examined=2` and `provider_total_count=749`, proving the defect remained live before the source correction.

## Actual execution path traced

The production path is:

1. canonical capability `endpoint.device.search` in `implementation/orchestrator/resource_capability_catalog.py`;
2. Central Orchestrator routing through `implementation/orchestrator/capability_routing_invoker.py`;
3. Datto provider translation through `implementation/connectors/provider_resource_adapters.py`;
4. Datto execution in `implementation/connectors/datto_rmm/connector.py`;
5. MCP conversational projection in `implementation/mcp_service/src/jason_mcp/server.py`.

No direct-provider ChatGPT path is involved.

## Root cause

Three defects combined:

1. Datto account-device pagination is zero-based, but device search/fallback began from page 1.
2. The hostname fallback requested `max=250` and treated any returned page with fewer than 250 records as provider exhaustion. Datto may cap a page below the requested maximum. Therefore a successful short page was incorrectly interpreted as terminal even when more devices existed.
3. MCP projected `match_count=0` without projecting connector-level `discovery_complete` / incomplete reason, allowing a partial scan to look like a definitive not-found result.

The observed two-page behavior is explained by one initial provider-filtered hostname request plus one fallback enumeration page that was incorrectly accepted as complete.

## Source correction

Branch: `fix/jason-datto-endpoint-discovery-20260918`

The fix:

- starts Datto account-device enumeration at page zero;
- continues sequentially until a genuine empty provider page;
- detects pagination stalls/repeated records;
- returns `discovery_complete=false` with a bounded reason when the safety page bound is reached before exhaustion;
- retains provider errors as failures rather than converting them to zero-match success;
- prefers exact case-insensitive hostname matches;
- uses exact normalized site name as a disambiguator when supplied;
- keeps identifier-fragment matching only as a lower-priority fallback;
- projects `discovery_complete` and `incomplete_reason` through MCP;
- updates the Grafana roadmap exporter to read the canonical `docs/roadmaps/Jason-Roadmap-Status.json` source.

No grants, provider identities, allowlists, write authority, approval policy, or direct-provider access were changed.

## Regression coverage

Connector tests cover:

- exact SOSServer2024 + Star of the Sea resolution to `52b4f1ad-d834-4c79-4955-8434101ccb7a`;
- endpoint discovery beyond provider page 2;
- genuine exhausted not-found with `discovery_complete=true`;
- bounded incomplete enumeration with `discovery_complete=false`;
- case-insensitive exact hostname normalization;
- site disambiguation for identical hostnames at different sites.

MCP contract tests cover complete zero-match versus incomplete zero-match projection.

The focused Datto connector suite passed before an unrelated pre-existing Datto component-catalog workflow fixture failure. The same Datto workflow already failed on the authoritative base commit `d8552b3a57a2859ffba8459f0f10cc93fd6d5394`, so that unrelated baseline failure is not attributed to this endpoint-discovery change.

## Hardening disposition

The existing search contract already returns a durable `resolved_resource_id` after safe resolution. Downstream work should carry that identifier through the current workflow and feed it to exact device reads rather than rediscovering the hostname repeatedly. No new persistent cache is introduced; that avoids stale mappings when devices are renamed, moved, duplicated, or reconciled by the provider.

Cross-source contradiction detection remains a post-core hardening item. It is intentionally not activated before the production discovery fix is proven, so the endpoint-discovery correction does not expand provider scope or introduce unrelated correlation behavior.

## Governance verification

Required invariants remain:

- Central Orchestrator authoritative;
- `direct_provider_access=false`;
- provider credentials not exposed;
- no provider production writes;
- no endpoint mutation;
- governed execution/approval behavior unchanged.

## Production acceptance — pending

This record must not be marked complete until the normal production deployment is performed and governed production validation proves:

1. `endpoint.device.search(hostname="SOSServer2024", site="Star of the Sea Catholic Church")` returns the correct endpoint and UID without caller-supplied UID;
2. the returned UID feeds `endpoint.device.read` successfully;
3. at least one additional existing endpoint validates generalized multi-page discovery;
4. live MCP remains healthy in governed-read-plus-actions mode with unchanged governance;
5. the deployed source/image revision and validation correlation IDs are recorded here;
6. the roadmap milestone is changed from `active` to `complete` and deployed Grafana/Prometheus status is verified.

## Section Goal final status

**PENDING — production deployment/validation not yet claimed.**
