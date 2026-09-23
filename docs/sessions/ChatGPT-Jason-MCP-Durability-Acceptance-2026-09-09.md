# Project Jason — ChatGPT MCP Durability Acceptance

**Date:** 2026-09-09  
**Classification:** Evidence / point-in-time production-pilot proof  
**Status:** Accepted  
**Primary tracking record:** GitHub Issue #166 — Durabilize ChatGPT MCP pilot and reproduce from source

## Purpose

Preserve the final durable acceptance state reached after the earlier ChatGPT, Entra, workspace-enable, and MCP functional-baseline records.

This record supersedes only the unfinished-work statements in the earlier 2026-09-09 MCP closeout checkpoint. It does not rewrite that historical proof.

## Last durable MCP source

Source commit:

`727c3fa6cbcb59dab32f77632393bc5407826ed0`

Source-built live image:

`jason-mcp:source-727c3fa`

Accepted image ID:

`sha256:5d5532b0425c6baed53d881392515a9518616371eeb65c6496f648b04d0c2c6e`

The live `jason-mcp-pilot` was recreated from committed source rather than depending on manual in-container code mutation.

## Accepted MCP surface

The intended and proven MCP tool surface is exactly:

- `jason_mcp_status`
- `discover_capabilities`
- `execute_read_capability`

No write or consequential MCP tool exists in this accepted baseline.

The service remains a governed read adapter. It does not expose provider credentials, unrestricted provider HTTP access, unrestricted raw provider pages, or a direct provider execution bypass.

## Governed path

`ChatGPT -> OAuth / Entra -> Jason MCP -> Jason identity and authority -> Central Orchestrator -> governed read capability -> governed evidence -> ChatGPT`

A ChatGPT tool call remains a request for governed execution and does not grant business, provider, client, or consequential-action authority.

## Acceptance results

The source-built service and public boundary passed the required durability and transport acceptance, including:

- health endpoint reachable;
- protected-resource metadata correct;
- authorization-server metadata correct;
- Entra OIDC compatibility metadata correct;
- PKCE S256 preserved;
- anonymous MCP access rejected with HTTP 401;
- valid unauthenticated Host reaches authentication and returns 401;
- hostile application Host rejected with 421;
- hostile Origin rejected with 403;
- exact three-tool read-only surface;
- governed capability discovery;
- harmless governed live read;
- ChatGPT OAuth/tool invocation after source-built recreation;
- no write surface.

The external Caddy edge was also corrected so hostile Host traffic is rejected before an unintended fallback response.

## Rollback evidence

The prior MCP rollback containers/images were preserved through acceptance.

The Caddy edge backup created during host-guard correction is:

`/etc/caddy/Caddyfile.backup-mcp-host-guard-20260909T133922Z`

Do not remove rollback material merely because this proof exists.

## Completion state

GitHub Issue #166 was closed as completed on 2026-09-09 after the complete fresh-source acceptance battery passed.

Therefore:

- ChatGPT / Entra functional integration: complete for the read-only baseline;
- source durability: complete;
- public transport/edge acceptance: complete;
- read-only governed live execution: complete;
- write/consequential tools: not part of this baseline;
- System Registry reconciliation: separate remaining documentation/operational-state work.

## Related records

- `docs/sessions/PROJECT-JASON-CHATGPT-MCP-ENTRA-FUNCTIONAL-BASELINE-2026-09-09.md`
- `docs/sessions/PROJECT-JASON-CHATGPT-WORKSPACE-ENABLEMENT-2026-09-09.md`
- `docs/sessions/PROJECT-JASON-CHATGPT-MCP-CLOSEOUT-2026-09-09.md`
- `docs/decisions/ADR-010-ChatGPT-Business-Primary-Conversational-Interface.md`
- `docs/architecture/J-104-ChatGPT-Jason-Access-Architecture.md`
- `docs/engineering/interfaces/Jason-MCP-Construction-Guide.md`

## Authority boundary

This is a proof record, not an authority grant. Current production claims still require current Git, System Registry state, and fresh observed evidence when the fact is operationally volatile.
