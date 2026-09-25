# KFS Toner Intelligence — Nonproduction Prototype

Status: **prototype only — do not deploy to production**

## Goal
Provide an AOT morning view that answers: **Which toner should we ship today?**

The prototype is intentionally observational. It does not create Autotask tickets, create or modify purchase orders, notify customers, or change KFS/provider state.

## Signals
- KFS toner level history by customer/device/color/part number.
- Probable cartridge replacement event: prior level <=15%, next level >=90%, jump >=60 points.
- Recent median decline rate, normalized per day.
- Customer/device seasonal factor hook. It defaults to 1.0 until sufficient history exists.
- Later validation source: Autotask toner orders / PO lines and KFS replacement events.

## Initial action bands
- `ship_today`: <=5% now, or projected depletion <=7 days.
- `ship_soon`: <=15% now, or projected depletion <=14 days.
- `watch`: not yet actionable.
- `needs_review`: low toner with insufficient usable decline history.

These are review defaults, not approved AOT production policy.

## Seasonal model
Seasonality must be learned separately for each customer/device. Holiday periods are labels, not assumptions: the model should compare that customer's historical behavior around each holiday and recurring seasonal period. Company A may slow down while Company B increases usage.

Until enough history exists, the prototype reports `seasonality_status=insufficient_history` and does not invent a seasonal adjustment.

## Validation loop
1. Jason recommends `ship_today`.
2. Compare with Autotask toner order/PO timing.
3. Detect the later KFS low-to-full replacement event.
4. Measure recommendation-to-order and recommendation-to-replacement days.
5. Track misses, early recommendations, duplicates avoided, and model/color-specific reliability.

## Production gates
Do not deploy until the dashboard and logic have been reviewed with real AOT data, customer mapping is reliable, zero/unknown toner semantics are validated, seasonality has sufficient history, and AOT explicitly approves production deployment.

## Telemetry freshness safety gate
A shipping recommendation is valid only when both the KFS collector and the relevant device/toner telemetry are fresh.

Freshness is measured against **successful KFS collections**, not calendar days:
- `current`: device and toner are present in the latest successful collection.
- `stale`: device missed one successful collection.
- `not_reporting`: device missed two or more successful collections.
- `long_term_missing`: device has no fresh telemetry for at least 7 days.
- `toner_stale`: device is current but this toner stream did not update in the latest successful collection.
- `collection_stale`: the latest successful KFS collection itself is older than 36 hours.

Any non-current state forces the toner to `needs_review`. **No fresh telemetry = no `ship_today` or `ship_soon` recommendation.** When reporting resumes, new readings are required before the trend should be trusted again; replacement/reset jumps remain separately classified.
