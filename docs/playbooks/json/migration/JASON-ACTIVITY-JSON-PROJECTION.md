# Jason Activity Log — JSON domain projection candidate

## Section Goal
Preserve the existing deterministic, append-only Jason Activity Log
projection as a source-bound PMv4 JSON candidate, using the existing
`managed_ticket_notes` renderer and `autonomy_ticket_activity` store
without creating a new runbook registry, provider transport, or execution
authority.

## Source and status
- Legacy `jason_activity_log@1.0.0`;
  `docs/playbooks/Jason-Activity-Log.md`,
  Git blob `727db8ae9808c3464e1f4eb348944ee4542c64c5`.
- JSON candidate `candidates/jason_activity_log.v1.json`,
  `1.0.0-migration.2`, canonical fingerprint
  `84755d1fc0bccc58ca34dd27dcb536ebd47d03a6d0aee95a2c8bb40137dccdb6`.
- `autonomy.activation=shadow`, `direct_provider_access=false`.
- No JSON version is staged or activated in production. No legacy worker
  scheduling or ticket activity logic is disabled.

## Existing-source deterministic behavior
`json_activity_projection.py` reuses
`render_activity_chunks`, `managed_note_mutation` and
`exact_named_note` from the current deployed note module. It consumes
the existing local activity list and a separate existing-governed
`service.ticket.notes.search` response, checks current ticket/company
identity and the specific Jason creator, and produces immutable prospective
note create/update/noop instructions. It NEVER executes those actions.

- Consecutive duplicate phase/reason records are suppressed.
- Rollover to `Jason Activity 2`, `Jason Activity 3` is deterministic.
- An existing note must have exact internal visibility and the configured
  Jason execution resource; technician/client/workflow notes are protected.
- Existing historical content cannot be overwritten with a non-prefix
  replacement.
- Duplicate title, partial list, wrong company, wrong ticket, missing
  creator and non-append revisions are rejected before planning any action.
- Source JSON includes separate `service.ticket.note.create` and
  `service.ticket.note.update` steps requiring independently verified
  exact immutable Owner promotion. The JSON itself cannot grant approval.

## Independent synthetic acceptance evidence
`implementation/runtime_service/tests/test_json_activity_projection.py`
compares the candidate planner to the deployed pure rendering functions
and checks new/create, unchanged, append, rollover, duplicate titles,
cross-tenant, non-Jason creator, client visibility, incomplete pagination,
source activity identity, and no unintended provider call. Interpreter
branch tests reject missing approval facts. No credentials, provider
endpoint or protected production runtime were touched.

## Unresolved full parity gates
- Existing local `autonomy_ticket_activity` read must be composed with the
  shared runtime as a trusted, client-bound source, not a user-passed fact.
- A multi-chunk append/rollover operation needs durable ordered batch
  scheduling and per-note reconciliation using existing runtime mechanics,
  with no duplicate write after process death.
- Exact provider response/readback and immutable `service.ticket.note.update`
  creator/visibility audit require independent preproduction acceptance
  and current owner promotion; the source-only planner is not an execution
  bridge.
- The actual production note update surface may be source-only or disabled
  and must not be activated by JSON alone.

## Section Goal closure
**Pure projection parity: validated in synthetic source tests.**
**Full legacy parity / provider-connected acceptance: NOT VERIFIED.**
**Accepted source replacement: NO.**
**Production JSON activation / legacy retirement: NOT AUTHORIZED.**
