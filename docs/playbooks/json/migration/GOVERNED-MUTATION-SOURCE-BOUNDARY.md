# PMv4 JSON — Existing Governed Action Gateway Source Boundary

## Section Goal
Prove an exact JSON-produced modifying intent can be passed through Jason's
**existing** `GovernedAutonomyActionPort` with its exact versioned Owner
promotion, while preventing duplicate provider execution following uncertain
network or process outcomes. This source component is NOT wired into the
production Ticket Core or JSON dispatcher and has no authority to activate
a playbook or grant a provider action.

## Exact initial scope
- Existing legacy `unsupported_triage_human_review` — reviewed source-only
  JSON candidate `1.0.0-migration.1`.
- Only modifying operation: `service.ticket.update`.
- Exact pilot ticket IDs come from the immutable JSON document and remain
  narrow: 143305 or 143272.
- Intended payload: `{"payload":{"id":<exact ticket>,"queueID":"Help Desk I","status":"Human Review"}}`.
- Exact source/target/client/version/step/capability/arguments/readback fields
  bind the stored intent SHA256; tampering rejects before any provider call.
- No customer-facing note or notification, no reboot/network reset/service
  restart, and no other mutation capabilities.

## Existing architecture, not parallel authority
1. The canonical JSON interpreter emits a candidate `remediation` instruction;
   only a modifying, explicitly approval-required step is eligible.
2. The **existing** client-bound governed Observe port obtains the current
   unique Autotask ticket and the managed internal investigation note.
   `playbook_ticket_evidence.handoff_identity_facts` checks the exact ticket,
   company, ownership, source queue/status, resource assignment, source
   snapshot, note title/body, and reviewed pilot allowlist. Untrusted
   preflight booleans cannot replace these reads.
3. An isolated SQLite checkpoint durably claims the exact run, step and
   immutable intent before invoking the existing Owner-promotion-bound
   `GovernedAutonomyActionPort`. Only that gateway uses the existing Central
   Orchestrator and service identity for the actual action.
4. Even a successful gateway acknowledgement is insufficient for completion.
   Fresh `service.ticket.read` via the same client-bound governed read port
   must show the exact ticket/company and expected numeric queueID/statusID
   from the reviewed JSON `expected_state`.
5. After indeterminate response or interruption, the same claim must **never**
   dispatch again. A separate reconciliation step can only confirm the
   mutation through a fresh governed ticket read; it never accepts a caller-
   supplied `readbackVerified` flag and never calls the provider write API.

## Evidence and limits
- `implementation/runtime_service/tests/test_json_governed_mutation_bridge.py`
  covers positive exact promotion and independent readback, no-grant and
  wrong-version denial, synthetic provider denial, missing receipt, missing
  field readback, uncertain-result no-replay, preclaimed crash/restart, fresh
  reconciliation, cross-client identity, stale/missing managed note, and
  modified intent fingerprint/action fields.
- All tests use in-memory mocked Autotask and a synthetic SQLite promotion
  store. No actual Owner approval is granted or consumed.
- **Not production acceptance.** The bridge is source-only; it must be
  wired through a separately governed nonproduction runtime, tested with
  a real authorized read port and provider action/readback, and audited
  under an exact approved release before any production JSON mutation.
- This proof covers ONE narrowly scoped handoff. It does NOT confer reusable
  write authority across other JSON playbooks. Other mutations need their
  own exact, independently verified before/after evidence normalization.
- A document is not considered fully migrated merely because this bridge
  exists; complete legacy-specific retries, note handling, owner state,
  scheduling, and end-to-end behavior parity remain separate acceptance gates.

## Section Goal closure
Source-level one-shot intent and replay safety: PASS only at a passing
CI revision. Environment-bound operational acceptance: NOT VERIFIED.
Production activation or legacy retirement: NOT AUTHORIZED.
