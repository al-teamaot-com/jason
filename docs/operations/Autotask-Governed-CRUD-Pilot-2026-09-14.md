# Autotask Governed CRUD Pilot — 2026-09-14

> **Current-state note — 2026-09-16:** This document preserves the design, authority model, and acceptance plan as they existed on 2026-09-14. It is no longer the current resume point. The later bounded live pilot successfully exercised `service.ticket.update` on controlled ticket `T20191013.0001`, changing priority `3` to `2`, and a fresh governed read on 2026-09-16 confirmed `priority=2`. Current state and next actions are recorded in `docs/sessions/Jason-Governed-Execution-Checkpoint-2026-09-16.md` and `docs/control/CURRENT.md`. Nothing in this historical document independently authorizes another mutation.

## Accepted authority model

AOT approved Autotask's requester security profile as the authoritative maximum permission boundary for Autotask operations performed through Jason.

Jason may further restrict an operation through its own Owner/Admin/Tech/RO role, client/resource scope, risk policy, approval policy, target-resolution rules, or other governance controls. Jason must never grant a requester more Autotask authority than that requester's effective Autotask security profile permits.

Provider service credentials are execution credentials only. They do not confer requester authority. Autotask also requires the API execution identity itself to possess the applicable entity permission, so a mutation proceeds only when both the execution identity and the impersonated requester are permitted by Autotask.

## Initial pilot scope

The first governed mutation slice is limited to:

- Tickets: read/search, create, partial update.
- Ticket Notes: read/search, create, partial update.

Autotask currently documents Tickets and TicketNotes as create/update/query capable and not delete capable. The pilot therefore does not invent delete support for these entities. A future delete capability may be added only for an entity where Autotask supports deletion and the complete Jason + requester authorization chain permits it.

## Credential separation

The accepted production read connector continues to use the logical secret `autotask.readonly`.

The mutation connector uses a distinct logical secret, `autotask.write`, mapped to a separate OpenBao secret path. The mutation connector does not advertise or execute reads, and the read connector does not advertise or execute mutations.

The intended `autotask.write` credential must be a separate Autotask API-only execution identity/security profile restricted to the minimum provider permissions required for the approved Ticket and TicketNote pilot plus provider-native impersonation. It must not be implemented by broadening the accepted `autotask.readonly` profile merely for convenience.

A live read-only schema check of the currently accepted read credential reported Ticket create/update access as `None`. That is expected for the accepted read-only path and confirms that the existing read credential must not be reused for mutation execution.

No `autotask.write` credential has been provisioned or activated by this source work.

## Provider-enforced requester authority

All Autotask mutations must use provider-native requester impersonation.

Required chain:

1. authenticate the human through Jason's trusted identity path;
2. resolve the Jason identity to one active trusted email binding;
3. resolve that trusted email to exactly one active Autotask Resource;
4. resolve only the dedicated write execution credential;
5. use the requester Resource as `ImpersonationResourceId` on the Autotask request;
6. perform an impersonated `entityInformation` preflight for the target entity/action when available;
7. allow Jason policy to restrict the action further;
8. issue the mutation with the same impersonated requester identity;
9. treat the actual Autotask mutation response as the final provider enforcement result;
10. verify the resulting durable state and audit the result.

There is no Jason-managed/service-account requester-authority fallback for writes. Missing, ambiguous, or unverifiable requester identity fails closed. If provider-native impersonation is not explicitly active, Jason must fail before resolving the write execution credential.

`userAccessForCreate` / `userAccessForUpdate` preflight values are explainability and early-denial evidence. `None` denies before mutation. `Restricted` is not treated as universal permission; the concrete provider operation remains authoritative for record-level conditions.

## Initial acceptance target

- Test company: **XYZ Test Company**.
- Live governed read confirmed that this name resolves to exactly one active Autotask company record.
- Initial live requester: **Al Davis only**.
- Lindsey and Adam are intended to begin as Jason **Tech** users later, but they are not part of the first live-write acceptance test.

No production Autotask mutation is authorized by this document. Source implementation, unit tests, dry-run/preflight validation, and read-only provider validation may proceed. The first live create/update under `XYZ Test Company` requires a separate explicit approval immediately before execution.

## Safety requirements

- Write capability remains disabled by default and must require an explicit runtime enablement gate.
- Provider-native impersonation is mandatory for every mutation.
- Exact requester-to-Autotask-Resource mapping is mandatory.
- Read and write execution credentials remain separate.
- The mutation connector may resolve only `autotask.write`; the ordinary read connector remains on `autotask.readonly`.
- The mutation connector exposes no read operations, preventing privileged write credentials from becoming a general read path.
- Ticket updates use bounded partial update semantics (`PATCH`), not full replacement (`PUT`).
- Update operations require a positive durable entity id in the request payload.
- No arbitrary entity write endpoint is exposed in the pilot; only the approved Ticket and TicketNote operations are compiled.
- No delete endpoint is exposed for Tickets or TicketNotes.
- Source-level provider-neutral mutation definitions remain non-active and unregistered in production composition.
- No mutation is exposed through MCP until the Central Orchestrator write/action authorization path, auditing, approval behavior, and live acceptance are proven.
- Failed or indeterminate authorization must release no write authority and must not retry as the API service account.
- Every mutation must be attributable to the authenticated Jason principal and the impersonated Autotask Resource without exposing credentials or secret material in audit records.

## Initial capability intent

Provider operations implemented behind the dormant governed write foundation:

- `autotask.ticket.create` -> `POST /V1.0/Tickets`
- `autotask.ticket.update` -> `PATCH /V1.0/Tickets`
- `autotask.ticket.note.create` -> `POST /V1.0/TicketNotes`
- `autotask.ticket.note.update` -> `PATCH /V1.0/TicketNotes`

Provider-neutral source-only capability definitions:

- `service.ticket.create`
- `service.ticket.update`
- `service.ticket.note.create`
- `service.ticket.note.update`

These definitions remain in `BUILDING` lifecycle state, high risk, owner-approval-required, and are not registered by production composition. Adding connector/catalog source does not itself authorize or advertise production write capability.

## Acceptance sequence

1. Build dormant connector write primitives and fail-closed requester/profile preflight.
2. Add unit/regression coverage proving no service-account fallback, no read-through-write-credential path, and no unsupported delete path.
3. Add provider-neutral write/action capability definitions in non-active lifecycle state without production registration.
4. Keep the accepted read-only execution profile unchanged and provision a separate minimum-permission Autotask API-only write execution identity plus OpenBao `autotask.write` secret as a distinct controlled change.
5. Prove Al's trusted identity binding and exact Autotask Resource resolution read-only.
6. Prove provider-native requester impersonation using bounded read-only probes.
7. Prove impersonated `entityInformation` access for Ticket create/update and TicketNote create/update using the dedicated write execution identity, without sending a mutation.
8. Stop for explicit approval before the first live mutation.
9. Under that approval, create one disposable ticket in **XYZ Test Company**, verify attribution and permissions, update it, add/update a note, and verify the resulting records.
10. Keep write capability disabled if any permission, attribution, scope, audit, or verification result is ambiguous.
11. Only after successful acceptance may production activation be proposed as a separate governed change.
