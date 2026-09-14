# Autotask Governed CRUD Pilot — 2026-09-14

## Accepted authority model

AOT approved Autotask's requester security profile as the authoritative maximum permission boundary for Autotask operations performed through Jason.

Jason may further restrict an operation through its own Owner/Admin/Tech/RO role, client/resource scope, risk policy, approval policy, target-resolution rules, or other governance controls. Jason must never grant a requester more Autotask authority than that requester's effective Autotask security profile permits.

Provider service credentials are execution credentials only. They do not confer requester authority.

## Initial pilot scope

The first governed mutation slice is limited to:

- Tickets: read/search, create, partial update.
- Ticket Notes: read/search, create, partial update.

Autotask currently documents Tickets and TicketNotes as create/update/query capable and not delete capable. The pilot therefore does not invent delete support for these entities. A future delete capability may be added only for an entity where Autotask supports deletion and the complete Jason + requester authorization chain permits it.

## Provider-enforced requester authority

All Autotask mutations must use provider-native requester impersonation.

Required chain:

1. authenticate the human through Jason's trusted identity path;
2. resolve the Jason identity to one active trusted email binding;
3. resolve that trusted email to exactly one active Autotask Resource;
4. use that Resource as `ImpersonationResourceId` on the Autotask request;
5. perform an impersonated `entityInformation` preflight for the target entity/action when available;
6. allow Jason policy to restrict the action further;
7. issue the mutation with the same impersonated requester identity;
8. treat the actual Autotask mutation response as the final provider enforcement result;
9. verify and audit the result.

There is no Jason-managed/service-account fallback for writes. Missing, ambiguous, or unverifiable requester identity fails closed.

`userAccessForCreate` / `userAccessForUpdate` preflight values are explainability and early-denial evidence. `None` denies before mutation. `Restricted` is not treated as universal permission; the concrete provider operation remains authoritative for record-level conditions.

## Initial acceptance target

- Test company: **XYZ Test Company**.
- Initial live requester: **Al Davis only**.
- Lindsey and Adam are intended to begin as Jason **Tech** users later, but they are not part of the first live-write acceptance test.

No production Autotask mutation is authorized by this document. Source implementation, unit tests, dry-run/preflight validation, and read-only provider validation may proceed. The first live create/update under `XYZ Test Company` requires a separate explicit approval immediately before execution.

## Safety requirements

- Write capability remains disabled by default and must require an explicit runtime enablement gate.
- Provider-native impersonation is mandatory for every mutation.
- Exact requester-to-Autotask-Resource mapping is mandatory.
- Ticket updates use bounded partial update semantics (`PATCH`), not full replacement (`PUT`).
- Update operations require a positive durable entity id in the request payload.
- No arbitrary entity write endpoint is exposed in the pilot; only the approved Ticket and TicketNote operations are compiled.
- No delete endpoint is exposed for Tickets or TicketNotes.
- No mutation is exposed through MCP until the Central Orchestrator write/action authorization path, auditing, approval behavior, and live acceptance are proven.
- Failed or indeterminate authorization must release no write authority and must not retry as the API service account.
- Every mutation must be attributable to the authenticated Jason principal and the impersonated Autotask Resource without exposing credentials or secret material in audit records.

## Initial capability intent

Provider operations to implement behind dormant governed write capability:

- `autotask.ticket.create` -> `POST /V1.0/Tickets`
- `autotask.ticket.update` -> `PATCH /V1.0/Tickets`
- `autotask.ticket.note.create` -> `POST /V1.0/TicketNotes`
- `autotask.ticket.note.update` -> `PATCH /V1.0/TicketNotes`

Provider-neutral orchestration names and activation state remain separate from these provider operations. Adding connector source does not itself authorize or advertise production write capability.

## Acceptance sequence

1. Build dormant connector write primitives and fail-closed requester/profile preflight.
2. Add unit/regression coverage proving no service-account fallback and no unsupported delete path.
3. Add provider-neutral write/action capability definitions in non-active lifecycle state.
4. Prove identity binding and Autotask Resource resolution read-only.
5. Prove impersonated `entityInformation` results for Tickets and TicketNotes read-only.
6. Stop for explicit approval before the first live mutation.
7. Under that approval, create one disposable ticket in **XYZ Test Company**, verify attribution and permissions, update it, add/update a note, and verify the resulting records.
8. Keep write capability disabled if any permission, attribution, scope, audit, or verification result is ambiguous.
9. Only after successful acceptance may production activation be proposed as a separate governed change.
