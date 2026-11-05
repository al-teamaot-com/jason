# Open-World Operational Analytics — 2026-11-05

## Objective

Allow an authenticated AOT user to ask novel operational questions in ordinary language and have Jason determine how to answer them from currently authorized governed data sources. The implementation must not require a developer to anticipate each question and add a report, script, or question-specific capability.

## Architectural rule

The conversational path remains:

`human question -> semantic schema mapping -> live capability discovery -> generic relational planning -> governed reads -> deterministic joins/calculation/aggregation -> evidence-backed rendering`

The language model may select fields and propose bounded relational/arithmetic operations. It does not receive provider credentials, call providers directly, invent fields, calculate provider facts, or create authority. Operational values are calculated only by deterministic execution over governed evidence.

## Generic print-history primitive

`print.meter.usage.search` is a read-only collection primitive. It returns per-device usage facts for a bounded period from Jason's KFS historical evidence plane. It does not rank, group, format, or implement a report.

Returned facts include device/serial/equipment/model identity, verified customer identity when available, period boundaries, total/B&W/color/printer/copier/scan deltas, usage verification status, and fleet inventory coverage evidence.

The same collection can support questions such as top-N usage, totals by customer, color-vs-mono comparisons, cross-period changes, anomaly filters, or other future questions expressible through the generic query engine.

## Generic query-source narrowing

Capabilities may declare `query_filter_bindings` that map relational field predicates to safe provider arguments. Jason deterministically lowers only declared filter/operator pairs. The model cannot provide arbitrary provider arguments. The same predicate is still re-evaluated by the deterministic query engine after evidence materialization.

This allows questions such as “last 10 days” to narrow the governed historical read instead of reading an arbitrary default period and pretending it represents the requested interval.

## Deterministic arithmetic

The generic query engine supports bounded numeric add/subtract/multiply/divide expressions. Arithmetic is evaluated only over governed values after source reads. Missing operands remain unavailable and division by zero fails closed.

This enables questions such as “which devices increased the most versus the previous period” without a comparison-specific capability.

## Customer and device identity

KFS customer identity is used when present. When a requested answer requires company or service-configuration identity that is absent from KFS, Jason may use the bounded post-query lookup stage against already-authorized governed resources. For AOT copier identity, exact KFS serial numbers can resolve through Autotask configuration items and then through the owning Autotask company. Lookups are exact-unique, bounded after the analytical result, cached per value, and fail closed on ambiguity.

This release does not require a new SharePoint identity, secret, AppRole, or document-specific report workflow.

## Evidence and completeness

Period usage is derived from historical meter boundaries. Reset/decreasing counters, absent boundaries, and inconsistent total/B&W/color values are marked as exceptions rather than estimated. Fleet inventory coverage is independently reconciled against the latest successful KFS collection snapshot. Targeted device queries retain fleet-snapshot coverage evidence without requiring selected record count to equal the whole fleet.

## Verified development evidence

Provider-backed read-only validation against the live KFS history database returned 436 selected devices from a 436-device reconciled inventory for the 2026-10-27 through 2026-11-05 test period, with 433 reconciled usage records and three meter-boundary exceptions. The raw generic records reproduced the independently verified top-ten period totals, including 25,636 impressions for serial `RRG2301432`.

A targeted read for `RRG2301432` returned one selected record while preserving verified 436-device fleet snapshot coverage.

Provider-backed Autotask acceptance then resolved all ten independently verified high-volume KFS serials to exactly one active ConfigurationItem. The resulting company IDs all resolved to exactly one active Autotask company, including `RRG2301432` -> configuration `1207 Teachers Work Room BIG -` -> company `St. Matthews Catholic School`. No SharePoint credential or document lookup was required.

Automated acceptance also proves the same raw `print_usage` resource can answer materially different query shapes: top-N total usage, grouped customer color totals, and joined cross-period usage increase. A separate generic exact-lookup phase can enrich bounded query outputs from other governed resources without changing the analytical primitive or adding question-specific report code. No ranking/report-specific runtime capability is involved.

## Production boundary

The existing `JASON_UNIVERSAL_QUERY_ENABLED` rollout gate remains authoritative. The runtime compose file now passes that variable through with a default of `false`; this change does not activate the open-world conversation path by itself. A controlled production deployment must explicitly set `JASON_UNIVERSAL_QUERY_ENABLED=true` for AOT internal rollout and verify the resulting conversation path end to end.

Production deployment requires normal PMV3 exact-revision authorization, rollback verification, provider-backed acceptance, and post-deployment health validation.
