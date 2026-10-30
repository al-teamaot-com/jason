# KFS fleet month-to-date ranking: governed read-only acceptance

Owner: AOT Copier Operations · Issue #2176 · PR #2177 · 2026-10-30

## Expected experience
An authorized AOT staff member can ask "Jason, what are our top 5 highest-volume printers for October 2026?" Jason selects `print.fleet.usage.rank` through governed resource interpretation and returns customer, equipment ID, B&W pages, color pages, total impressions, latest reading timestamp, and coverage/exception details. No user-uploaded KFS spreadsheet, device ID, or direct provider credential access is required.

## Data contract
- Source of truth for inventory: the latest completed successful `kfs_runs` row at or before the reporting period end, and the corresponding `kfs_device_status_readings` rows. Check `device_count`, `error_count=0`, unique device IDs, and snapshot freshness (at most 36 hours).
- Meter source: read-only `kfs_meter_readings` sampled near the period-start and period-end boundaries, with a configurable bounded window (default 36 hours). All SQL parameters are bound; no side-effecting statements.
- For the current month, stop at the present observation time. Never extrapolate to month-end. A prior month uses the specified month boundaries in the requested timezone.
- Rankings are by nonnegative, actual `total` impression difference. Require matching B&W and color deltas and `B&W + color = total`. Scans are excluded. Stable tie-break by device ID.
- Report `complete=true` only if the successful inventory is fresh, its reported and enumerated device counts agree, no current devices are missing, and all included devices have usable B&W/color/total deltas. Otherwise identify the report as provisional and list exceptions; never present a partial ranking as authoritative.
- Data gaps may be legitimately caused by offline/nonreporting printers. Such gaps are not estimated or silently excluded.

## Scope and guardrails
- AOT organization observe-only; tenant/client scoped calls remain denied until approved mappings exist.
- No endpoint changes, service restarts, printer changes, ticket updates, new provider permissions or credential handling outside current governed KFS read path.
- The preproduction branch does not alter production until a separately authorized controlled release.
- No change to other pending PRs #2125/#2126/#2128; their overlapping `composition.py` portions should be reviewed during integration.

## Validation
- KFS connector, catalog, authority and history tests.
- A literal LaToshia query end-to-end metadata/plan routing test, plus top-ten and unrelated-toner intent tests.
- 435-device fixture, missing boundary/reset, stale inventory, mismatched fleet counts and report completeness tests.
- Provider-backed acceptance: compare the actual live KFS full-fleet inventory with stored run counts, verify latest collection and exact October deltas, and rerun the same October query as Adam and LaToshia. Verify the same top five and exceptions.
- All required CI, overlap/standards/documentation gates, controlled release scope, last-known-good SHA, exact candidate SHA and postdeploy health must pass before deployment.

## Production readiness
Implementation and synthetic tests alone do **not** establish live KFS readiness. Until provider-backed acceptance succeeds, mark the capability NOT VERIFIED for production.

## Latest non-disruptive collector evidence (2026-10-30)

Observed on the authorized Jason host via **read-only** inspection of collector result summaries (not a preproduction execution of this PR):

| Completed UTC collector run | Result | Managed devices | Errors | Meter-reading rows |
|---|---|---:|---:|---:|
| 2026-10-30 16:00:01 | ok | 435 | 0 | 7,330 |
| 2026-10-30 10:00:02 | ok | 435 | 0 | 7,330 |
| 2026-10-30 04:00:00 | ok | 435 | 0 | 7,330 |

The 16:00Z collector run ID is `11ad789b-73eb-4762-8fa7-44f8124a70b4`. A successful collector summary supports inventory freshness, **not** the accuracy of October per-device deltas, the ranking, live AOT user routing, or the full database join. Those remain provider-backed acceptance requirements.

### Exact source scope caution

At this inspection, the running production runtime and `/opt/jason/current` both identify `cb76e14f9f42ec4f914b10967db1d408c271c1aa`. Protected main is ahead of that running release by one separate engineering-standards commit (five files, including `AGENTS.md` and the JES registry). A future merged KFS release must disclose that separate commit in the complete release scope and verify the root-pinned last-known-good release; the running SHA alone is not sufficient to claim rollback readiness. No merge or production deployment is implied here.

## Provider-backed report acceptance evidence (2026-10-30, read-only)

Using the exact PR development code in an isolated source checkout, the existing `kfs_reader` role and PostgreSQL transaction read-only mode, the October month-to-date batch query reconciled **435 of 435** current inventory devices against the completed collector run `11ad789b-73eb-4762-8fa7-44f8124a70b4`.

First pass: 219 devices had complete total/B&W/color deltas; 216 were flagged. Investigation of the source data established that 213 of those devices have no separate color counter **and** independently observed total and B&W deltas are exactly equal. This justifies derived *zero* color impressions with explicit provenance; it is not a usage estimate. Three devices lack required total and B&W boundaries and remain exceptions.

After applying the no-estimate monochrome rule and re-running the live read-only calculation, 432 devices had usable actual monthly deltas and 3 remained meter exceptions. **Do not claim full-fleet ranking certainty** while any inventoried device lacks bounds.

A separate KFS upstream customer-assignment gap is confirmed: only 131 of the 435 devices in the latest inventory have a nonempty `kfs_devices.customer_name`. The KFS group metadata did not supply names for four of the five current highest-volume devices; all four also have empty customer IDs, and the root group is shared by multiple unrelated customers. **Do not infer customer from a shared group**. The report explicitly labels unmapped customers and publishes the missing-mapping count rather than inventing a customer.

This source+live-data validation is not a deployed Jason user conversation acceptance. Normal user tests previously failed on production before this branch was merged. Required next evidence: current-head CI and controlled preproduction end-to-end conversation response, then exact merged SHA / root-pinned rollback verification and a separately authorized deployment. No production change has been made in these checks.
