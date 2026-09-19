# Jason Operational Resolution Memory Integration — 2026-09-18

## Section Goal
Make Jason reuse prior operational resolutions as governed evidence during troubleshooting without allowing historical similarity to create execution authority, cross client boundaries, or replace current verification.

## Implemented
- Registered Operational Resolution Memory in the generic Integration Broker used by Jason's investigation loop.
- Preserved same-client raw-case isolation. Resolution search/read is not exposed to the reasoning model without authenticated current client scope.
- Requires a grounded current incident signature before a historical search may execute.
- Preserves recency, similarity, outcome-quality, failure/contradiction, and technician-confirmation signals.
- Excludes unconfirmed `observed` cases from live troubleshooting guidance; verified and technician-confirmed evidence can contribute under the existing weighting model.
- Historical actions remain evidence only and retain their read-only, approval-required, and disruptive classifications. `grants_authority=false` remains explicit.
- Added organization aggregate `operations.resolution.summary`, which exposes only case count/scope/health metadata and no raw case content.
- Persisted current client scope into bounded dynamic conversation context so the broker can fail closed across turns.
- Added Resolution Memory Prometheus exporter source and file-discovery configuration with aggregate-only metrics.

## Validation
Focused Resolution Memory, investigation, and conversation-context suites passed. Additional compatibility suites for dynamic conversation and investigation paths passed. Exporter aggregate-only regression passed.

Production image: `jason-mcp:resmem-8c9fb0e`.

Live governed proof: `operations.resolution.summary` succeeded with correlation `corr_mcp_a989d2f8a8ea43cfb9d73f45c53b5113`; result reported organization `aot`, zero cases, `scope=organization_aggregate`, `raw_cases_exposed=false`, and `grants_authority=false`.

## Current limitation
The production Resolution Memory store currently contains zero cases. The reuse/search path is implemented, but there is not yet historical production content to reuse. The next implementation slice is controlled ingestion of authoritative technician-confirmed resolved tickets/playbook outcomes into `ResolutionCase` records with exact client/ticket/correlation provenance.

## Section Goal closure
**PARTIAL / FOUNDATION LIVE.** Governed reuse is integrated and live, but this Section Goal is not complete until verified resolved work is ingested and a controlled similar-case retrieval is proven against real AOT history.

## Grafana / Prometheus reconciliation
The canonical roadmap status now exposes `RESMEM-001` as `active`. The live status exporter was reconciled and Prometheus returned one `jason_roadmap_item_info` series for `RESMEM-001` with status `active` and phase `Reasoning Quality`. Aggregate-only Resolution Memory exporter source and Prometheus file-discovery configuration are committed. The current session could not install the new systemd unit because the remote command policy blocks privileged service installation; this does not affect the live MCP capability. The existing roadmap panel therefore reflects the active implementation now, while dedicated case-count metrics await exporter service installation.

## Confirmed-case ingestion checkpoint
Implemented and deployed a fail-closed ingestion path for reviewed resolution candidates. A ticket being Complete is not sufficient by itself: ingestion requires the exact ticket source reference, matching current/ticket company boundary, normalized incident signature, explicit root cause/final resolution, owner, and terminal verification before a resolved case can become `verified`. Non-resolved/unconfirmed history is stored only as `observed` and cannot steer live troubleshooting under the existing matcher rules. A controlled operator ingestion tool was added; it performs no provider calls and cannot grant execution authority. Production image `jason-mcp:resmem-ingest-1a5f2b2` is live and the governed aggregate summary succeeded after deployment (`corr_mcp_56b21063bfc545ccb1f054f0c167b050`).

A live Autotask review also demonstrated why fail-closed ingestion is necessary: `T20260918.0030` contains strong Jason diagnostic provenance and exact Datto job references, but the ticket is currently status 30 and has no `resolvedDateTime`/`completedDate`; it was therefore **not** ingested as a verified resolution. Historical Complete-ticket search likewise returned legacy records whose `resolution` fields are empty, so completion status alone is intentionally not treated as authoritative resolution evidence.
