# Client Information Request — JSON conversion source candidate

## Section Goal
Convert the approved Round 1 client-question catalog and deterministic
selection into a source-bound PMv4 JSON workflow without generating any
client-facing communication until exact promoted source authority and
provider readback have independently passed acceptance.

## Source, expected state and scope
Legacy `client_information_request@1.0.0`,
`docs/playbooks/Jason-Client-Information-Requests-Round1.md`.
Candidate `candidates/client_information_request.v1.json`,
`1.0.0-migration.2`, canonical fingerprint
`a1848fe643728391707e1dc35096811cffcc7749d49738835ca0ae4d193430f5`.
The **only** mutation permitted by original registry is
`service.ticket.client.notification.create`.

`json_client_question_plan.py` reuses existing
`client_information_requests.load_round1_catalog`,
`select_question_from_diagnostic`, `render_question` and the 120 immutable
approved question templates. It reconstructs the exact question/footer SHA256
from the catalog; no freeform text, recipient override, or implicit
authorization is generated.

Exact ticket, company, contact, enabled email notification, evidence hash,
page-complete notes/history and routine question class must be independently
proven by the existing governed read port. Contradictory note/contact/source
facts fail closed; already described or duplicate questions produce no send.

## State, governance and independent synthetic tests
JSON declares the original states
`reserved -> send_uncertain -> delivery_pending -> awaiting_reply ->
reply_verified -> resumed`, with one allowed send per exact
ticket/question/evidence fingerprint and no blind retries. These are
declarations, NOT a second live sender.

`test_json_client_question_plan.py` tests all 120 source-controlled
questions, same-client/contact and notification preferences, no freeform
template/email override, JQ-001 no-description guard, duplicates, pending
history, completed ticket, invalid gap and hash, missing source promotion,
outbound and response readback guards. Non-routine questions remain
human-review-only. Source tests never call a real provider.

## Remaining legacy-versus-JSON acceptance gaps
- Bind existing `SQLiteClientQuestionLedger` reservations and all state
  transitions to the existing JSON runtime, including crash recovery.
- Independently verify profile, originating diagnostic promotion, exact
  owner grant and source catalog integrity.
- Add guarded `service.ticket.client.notification.create` via existing
  Central Orchestrator and real preproduction provider recipient/readback;
  only exact approved sandbox targets, never unsolicited clients.
- Prove fresh same-contact notification history and authored reply,
  10-day aging/human-review and correct originating diagnostic resume.
- Prove source-matched error, missing dependency, duplicate, outage and
  restart outcomes in isolated provider-connected preproduction.

**Full parity: NOT VERIFIED. Production activation/legacy retirement: NO.**
