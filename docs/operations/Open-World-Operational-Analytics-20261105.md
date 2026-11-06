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

The existing `JASON_UNIVERSAL_QUERY_ENABLED` rollout gate remains authoritative. Runtime compose passes that variable through with a default of `false`. Production activation is source-bound by `config/universal-query-activation.json`: the reviewed `aot-internal-read-v1` profile makes the canonical runtime deploy inject `JASON_UNIVERSAL_QUERY_ENABLED=true`; `off` injects `false`; rollback always injects `false`. There is no host-only enable override. The controlled production rollout must verify the resulting AOT internal conversation path end to end.

Production deployment requires normal PMV3 exact-revision authorization, rollback verification, provider-backed acceptance, and post-deployment health validation.

## Post-deployment acceptance recovery

Production deployment of the open-world candidate passed native PMV3 health, drift, artifact, runtime/MCP/host alignment, and freeze-restoration checks. The subsequent provider-backed functional acceptance exposed a distinct operational failure: `print.meter.usage.search` reported a reconciled 436-device inventory and 436 selected devices but materialized only 100 usage records to the governed reasoning surface. A fleet-wide top-N answer therefore remained incomplete and the release must not be accepted as operational for the stated objective.

The release authorization explicitly bound rollback to the pre-release LKG if required production validation failed. PMV3 previously had automatic rollback only inside the initial deployment exception path; a release that had already reached `closed` had no public, governed exact-LKG rollback verb. Direct deployment-script execution is not an acceptable substitute.

`rollback-release` adds a bounded post-acceptance recovery control. It may act only on a closed production-verified release and requires all of the following to match the existing release evidence exactly:

- candidate SHA;
- reviewed scope SHA-256;
- recorded rollback/LKG SHA;
- exact Owner approval;
- consumed one-transaction Owner unfreeze receipt;
- complete pre-release LKG manifest; and
- restored production-freeze bytes.

The rollback itself executes under the serialized production transaction lock. It creates a single-use rollback receipt, temporarily removes the restored freeze only for that exact rollback transaction, restores MCP first, then host/release-manager source, approval policy, and runtime, verifies exact immutable LKG image IDs and full production alignment, restores the protected LKG, records the failed candidate as `rolled_back`, opens the circuit breaker against the failed candidate, and restores the original freeze bytes in `finally`. Ambiguous or mismatched evidence fails before production mutation. The control grants no standing rollback authority.

## Cross-channel fleet projection correction

The 2026-11-05 provider-backed post-deployment acceptance found that KFS itself selected and reconciled all 436 managed fleet devices, but the external Jason MCP evidence projector applied its generic 100-item list bound after the governed read. That made ChatGPT/Jason MCP consumers see only the first 100 usage records even though the KFS source and internal open-world runtime held the full selected fleet. The production candidate was rolled back rather than treating that partial projection as a trustworthy fleet-wide answer.

The corrective design preserves the existing global 100-item MCP safety bound for unrelated capabilities and adds a capability-specific projection for `print.meter.usage.search`. That projection may expose at most 1,000 records, matching the already-governed source contract, while applying the normal recursive secret-key redaction to every record. Fleet analytics therefore receive the complete bounded selected dataset without weakening the generic MCP evidence boundary.

## Final MCP double-bound correction

The second production acceptance on 2026-11-05 proved that the KFS source returned 436 selected records and the dedicated `print.meter.usage.search` projector preserved all 436, but `execute_read_capability` subsequently treated the capability as an unprojected dynamic read and passed its evidence through the generic navigation/evidence sanitizer. That sanitizer intentionally limits arbitrary lists to 100 items, recreating the exact truncation after the dedicated projector had already enforced the capability's 1,000-record governed source contract.

The final correction registers `print.meter.usage.search` as an already-projected capability at the `execute_read_capability` boundary. This does not widen the generic dynamic evidence limit and does not change the KFS source contract. Regression coverage now proves both sides of the boundary: 436 print-usage records survive the complete `execute_read_capability` path, while an unrelated dynamic capability remains limited to 100 records.
