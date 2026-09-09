# Project Jason — ChatGPT Workspace Enablement Checkpoint

**Date:** 2026-09-09  
**Branch:** `feature/jason-runtime-service`  
**Status:** ChatGPT custom app published into the TeamAOT workspace and shown as enabled after successful end-to-end Jason MCP proof.

## Purpose

This checkpoint records the ChatGPT workspace state after the Jason MCP + Microsoft Entra functional baseline was achieved.

It complements:

- [Project Jason — ChatGPT MCP + Microsoft Entra Functional Baseline](PROJECT-JASON-CHATGPT-MCP-ENTRA-FUNCTIONAL-BASELINE-2026-09-09.md)
- [Project Jason — Teams + Datto RMM Functional Baseline](PROJECT-JASON-TEAMS-DRMM-FUNCTIONAL-BASELINE-2026-08-28.md)

The underlying functional proof remains the successful governed ChatGPT read of `AOT-50282` through Jason. This checkpoint records that the resulting custom app was subsequently published/available at the TeamAOT workspace level.

---

## Observed ChatGPT workspace state

The TeamAOT ChatGPT app details screen showed the custom app as:

- **App name:** `Jason`
- **Status:** `Enabled`
- **Availability:** `Workspace default`
- **Availability description:** applies to everyone in the workspace
- **MCP URL:** `https://mcp-jason.teamaot.com/mcp`
- **Permissions:** `Workspace default`
- **Actions:** `All enabled`
- **New actions policy:** `Enable all new actions`
- **Category:** `Other`
- **Developer:** `App developer`
- **Catalog:** `TeamAOT`
- **Version:** `1.0.0`

This UI state is important because it demonstrates that Jason moved beyond an isolated draft/test app and became a workspace-managed ChatGPT app with its MCP action surface enabled.

---

## What this proves

Taken together with the functional baseline, the workspace state demonstrates all of the following:

1. The Jason custom app can be created successfully in ChatGPT.
2. The app can complete Microsoft Entra-backed OAuth.
3. The app can discover and invoke Jason's MCP tool surface.
4. A real governed read can return live operational evidence.
5. The app can be published into the TeamAOT catalog/workspace.
6. The workspace can mark Jason enabled.
7. The workspace can keep the Jason action surface enabled.
8. The public MCP URL remains `https://mcp-jason.teamaot.com/mcp`.

This is the workspace-availability milestone for the ChatGPT client surface.

---

## Governance interpretation

`Enabled`, `Workspace default`, and `All enabled` in ChatGPT do **not** supersede Jason governance.

The trust model remains:

`ChatGPT workspace permission -> Entra authentication -> Jason identity binding -> Jason authority -> active read-only capability -> Central Orchestrator -> governed evidence`

The ChatGPT workspace setting determines whether the app/actions are available to ChatGPT users. It does not grant direct Datto RMM access, expose provider credentials, or create write authority inside Jason.

Jason's MCP service remains read-only at this checkpoint.

---

## New-actions policy note

The workspace UI showed:

`New actions: Enable all new actions`

This is convenient during the controlled Jason pilot, but it is an explicit operational consideration for future MCP expansion.

If a future Jason MCP release introduces additional tools, ChatGPT may make those newly discovered actions available automatically according to this workspace setting. Therefore:

- the MCP server must continue to expose only intentionally approved tools;
- write/mutation tools must not be introduced casually;
- any future expansion beyond the current governed read surface should receive a deliberate security/governance review;
- the workspace `New actions` policy should be reconsidered before introducing consequential MCP actions.

At the current checkpoint this does not create write risk because Jason's exposed MCP interface is intentionally read-only.

---

## Current supported MCP surface

The intended Jason MCP tool surface at this checkpoint is:

- `jason_mcp_status`
- `discover_capabilities`
- `execute_read_capability`

The first confirms pilot/read-only state, the second discovers currently active governed read capabilities, and the third executes one authorized read through Jason governance and the Central Orchestrator.

No write tools are part of this baseline.

---

## Operational acceptance state

The ChatGPT client surface should now be considered to have achieved three distinct milestones:

### 1. Protocol/authentication baseline — achieved

- public MCP reachability;
- protected-resource discovery;
- OAuth authorization-server compatibility metadata;
- PKCE/S256 advertisement;
- Microsoft Entra authentication;
- correct resource/scope handling;
- public-host transport security.

### 2. Functional governed-read baseline — achieved

- ChatGPT can invoke Jason;
- Jason can execute an authorized live read;
- Jason returns bounded governed evidence;
- ChatGPT can produce a useful grounded operational answer.

Representative proof:

`who is logged into aot-50282`

returned the provider-reported last logged-in user association and online state through Jason.

### 3. TeamAOT workspace availability baseline — achieved

- app appears as `Jason`;
- status is `Enabled`;
- availability is workspace default;
- actions are enabled;
- TeamAOT catalog entry is present;
- version shown as `1.0.0`.

---

## Remaining engineering distinction

Workspace enablement does **not** eliminate the durability warning documented in the MCP/Entra functional baseline.

The working MCP pilot code still needs to be made reproducible from version-controlled source and a rebuilt image rather than relying on in-container mutation.

Therefore the correct status is:

- **ChatGPT workspace integration:** achieved
- **End-to-end governed functionality:** achieved
- **Workspace enablement/publication:** achieved
- **Durable reproducible MCP deployment:** still requires engineering closeout
- **Production conversation-runtime promotion:** not part of this checkpoint

---

## Checkpoint conclusion

**Workspace enablement baseline: ACHIEVED.**

As of 2026-09-09, TeamAOT has an enabled ChatGPT `Jason` app pointing to the governed Jason MCP endpoint, with the workspace action surface enabled and a successful live governed read already demonstrated.

The immediate technical priority remains to convert the proven pilot implementation into a durable version-controlled MCP build and repeat the acceptance battery from a freshly recreated container.