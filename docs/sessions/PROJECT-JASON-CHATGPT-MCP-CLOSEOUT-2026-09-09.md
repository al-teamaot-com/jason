# Project Jason — ChatGPT MCP Enablement Closeout

**Date:** 2026-09-09  
**Branch:** `feature/jason-runtime-service`  
**Status:** ChatGPT client enablement complete; remaining deployment-durability work tracked separately.

## Closeout summary

The ChatGPT portion of the Jason MCP integration is functionally complete for this checkpoint.

TeamAOT now has an enabled workspace app named **Jason** pointing to:

`https://mcp-jason.teamaot.com/mcp`

The integration has demonstrated the complete governed path:

`ChatGPT -> OAuth 2.0 / PKCE -> Microsoft Entra ID -> Jason MCP -> Jason identity/authority -> Central Orchestrator -> authorized read capability -> governed evidence -> ChatGPT response`

A real live read was successfully completed from ChatGPT against `AOT-50282`, proving that the integration works beyond protocol/authentication setup.

## Completed for this checkpoint

- Public MCP endpoint established.
- Microsoft Entra OAuth authentication established.
- Dedicated ChatGPT confidential OAuth client established.
- Canonical MCP resource established as `https://mcp-jason.teamaot.com/mcp`.
- Delegated OAuth scope established as `https://mcp-jason.teamaot.com/mcp/Jason.Read`.
- JWT validation correctly continues to enforce the Entra `scp` value `Jason.Read`.
- Protected-resource metadata established.
- OAuth authorization-server compatibility metadata established.
- PKCE `S256` advertisement established.
- Exact authorization-server issuer matching established.
- Entra OIDC compatibility endpoint established.
- MCP DNS-rebinding protection preserved with the public Jason host explicitly allowlisted.
- Anonymous MCP access remains rejected with HTTP 401.
- ChatGPT can authenticate and invoke Jason.
- Jason remains read-only and governed by Jason identity/authority and the Central Orchestrator.
- ChatGPT workspace app published as **Jason**.
- Workspace state observed as Enabled / Workspace default / All actions enabled.
- Current intended tool surface remains:
  - `jason_mcp_status`
  - `discover_capabilities`
  - `execute_read_capability`
- No write tool is part of this baseline.

## Documentation completed

Primary technical record:

- `PROJECT-JASON-CHATGPT-MCP-ENTRA-FUNCTIONAL-BASELINE-2026-09-09.md`

Workspace enablement record:

- `PROJECT-JASON-CHATGPT-WORKSPACE-ENABLEMENT-2026-09-09.md`

Prior related conversational baseline:

- `PROJECT-JASON-TEAMS-DRMM-FUNCTIONAL-BASELINE-2026-08-28.md`

## Remaining item intentionally carried forward

The working MCP behavior is proven, but the implementation must still be made reproducible from version-controlled source and a source-built image.

That work is now tracked in:

- GitHub Issue **#166 — Durabilize ChatGPT MCP pilot and reproduce from source**

Issue #166 is the single source of truth for the remaining closeout work, including:

- recovering the final working MCP implementation into Git;
- adding automated tests;
- building a versioned MCP image;
- recreating the pilot without in-container mutation;
- rerunning the full external acceptance battery;
- preserving rollback until the fresh-build proof passes.

## Important do-not-break notes

Until Issue #166 is complete:

1. Do not recreate `jason-mcp-pilot` from the old image unless prepared to reapply the proven MCP changes.
2. Do not change the canonical resource URL.
3. Do not replace JWT scope validation `Jason.Read` with the fully-qualified OAuth request scope.
4. Do not break the exact issuer value `https://mcp-jason.teamaot.com/` between protected-resource and authorization-server metadata.
5. Do not remove `S256` advertisement.
6. Do not disable DNS-rebinding protection; keep the explicit allowlist.
7. Do not document or commit the ChatGPT OAuth client secret.
8. Before adding any write/consequential MCP tool, review both Jason governance and the ChatGPT workspace setting `New actions: Enable all new actions`.

## Resume point

When work resumes on this area, do **not** restart OAuth troubleshooting from the beginning.

The next task is Issue #166: recover the final working MCP source, build a durable image, recreate the pilot, and prove the same behavior from a clean deployment.

## Final checkpoint state

- **ChatGPT OAuth / Entra integration:** COMPLETE
- **MCP protocol compatibility:** COMPLETE
- **Governed read functionality:** COMPLETE
- **TeamAOT workspace enablement:** COMPLETE
- **Documentation of achieved baseline:** COMPLETE
- **Durable source/image reproduction:** OPEN — tracked in Issue #166
- **Production conversation-runtime promotion:** OUT OF SCOPE for this checkpoint

This closes the ChatGPT MCP enablement workstream for the current phase.