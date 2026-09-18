# Project Jason Support List

This list tracks Jason operational blockers and missing capabilities discovered during real support work. An item closes only after the blocked workflow is reproduced, corrected through the governed architecture, and verified with authoritative readback or equivalent acceptance evidence.

| ID | Priority | Status | Item | Current blocker / evidence | Acceptance criteria |
| --- | --- | --- | --- | --- | --- |
| SUPPORT-CONN-001 | P1 | Resolved 2026-09-18 | Autotask ticket read path failing through Jason | `service.ticket.search/read/count` were failing with `CAPABILITY_INVOCATION_FAILED` while the live MCP used provider-native requester impersonation for Autotask reads. The read and mutation paths shared one requester-mode gate. | Autotask reads succeed through Jason governance; write surfaces remain active; mutations retain provider-native requester impersonation, approval, provider preflight, and readback verification. |
| SUPPORT-CONN-002 | P1 | Open | MCP `UNAVAILABLE / Connection failed` interruptions | Repeated Jason MCP transport interruptions occurred during the AOT-50282 investigation, independent of the Autotask provider-read failure. | Reproduce or observe the interruption, identify the failure domain, correct it without bypassing MCP governance, and prove stable repeated MCP requests with no unexpected service restarts. |
| SUPPORT-CAP-003 | P1 | Open | Missing governed Datto AV/EDR threat-detail and remediation state | Jason could not retrieve provider-native threat details/remediation state for Datto AV threat `15884344`; `direct_provider_access=false` correctly prevented bypass. | Governed threat-detail/read capability is available; remediation remains a separately governed write capability; verify against AOT-50282 closure workflow without direct-provider bypass. |
| SUPPORT-CAP-004 | P1 | Open | Missing governed Datto alert resolution | Jason could read Datto alert `bd0882e0-8700-4985-ad89-f789b865c76e` but had no governed alert-resolve/write action. | Add a governed alert-resolution capability with bounded scope, approval safeguards as required, idempotency/attempt controls, and post-action readback verification. |
| SUPPORT-CONN-005 | P1 | Investigating | Autotask closeout workflow blocked | Ticket `T20260918.0005` / ID `140629` previously could not be completed because the read path and internal-note/update workflow were blocked; the Complete status must be resolved authoritatively and no status ID may be guessed. | Resolve the authoritative Complete status mapping, create required internal documentation, perform the bounded ticket update, and verify the resulting ticket state through post-write readback. Datto alert closure remains governed separately by SUPPORT-CAP-004. |

## SUPPORT-CONN-001 closure evidence — 2026-09-18

- Root cause confirmed: one global `JASON_AUTOTASK_REQUESTER_AUTH_MODE` controlled both reads and mutations. `impersonated` preserved writes but caused the known Autotask read failure; `jason_managed` restored reads but the mutation surfaces previously refused to initialize.
- Fix branch: `fix/jason-autotask-read-write-auth-split-20260918`.
- Fix commit: `795427ea30f51eb158b34069e5e02fbb2165c35b`.
- Focused regression result: 46 tests passed covering Autotask requester authorization, mutation connector behavior, internal-note creation, ticket update, and information authorization.
- Candidate image: `jason-mcp:support-autotask-auth-split-2d184f74e843`.
- Shadow acceptance: MCP healthy, `jason_managed` effective, write capabilities active, three repeated governed Autotask ticket reads succeeded, 30/30 health checks passed, zero restarts.
- Production cutover completed with rollback container preserved as `jason-mcp-pilot-pre-autotask-auth-split-20260918T094417` and pre-change inspect backup under `/home/al/jason-cutover-backups/`.
- Post-cutover external MCP proof: `jason_mcp_status` reports `direct_provider_access=false`, Central Orchestrator governance, and active `automation.component.execute`, `service.ticket.note.create`, and `service.ticket.update`; governed `service.ticket.read` for `T20260918.0005` succeeded through provider `autotask`.
