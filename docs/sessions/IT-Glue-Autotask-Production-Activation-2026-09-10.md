# Project Jason — IT Glue + Autotask Production Read Activation

**Date:** 2026-09-10  
**Branch:** `feature/jason-provider-reads-itglue-autotask-20260909`  
**Deployment source commit:** `ea9d8a095b3539d9d35d08959f3b6e652922f960`  
**Status:** Initial governed production read subset activated and live-verified through ChatGPT -> Jason MCP

## Purpose

Record the bounded production activation and live MCP verification of Jason's initial IT Glue and Autotask governed read subset.

This record does not authorize or activate provider writes, IT Glue credential-vault/password data, document search/read capabilities, or PR merge.

## Production runtime activation

The Jason host activated the source-controlled profile:

`itglue-autotask-initial-read-v1`

The activation was performed from an isolated detached worktree pinned to:

`ea9d8a095b3539d9d35d08959f3b6e652922f960`

Host verification reported:

- source pin: PASS;
- runtime credential metadata preflight: PASS;
- four provider credential files present and identical to the approved bootstrap sources;
- runtime credential owner/mode verification: PASS;
- Compose render with the exact activation profile: PASS;
- `jason-runtime` build: PASS;
- recreation of only `jason-runtime`: PASS;
- new runtime health: PASS;
- all four provider mounts read-only: PASS;
- runtime credential readability without printing credential contents: PASS;
- all other containers unchanged during the activation window: PASS;
- provider writes enabled: NO.

Rollback image preserved during this activation:

`jason-runtime:rollback-provider-read-resume-20260910T164948Z`

## MCP runtime verification

The live `jason-mcp-pilot` was inspected after runtime activation.

It already had:

- `JASON_PROVIDER_READ_ACTIVATION_PROFILE=itglue-autotask-initial-read-v1`;
- read-only IT Glue AppRole mounts;
- read-only Autotask AppRole mounts;
- all four provider credential files readable by the MCP process;
- the same authority and Microsoft identity-binding stores used by the runtime;
- current provider-read source modules present inside the MCP container.

No MCP rebuild or restart was required for the authority activation.

## Governed authority activation

Before authority activation, live MCP requests for:

- `documentation.organization.search`; and
- `service.ticket.search`

failed closed with `NO_MATCHING_AUTHORITY_GRANT` for `person-al` in organization `aot`, while Datto RMM reads continued to succeed under the existing organization-scoped provider-read grant.

The production authority store was backed up with SQLite's backup API before modification:

`/var/lib/jason/authority/authority.sqlite3.backup-provider-read-20260910T180115Z`

Backup integrity and mode `0600` were verified.

Two and only two new grants were then added atomically:

- `grant-aot-it-glue-provider-read-observe`
  - subject: `organization:aot`
  - capability: `provider-read:it_glue`
  - organization: `aot`
  - client: `None`
  - permission: `observe`
  - approval required: `false`
  - status: `active`

- `grant-aot-autotask-provider-read-observe`
  - subject: `organization:aot`
  - capability: `provider-read:autotask`
  - organization: `aot`
  - client: `None`
  - permission: `observe`
  - approval required: `false`
  - status: `active`

Authority grant count changed from 9 to 11. Existing grants were verified unchanged. No service restart occurred.

The provider-read authority matcher remains constrained to observe-only requests for currently registered provider-neutral capabilities whose metadata is explicitly read-only and that are advertised by the named provider. The new grants therefore do not create a generic write/execute authority path.

## Live ChatGPT -> Jason MCP provider verification

After the two grants were added, fresh live MCP calls succeeded through Jason governance and Central Orchestrator.

### IT Glue

Capability:

`documentation.organization.search`

Provider resolution:

`it_glue` -> `it_glue.entity.query`

Result:

- governance: allowed;
- provider invocation: completed;
- provider path: live;
- query was bounded to page size 1;
- no provider mutation occurred.

The selected test name returned zero organization records, which is acceptable for connectivity/execution proof because the provider call itself completed successfully through the governed path.

### Autotask ticket search

Capability:

`service.ticket.search`

Provider resolution:

`autotask` -> `autotask.ticket.search`

Result:

- governance: allowed;
- provider invocation: completed;
- provider path: live;
- result bounded to one ticket record;
- no provider mutation occurred.

### Autotask company read

Capability:

`service.company.read`

Provider resolution:

`autotask` -> `autotask.company.get`

Result:

- governance: allowed;
- provider invocation: completed;
- provider path: live;
- exact company read completed successfully;
- no provider mutation occurred.

## MCP safety state after activation

Fresh MCP status remained:

- mode: `read-only`;
- governed execution: `central-orchestrator`;
- direct provider access: `false`;
- write tools enabled: `false`.

The active MCP capability registry now exposes the initial approved IT Glue/Autotask reads alongside the existing governed read capabilities without adding provider-specific MCP tools.

## Evidence-shaping observation

The live zero-result IT Glue organization search also returned provider filter/permitted-value metadata that was larger than needed for the user-facing answer. This did not expose credentials or enable any write path, and it does not invalidate the live provider-read proof. It is recorded as a separate evidence-minimization hardening item rather than being treated as a failure of the initial production read activation.

## Remaining boundaries

This checkpoint does **not** activate:

- `documentation.document.search`;
- `documentation.document.read`;
- any provider write capability;
- any provider-specific MCP tool;
- any bypass around Jason identity/authority/client scope;
- PR merge.

The static IT Glue document capabilities remain PILOT until their own bounded provider-backed live acceptance is completed and separately approved for activation.

## Completion statement

The initial IT Glue + Autotask governed provider-read production activation is complete for the approved subset:

- runtime credentials: active and mounted read-only;
- activation profile: active;
- organization-scoped observe-only authority: active;
- ChatGPT -> Jason MCP -> Central Orchestrator -> IT Glue: live verified;
- ChatGPT -> Jason MCP -> Central Orchestrator -> Autotask: live verified;
- provider writes: disabled;
- MCP write tools: disabled;
- PR #171: remains draft and unmerged pending separate decision.
