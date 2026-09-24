# Jason Direct Ticket Update Canonicalization — Production Acceptance

**Date:** 2026-09-24  
**Support item:** SUPPORT-CAP-019  
**Capability:** `service.ticket.update`  
**Outcome:** Resolved and production-proven

## Scope

This record preserves the production fix and bounded acceptance evidence for the direct Autotask ticket-update canonicalization defect that surfaced as `EXECUTION_PLAN_AUTHORIZATION_REJECTED`.

The defect affected ordinary technician-friendly `service.ticket.update` requests. Special `begin_work` and `return_work` transitions were already canonicalized, but ordinary direct updates could reach execution-plan preparation without the provider-required structured payload and authoritative positive numeric ticket ID.

No execution-plan, approval, provider-isolation, Central Orchestrator, or readback control was bypassed to resolve the issue.

## Root cause

The MCP governed-action boundary returned ordinary `service.ticket.update` arguments unchanged.

As a result, inputs such as `ticket_id` or `ticketID` plus a mutable field such as `status` could reach the Autotask update planner without:

- `payload.id` containing the exact positive numeric Autotask ticket ID; and
- the requested mutable fields inside the structured `payload` envelope.

Observed pre-provider failures included `ticket update requires a structured payload` and `id must be a positive integer`. The provider was not invoked.
## Implemented correction

Fix commit: `17ca474de031efd87200fa46ad408f0f8a8ef14a`.

The generic MCP canonicalization boundary now:

- accepts exact ticket selectors `ticket_id`, `ticketID`, or `id`;
- rejects missing, malformed, non-positive, conflicting, or ambiguous ticket identity;
- confirms the authoritative numeric ticket ID through governed `service.ticket.read`;
- emits `payload.id=<authoritative positive numeric ticket ID>`;
- retains only explicitly requested allowed mutable fields;
- preserves symbolic values such as `status="Complete"` until the existing authoritative Autotask symbolic-resolution step;
- fails closed on ambiguous symbolic mappings; and
- completes canonicalization before approval reservation, intent fingerprinting, and execution-plan authorization.

The fix is generic for ordinary `service.ticket.update` operations and is not specific to OWNI7JAN25.

## Regression evidence

After rebasing onto the then-current `main`:

- MCP lifecycle/canonicalization tests: **48/48 passed**;
- Autotask ticket-update tests: **15/15 passed**;
- execution-plan binding tests: **12/12 passed**;
- `git diff --check`: passed;
- Python compilation checks: passed.

Coverage includes numeric `ticket_id`, the `ticketID` alias, malformed/non-positive/missing/conflicting identity, authoritative ID confirmation, existing-payload normalization, symbolic `Complete`, ambiguous symbolic resolution, deterministic re-prepare fingerprint stability, execution-plan mismatch fail-closed behavior, exactly one provider PATCH, and post-write readback verification.
## Production promotion

PR #249 merged the fix as production source `5244e9e41ac86a366fc475b37be0559919fdc968`.

Production MCP image:

`sha256:785279fe3ea25145dea7e55bd4256656999adc4bd7fc2f838cbf66877f7ba901`

Deployment evidence:

- deployment preflight: PASS;
- hardening verification: PASS;
- health check: PASS;
- image alias promotion: PASS;
- MCP governance post-check: PASS;
- governed execution: Central Orchestrator;
- `direct_provider_access=false`;
- rollback container preserved as `jason-mcp-pilot-rollback-20260924T151156Z`.

At documentation closeout, the production runtime image remained independently pinned to source `fe75d15304a294fe20193c5c837f9f99be74e4ee`; this change required only MCP promotion.

## Bounded production acceptance

Acceptance target:

- endpoint/context: OWNI7JAN25;
- Autotask ticket: `T20260905.0004`;
- Autotask ticket ID: `139815`;
- configuration item: `1256`;
- pre-write status: In Progress (`8`).

The latest governed ticket evidence stated that the original VulScan finding was no longer present and the ticket was ready for completion. No newer blocker was present in the ticket history.
Exactly one governed `service.ticket.update` mutation was performed.

Authorized execution evidence:

- approval ID: `approval_mcp_fdfaab04772f469bb87925521c25a0ef`;
- execution ID: `exec_mcp_action_2394b8b355f34b38bf2a9cd259015ccf`;
- correlation ID: `corr_mcp_action_ec27baa18b6d495aae03627762ca3bde`;
- intent fingerprint: `28ddf52db91504791cde71da36ea35a8e4ef86fea84e05023b9cb38146fa9b90`;
- execution-plan fingerprint: `c2af672ccbbadb634d9079f3dea45c40ef3616e9b57bc3644d6019ca4c219121`;
- selected provider: `autotask_ticket_update`;
- provider capability: `autotask.ticket.update`;
- method/path: `PATCH /V1.0/Tickets`;
- target resource: service ticket `139815`;
- normalized provider payload: `{"id":139815,"status":5}`;
- symbolic resolution: `Complete -> 5`;
- provider attempts: **1**;
- built-in post-write readback: **verified**.

Successful Central Orchestrator execution confirms the independently re-prepared execution plan matched the authorized execution-plan fingerprint before provider invocation. A plan mismatch would have failed closed with zero provider writes.

An independent governed post-read, correlation `corr_mcp_c3089e750d114265bd2b8ef883d693ad`, confirmed authoritative Autotask status `5` / Complete and completion time `2026-09-24T15:16:37.167Z`.

## Durable operating rule

Technician-friendly direct ticket updates must be canonicalized into the exact provider-shaped governed request before approval and execution-plan binding. Symbolic values must resolve through authoritative provider metadata during plan preparation. Ambiguous identity or symbolic mapping must fail closed. No direct-provider fallback is permitted.

SUPPORT-CAP-019 is closed.
