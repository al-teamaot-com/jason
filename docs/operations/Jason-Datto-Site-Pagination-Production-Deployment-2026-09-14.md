# Jason Datto Site Pagination Production Deployment — 2026-09-14

## Purpose

This record documents the production correction for Datto RMM managed-site pagination discovered during real-world Jason testing on 2026-09-14. It records the defect, the narrow source correction, production deployment identity, rollback assets, and live governed proof. It does not authorize provider writes, merge PR #174, alter authority, or weaken information-release controls.

## Defect

A governed `management.site.search` could receive a successful first Datto provider page containing 10 sites while provider metadata reported 45 total sites. Before the correction, ordinary unfiltered site enumeration defaulted to a "sufficient" collection read and could therefore treat that successful first page as complete evidence.

This was a correctness defect: successful receipt of one provider page is not equivalent to a complete collection when authoritative pagination metadata proves additional records exist.

## Source correction

Authoritative source commit:

- `6da45b3ef66d08762cbeed66c5c540c873b20889` — `Complete governed Datto site pagination`

The implementation change is intentionally narrow:

- `implementation/connectors/datto_rmm/connector.py`
- `implementation/connectors/tests/test_datto_rmm_connector.py`

`datto_rmm.site.search` now requests complete bounded collection handling by default. The existing provider-neutral `BoundedCollectionReadAdapter` remains responsible for following provider continuation metadata and retains its existing safety bounds:

- maximum pages: 20;
- maximum items: 1000;
- fail closed on incomplete pagination, malformed continuation, repeated page marker/cycle, missing continuation when more records are known to exist, or over-collection.

The regression case models five provider pages of `10 + 10 + 10 + 10 + 5 = 45` and verifies a final complete collection of 45 sites. Focused provider-adaptation and Datto connector tests passed before production deployment.

## Production deployment

The MCP-only production cutover completed successfully after explicit owner approval.

Current live MCP:

- container: `jason-mcp-pilot`;
- image: `jason-mcp:datto-pagination-6da45b3ef66d`;
- image ID: `sha256:320015a9196bacab883149da8257a40f1061ab002c50b14c694975e979989b49`;
- source revision: `6da45b3ef66d08762cbeed66c5c540c873b20889`;
- provider-read profile: `itglue-autotask-entra-governed-catalog-v4`;
- mode: read-only;
- governed execution: Central Orchestrator;
- direct provider access: disabled;
- write tools: disabled.

The deployment changed only the MCP container/image. `jason-runtime` and OpenBao container identities were verified unchanged after cutover. No authority change, provider write grant, provider write action, PR merge, runtime restart, or OpenBao restart occurred.

## Launch-contract preservation

The existing production MCP launch contract was reconstructed from live Docker metadata rather than guessed from stale deployment assumptions.

Important observed contract facts:

- network: `jason-core`;
- host binding: `10.87.246.157:8765 -> 8000/tcp`;
- MCP is not privileged;
- 15 bind mounts are present;
- 12 credential-related bind mounts are read-only and mounted inside the MCP under `/run/jason-secrets/openbao/...`;
- credential contents and host source paths were not printed or recorded in this documentation;
- all bind sources were verified Docker-accessible before cutover;
- each read-only credential source was verified byte-for-byte equivalent to the credential already mounted in the running MCP without exposing the credential value.

The earlier production-status reference to `/run/jason-runtime-credentials/openbao` did not describe the actual live MCP container-side credential destinations and is corrected in the current production-status record.

## Duplicate environment exception preserved

Issue #180 remains deliberately unresolved by this deployment.

The live MCP continues to contain two entries each for:

- `JASON_SOURCE_REVISION`;
- `JASON_PROVIDER_READ_ACTIVATION_PROFILE`;
- `JASON_AUTOTASK_REQUESTER_AUTH_MODE`.

The deployment preserved those duplicate-entry counts exactly rather than opportunistically cleaning them up during an unrelated pagination correction. Only the final/effective `JASON_SOURCE_REVISION` value changed to the pagination source revision. A raw Docker Engine API container-create path was used because a normal Docker CLI recreation normalized the duplicate environment entries during preflight.

## Security and transport acceptance

Pre-cutover and post-cutover behavior matched:

- anonymous MCP request: HTTP `401`;
- hostile Host header: HTTP `421`;
- local MCP health: PASS;
- public `https://mcp-jason.teamaot.com/healthz`: PASS;
- MCP status: read-only;
- governed execution: `central-orchestrator`;
- direct provider access: `false`;
- write tools enabled: `false`.

## Live governed pagination proof

After production cutover, Jason was queried through the governed MCP interface using the active `management.site.search` capability.

Live result:

- provider: Datto RMM;
- provider capability: `datto_rmm.site.search`;
- final `pageDetails.count`: `45`;
- final `pageDetails.totalCount`: `45`;
- `discovery_complete`: `true`;
- governed execution result: succeeded/completed.

This is the production proof that Jason no longer stops at the first 10-site provider page for ordinary governed site enumeration. The complete provider-reported 45-site collection was returned through the governed read path.

## Rollback assets

Immediate pre-pagination rollback is preserved:

- rollback container: `jason-mcp-pilot-pre-pagination-20260914T154422Z`;
- rollback image: `jason-mcp:pre-pagination-20260914T154154Z`;
- rollback image ID: `sha256:6d9303e501fac2690110f7526520ce2947be8783dcf3106be5709da1e1e5006d`.

Older rollback/checkpoint assets, including the pre-v4 rollback and the accepted provider-read-v4 checkpoint, remain preserved. The earlier checkpoint remains a historical rollback/reference point; it is not rewritten to pretend that its older MCP image is still the current live image.

## Scope intentionally not changed

This deployment did not address unrelated cleanup or product-quality work. In particular:

- duplicate MCP environment cleanup remains issue #180;
- provider foreign-key/user-relevant output enrichment remains separate work;
- continuous provider canaries remain separate work;
- PR #174 remains draft/open/unmerged;
- provider write capability remains disabled.

The live site-search proof also demonstrated that generic dynamic evidence can include provider-native site fields and implementation identifiers. That is a separate user-relevant-output concern and was not mixed into this pagination correction.

## Acceptance result

- source correction deployed: PASS;
- MCP health: PASS;
- public health: PASS;
- authentication/Host protections preserved: PASS;
- Central Orchestrator governance preserved: PASS;
- direct provider access disabled: PASS;
- write tools disabled: PASS;
- runtime identity unchanged: PASS;
- OpenBao identity unchanged: PASS;
- rollback preserved: PASS;
- live governed site enumeration: `45 / 45`, complete: PASS.
