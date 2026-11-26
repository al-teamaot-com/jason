# KFS fleet period ranking — source-only engineering, 2026-11-22

## Goal and ownership
Provide a governed AOT-internal `print.fleet.usage.rank` read capability for top-N and full-inventory month-to-date or completed-month printer usage, using the **existing** KFS history/collector and Central Orchestrator. This replaces chat-side sorting of a truncated first page; it is not an external export, billing mutation, or license for remote terminal access.

## Contract
- Inputs: `month` (YYYY-MM) or `start`/`end`, `timezone` (default America/New_York), `metric` (`total`, `black_white`, `color`), `top_n` (integer 1–50), `report_mode` (`rank` or `list`), `managed_only` (Boolean, default true), and `boundary_hours` (existing governed threshold)
- Source: pre-existing `KfsMeterHistoryStore.usage_search`, using maximum 1,000 devices; no direct KFS provider override and no operator-supplied first-page `limit` or `device_id` restriction
- Refuse ranking if source inventory coverage is not reconciled, a source collection is truncated, or device identifiers are missing/duplicated
- Include only measured, nonnegative, mutually consistent total/B&W/color period deltas. Exclude ambiguous, missing/reset and inconsistent counters from ranking; count and identify exceptions
- Sort by selected impressions descending; stable serial/device ID tie break
- Return each top device's customer name only when source verified it, otherwise blank and flagged; no invented identity
- Return exact period boundaries, source inventory, selected managed count and verified/exceptions/mapping-unknown counts
- In `list` mode return **every included device exactly once**, including unmeasured ones with explicit null meters and reason; preserve measured zero. The full source still includes all 435 devices for inventory reconciliation, but KFS `management_status=1` is required for managed-only reporting. The 20 devices with other management statuses in the earlier fleet baseline are not billable by assumption.
- Fail closed if management status is missing, duplicate inventory IDs exist, the source is truncated, or source fleet counts fail reconciliation. Never estimate a meter or invent a customer.
- The report is a structured governed read, not yet a directly downloadable or delivered Excel workbook, and it does not authorize an invoice write.
- AOT organization-wide observe only; no cross-client impersonation, no writes, no standing execution authority

## Verified live baseline
On 2026-11-22 the existing governed `print.meter.usage.search` returned 435 distinct of 435 KFS inventory devices for October 2026 (correlation `corr_mcp_4429eb04a4a04802bac4c79715942924`), 432 valid measured usage records, 3 missing-meter-boundary exceptions, and 304 missing verified customer mappings. The operation is provider-backed and read-only.

## KFS rich device-search projection integrity — 2026-11-22
Live `print.device.search` with `limit=1000` returned only 100 richly structured records while its original provider metadata claimed `matched_count=443`, `complete=true` and `next_offset=null`. This is an MCP collection-bound projection defect, not KFS inventory source loss. Five normal provider-backed `limit=100` pages at offsets 0/100/200/300/400 independently reconciled to 443 unique IDs: 424 `managementStatus=1` and 19 `managementStatus=2`, all consecutive continuation offsets and final page 43. This is current inventory, not October 2026 meter coverage.

The report fix preserves the security bound on individual rich device responses and repairs only contradictory completeness metadata to `complete=false`, `next_offset=offset+actual_returned`, `projection_bounded=true`, without inventing device records or changing provider state. Only a genuinely complete last page can report `complete=true`. Clients must honor returned continuation or use the governed full-fleet period report; never equate `matched_count` with the number actually returned in one rich search response.

## Engineering acceptance versus operational acceptance
Focused local tests cover 435 devices, exceptions, ties, incomplete source, duplicate IDs, invalid arguments, AOT-only requester restrictions, and invoker-enforced full source retrieval. Source-only test success is not release acceptance. The deployed MCP must independently discover the new capability and execute a full October report under an authorized AOT requester, verifying coverage and top-five against same-source facts; then Adam and LaToshia must confirm conversational use. Missing customer identities remain explicit data-quality exceptions, not a pretext to fabricate mapping. Export and delivery under issue #1735 remain a separate operational acceptance gate.

## Source integration coordination
PR #2624 separately changes SharePoint runtime composition. Its exact change hunks and this KFS proposal were reviewed: SharePoint imports/initialization and its conditional invoker registration do not intersect the KFS import and KFS invoker registration. The final integration must preserve both additive sections. The active CI change-integration gate uses the PR event body's exact `Integration coordination: #2624` acknowledgement; updated metadata requires a fresh PR event after review rather than re-running an earlier event with stale content.

## Release boundaries
This branch does **not** deploy, grant Owner release approval, clear production drift, restart a protected service, lift freeze, or update KFS/Autotask. Current production on Jason remains independently governed. Require approved exact candidate/rollback, source CI, isolated run, and live non-regression checks before release.
