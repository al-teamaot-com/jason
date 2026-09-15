# Project Jason Good Snapshot — Generic Governed Execution

Date: 2026-09-15
Status: GOOD SNAPSHOT / KNOWN-GOOD PRODUCTION STATE

## Snapshot purpose

This document records the first known-good production state in which Jason's MCP exposes the generic governed action surface in production, with Autotask internal-note creation and bounded Autotask ticket update active, hardened action-result projection, durable MCP credential bootstraps, and Datto RMM component execution present in source/credentials but deliberately dormant.

This is a recommended restore/continuation point for future Project Jason work.

## Authoritative source

Repository: `al-teamaot-com/jason`

Authoritative branch:
`feature/jason-generic-governed-execution-20260915`

Authoritative head:
`f835ec39b942074a38581124fe94da0d982d1c2d`

Commit message:
`Bound generic governed action results`

Draft integration PR:
PR #186 — `Generic governed execution for Autotask and Datto RMM`

PR remains draft/open/unmerged. Do not merge to main without an explicit merge decision.

## Production MCP state

Production container:
`jason-mcp-pilot`

Production image:
`jason-mcp:generic-governed-f835ec39b942`

Production image ID:
`sha256:a11724a816b7cc6a3e0fa16259b2d3e18323e7795f12fde0a0b79e4264fab857`

Production source revision label:
`f835ec39b942074a38581124fe94da0d982d1c2d`

Production mode:
`governed-read-plus-actions`

Central Orchestrator remains the governed execution path.

`direct_provider_access=false`

`write_tools_enabled=true`

Live active write capabilities:
- `service.ticket.note.create`
- `service.ticket.update`

Datto component execution is deliberately dormant.

## Live MCP tool surface

Verified live tools:
- `jason_mcp_status`
- `discover_capabilities`
- `execute_read_capability`
- `execute_governed_capability`
- `create_autotask_internal_note`

The generic governed execution MCP tool is active in production.

Important client-side note: an already-open ChatGPT conversation may still have an older cached MCP tool schema and may not expose `execute_governed_capability` until a fresh chat/session reloads the Jason connector schema.

## Governance state

Generic governed actions require:
- authenticated requester identity
- trusted Jason identity
- active executable capability
- exact authority evaluation
- risk/approval rules from capability metadata/authority
- Central Orchestrator execution
- bounded per-execution approval where applicable
- preserved tenant/client scope
- idempotency/attempt controls
- fail-closed behavior
- bounded output and audit evidence

Current action authority model reported by the live MCP:
`jason_exact_grant_plus_per_execution_approval`

Initial write pilots remain Owner-only.

## Autotask internal-note capability

Capability:
`service.ticket.note.create`

Activation profile:
`owner-internal-note-v1`

Security properties:
- Owner pilot scope
- requester impersonation required
- dedicated `autotask.write` credential path
- exactly one provider mutation attempt
- readback verification required
- note visibility remains internal (`noteType=3`, `publish=1`)
- creator/requester attribution is verified
- arbitrary provider response data is not exposed through the generic MCP result projection

The dedicated `create_autotask_internal_note` tool remains present for compatibility during the transition to the generic action surface.

## Autotask ticket-update capability

Capability:
`service.ticket.update`

Activation profile:
`owner-ticket-update-v1`

Allowed mutation fields:
- `status`
- `priority`
- `queueID`
- `assignedResourceID`
- `dueDateTime`

Security properties:
- Owner pilot scope
- requester impersonation required
- dedicated `autotask.write` credential path
- exactly one provider PATCH attempt
- requester-impersonated GET readback required
- every changed field must match readback
- maximum attempts = 1
- idempotency required
- arbitrary provider response data is not exposed through the generic MCP result projection

Pilot recommendation: use `status`, `priority`, or `queueID` first. Avoid `dueDateTime` in the first live pilot because provider datetime normalization may differ while the current verifier compares the normalized string value exactly.

## Hardened generic action-result boundary

Commit `f835ec39b942074a38581124fe94da0d982d1c2d` replaced broad propagation of `result.output["data"]` with capability-specific projection.

Current projection behavior:

### `service.ticket.note.create`
Exposes only bounded verification facts such as:
- verification availability
- readback verified
- ticket note reference
- impersonator recorded

Provider payload and creator-resource attribution are not passed through generically.

### `service.ticket.update`
Exposes only bounded verification facts such as:
- verification availability
- readback verified
- ticket reference
- bounded list of verified fields

Arbitrary provider response objects are not passed through.

### `automation.component.execute`
When eventually activated, projection is limited to bounded status/readback/allowlist facts and only whether a job reference exists; raw provider job UID is not exposed generically.

### Unknown future actions
Unknown generic action output fails closed with no arbitrary result exposure.

Contract tests cover raw-provider-data suppression.

## Datto RMM component execution state

Canonical capability:
`automation.component.execute`

Provider:
`datto_rmm_component_execution`

Activation profile when eventually used:
`owner-diagnostic-v1`

Current production state:
DORMANT / NOT ACTIVE

The separate Datto execution credential is mounted and durable, but no execution profile/component/device allowlist is configured in production.

Important constraints for first Datto pilot:
- exact allowlisted component only
- exact noncritical endpoint only
- Owner only
- no arbitrary shell/PowerShell
- no conversation-supplied component variables in first pilot
- one quick-job mutation request only
- bounded job-status readback
- maximum attempts = 1
- fail closed if terminal success cannot be verified

Do not invent component UID, endpoint UID, component name, allowlist name, or device class.

## Durable MCP credential bootstrap state

All required MCP AppRole bootstrap files were recovered to durable host storage under:
`/var/lib/jason/runtime-secrets/openbao/`

Recovered durable identities include:
- Microsoft Graph directory read
- IT Glue read
- Autotask read
- OpenAI semantic intent
- Autotask write
- Datto RMM execution

Durable credential files are intentionally protected as:
- owner UID: `0` (root)
- group GID: `1000` (MCP runtime group)
- mode: `640`

This matches the runtime requirement that MCP runs as UID/GID `1000:1000` while root retains file ownership.

Do not regress these recovered files to `root:root 600`, because the MCP process would be unable to read them and `/healthz` would fail with `ConnectorCredentialUnavailableError` / permission denied.

Existing Datto RMM read bootstrap remains on its established durable path and legacy MCP destination.

## Proven image ancestry

Proven base image tag:
`jason-mcp:datto-pagination-6da45b3ef66d`

Proven base image ID:
`sha256:320015a9196bacab883149da8257a40f1061ab002c50b14c694975e979989b49`

The generic governed production image was built from this exact proven base.

Do not guess or substitute another base when reproducing this snapshot.

## Rollback asset

Preserved rollback container from the successful production promotion:
`jason-mcp-rollback-pre-f835ec3-20260915T161544Z`

Rollback image ID:
`sha256:7c574cc5d2080c249e18b3114a090f7be8a221ae7f97f231c50c8e655ac322b6`

Previous production image:
`jason-mcp:internal-note-d5d3e8bc3810`

This rollback container was intentionally preserved after successful acceptance and is the immediate rollback target for this snapshot.

## Production acceptance evidence

Successful production promotion verified:
- authoritative local/remote source pin at `f835ec39...`
- clean worktree
- exact candidate image ID
- durable credential presence and permissions
- production container creation
- live image parity
- live process running
- live MCP mode `governed-read-plus-actions`
- active Autotask note-create and ticket-update capabilities
- Datto execution absent from active writes
- live MCP tool surface correct
- hardened generic action output boundary active
- public `/healthz` returned HTTP 200
- public mode reported `governed-read-plus-actions`
- unauthenticated public MCP initialize returned HTTP 401
- source revision label matched authoritative head

Final deployment result:
`PRODUCTION_DEPLOYMENT=PASS`

## Known unsuccessful attempts that are now resolved

### Missing durable mount sources
Earlier deployment preflight found vanished host bind-source files for Microsoft Graph, IT Glue, Autotask read, and OpenAI semantic credentials. These were recovered from the still-running production container into durable host paths.

### Invalid Docker mount syntax
An intermediate candidate create used bare `,rw` / `,ro` in `--mount`; Docker requires read-write to omit the option and read-only to use `readonly`. This was corrected.

### Candidate HTTP 500 after credential recovery
Recovered files were initially `root:root 600`; the candidate MCP runs as UID/GID 1000 and could not read the OpenAI RoleID. Credential files were corrected to `root:1000 640` and candidate health then passed.

### False smoke success due to missing stdin attachment
Earlier heredoc-based `docker exec` smoke commands omitted `-i`, so test bodies did not execute. All later contract/health checks use `docker exec -i` and are authoritative.

## Protected source/worktree rules

Protected primary repository:
`/home/al/projects/jason`

Do not reset, clean, stash, pull, rebase, repair, or run GC there.

Current isolated integration clone/worktree:
`/home/al/jason-worktrees/generic-governed-execution-clean-20260915T153224Z`

GitHub remains authoritative.

Never use `git add .` or `git add -A`; stage exact files only.

## Current next goal

Next immediate goal is the first real bounded Autotask ticket-update pilot through `execute_governed_capability`.

Recommended pilot:
- Owner requester
- XYZ Test Company / controlled test ticket
- one reversible field change
- prefer `status`, `priority`, or `queueID`
- record original value
- perform one governed update
- require post-mutation readback verification
- if appropriate, restore original value through a separate explicitly approved governed action

No direct-provider bypass should be used for the pilot.

Because an existing ChatGPT conversation may have cached the old MCP schema, a fresh ChatGPT conversation may be required before `execute_governed_capability` is visible to the client.

Estimated rounds from this snapshot to first successful Autotask ticket-update pilot: approximately 1–3, assuming no new provider-side authorization issue.

## Subsequent goal

After the Autotask ticket-update pilot, proceed to Datto RMM component execution only after identifying:
- exact approved diagnostic/read-only component
- exact noncritical endpoint
- exact allowlist name
- exact provider component UID/name
- exact endpoint UID/device class

Estimated additional rounds for Datto pilot: approximately 2–5 depending on provider metadata validation and first job behavior.

## Snapshot classification

GOOD SNAPSHOT: YES

PRODUCTION KNOWN-GOOD: YES

ROLLBACK PRESERVED: YES

GITHUB AUTHORITATIVE HEAD RECORDED: YES

GENERIC GOVERNED EXECUTION ACTIVE: YES

AUTOTASK INTERNAL NOTE ACTIVE: YES

AUTOTASK TICKET UPDATE ACTIVE: YES

ACTION OUTPUT BOUNDARY HARDENED: YES

DATTO COMPONENT EXECUTION ACTIVE: NO — DELIBERATELY DORMANT

DIRECT PROVIDER ACCESS: NO

NEXT STEP: REFRESH CLIENT TOOL CATALOG IF NEEDED, THEN RUN ONE BOUNDED AUTOTASK TICKET-UPDATE PILOT
