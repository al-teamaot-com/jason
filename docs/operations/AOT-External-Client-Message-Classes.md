# AOT External Client Message Classes — TODO-COMM-001

**Status:** Source-only design clarification, 2026-11-08. This specification is
not autonomous-send authority, content approval, or a production-release grant.

## Section Goal

Jason can choose the appropriate **preapproved canned or tightly parameterized
client-facing communication**, without being limited to information-gathering
questions. It must independently verify authority, the exact customer, recipient,
ticket, supporting facts, sending outcome, and durable follow-up.

This document extends the existing governed client-communications framework
(TODO-COMM-001 / GitHub #947). It does **not** create another communication
service or a separate source of approved wording.

## Content classes

| Class or group | Examples of purpose | Default delivery policy |
| --- | --- | --- |
| `status_update` | Work accepted/started, diagnostic progress, waiting on an internal action or vendor | Routine only after exact policy and template approval |
| `resolution_confirmation` | Work completed, independently verified fix, request for confirmation | Routine when evidence and approved template permit |
| `scheduling_coordination` | Approved maintenance window, appointment coordination, expected next update | Routine only with verified times and no unsupported commitment |
| `clarification.single_observation` | One necessary question when Jason cannot obtain information internally | Existing 120-question catalog; independent send authority still required |
| `expected_behavior.explanation` | Evidence-backed expected behavior or vendor-known limitation | Requires a supporting authoritative source and content policy |
| `simple_instruction` | One safe next step for the recipient | Approved low-risk instructions only |
| `approval_request` | Ask client to authorize a specific action or change | Approval-gated; a sent question is not permission to perform the action |
| `multi_step_diagnostic` | Client-assisted procedure with branching or side effects | Technician review/explicit policy approval required |
| `security_incident` | Vulnerability, threat, incident or sensitive exposure notice | Restricted content, recipient, audience and approval rules |
| `restricted_business` | Billing, legal, HR, contractual or policy commitments | Human approval unless a separately approved narrow policy exists |

"Work started," "waiting," "work completed," and "patch scheduling" are
instances of the applicable message classes, **not** a new custom capability
for each message. An existing VulScan fixed notification already demonstrates
that the approved-message framework supports **non-question** content.

## Authoritative content sources

- `config/client_communications/approved.json` already contains fixed
  workflow-bound client notifications (for example the VulScan update).
- `config/client_communications/information_requests_round1.json` contains
  120 approved question texts; this is **one** content subset, not a global
  client-communication scope restriction.
- `approved_client_messages.py` is the existing deterministic renderer and
  exact workflow/template resolver.
- Every new class/template is source-controlled, reviewed, enabled separately,
  and bound to its exact workflow, content revision and permitted audience.
- The abandoned XYZ acceptance text is **not** authorization for live sending.

## Canned vs. semi-canned

**Canned:** Approved title and body reproduced byte-for-byte.

**Semi-canned:** Approved fixed text plus individually allowlisted variable
slots, for example ticket number, verified device name, confirmed maintenance
window, and proven resolution state. The authoritative upstream source and
maximum length/format for **each** slot must be specified in the template.
The connector reconstructs the final body from freshly read evidence.
Unverified input, arbitrary reply text, user-supplied recipient addresses,
unbounded prose, or unsupported dates/commitments fail closed.

The current client-question renderer proves one bounded ticket-number
substitution; additional generic variable slots **remain separate engineering
acceptance work**, not permissions implied by this specification.

## Provider and communication gates

1. Confirm `enable_jason_outbound_comm` is **explicitly True** on the exact
   Autotask Company record. Missing, False, invalid or ambiguous is OFF.
2. Confirm exact requester/playbook authority **for the message class**,
   enabled workflow/template and approved wording. The Company UDF alone
   does not permit arbitrary communications.
3. Resolve the ticket, company and contact independently; verify recipient
   preferences, client isolation, information-release permissions and sensitive
   content restrictions. No guessed recipients or blind reply-all.
4. For normal outbound communication, use the existing governed client-facing
   Autotask **TicketNote** path. Verify the actual audience and publication
   behavior for the target tenant.
5. For **TimeEntries**, record legitimate work only; a customer-visible
   summary may use approved wording if the actual labor, invoice exposure,
   native permissions and contract rules are verified. Do not create fake
   labor/time entries just to send a message.
6. Persist exact message/template/class/facts fingerprint; dedupe before
   action. Create once, verify provider readback and required matching
   `NotificationHistory` evidence. Unknown delivery never auto-retries.
7. If awaiting reply/approval, track the expected contact, decision and
   deadline; resume the correct persisted ticket workflow, or escalate
   rather than silently abandoning the dependency.

## Acceptance

Demonstrate distinct fixed non-question classes (for example status and
completion), the existing VulScan notification, a permitted single question,
and later a source-validated semi-canned message. Negative tests must prove
blocked opt-out, unknown template/class, unapproved wording, missing evidence,
wrong company/contact, unauthorized sensitive messages, duplicates, and
unknown receipt. Time-entry behavior must be separately verified before any
external time-entry communication is promoted.

No client-wide automation, new approved content or production write is
activated by this document.
