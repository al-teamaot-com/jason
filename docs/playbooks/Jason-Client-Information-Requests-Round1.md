# Jason Playbook: Round 1 Client Information Requests

## Manifest
- ID: client_information_request
- Name: Jason - Approved Client Information Requests
- Version: 1.0.0
- Owner: AOT Service Management
- Target: Autotask ticket, same-company contact
- Trigger: A promoted diagnostic playbook has explicitly confirmed a missing client fact and selected a source-controlled gap code; or the verified client-created Jason-queue intake has a wholly empty description and no client-authored explanation.
- Ownership: Keep ticket in Jason queue; release active work slot while awaiting client reply.
- Retry: Maximum outbound attempts per ticket/question/evidence fingerprint = 1. Never blindly retry an ambiguous send.
- Recheck: On normal autonomous ticket worker cycle. Aging review target: 10 days.
- Verification source: Autotask ticket/contact/notes/NotificationHistory.
- Completion: Verified contact reply resumes original promoted diagnostic phase; not evidence that the underlying ticket is resolved.
- Autonomy: Routine text only after exact separate owner promotion and enabled activation profile. Sensitive text requires technician review. No disruptive branches.

## 1. Section Goal
Ask exactly one approved missing-information question, confirm the notification reached the ticket's authorized contact, and resume the correct diagnostic playbook on a verified contact reply. Do not declare the ticket resolved merely because the contact answered.

## 2. Trigger
An already authorized Jason diagnostic detects a required fact that is absent from available authoritative evidence. It supplies an exact catalog gap code and durable evidence fingerprint. Freeform ticket prose and model guesses are not triggers.

## 3. Scope and Boundaries
In scope: 120 approved JQ-001 through JQ-120 question texts, AOT footer, Autotask ticket notes and source-controlled message selection. Out of scope: freeform messages, other recipients, credentials, unauthorized status changes, alert resolution, endpoint modifications, reboots and network resets. Direct provider access remains prohibited.

## 4. Initial Identification
Read the exact ticket and its same-company contact. Validate current ownership, contact ID, enabled notification preference, valid contact email and ticket number. Device identification stays with the originating playbook; this playbook never guesses a device.

## 5. Expected State
Source-approved wording, no duplicate question, authorized recipient, a delivered notification, and an explicitly tracked awaiting-client state with resumption target.

## 6. State Model
reserved -> send_uncertain -> delivery_pending -> awaiting_reply -> reply_verified -> resumed. Unverifiable reads or provider errors remain pending or blocked; never infer success. A separate persisted operational-work phase is waiting_client_information:<original_phase>.

## 7. Diagnostic Workflow
Read exact ticket, exact contact, ticket note timeline, and notification history. Resolve one approved gap code to one question. Check whether an identical approved question has already been documented. Verify the missing fact was proven by the originating playbook; do not infer from a generic email subject.

## 8. Decision Gates
Require feature profile, exact owner promotion, originating playbook promotion, routine question class, corroborated missing-fact evidence, client scope, recipient and complete authoritative reads. Any mismatch fails closed.

## 9. Remediation
The only write is governed service.ticket.client.notification.create. Server reconstructs the title/body with footer and exact verified ticket number, publishes as client-facing note, and requires readback. No other action is authorized under this playbook.

## 10. Retry Policy
One outbound request per material fingerprint. Reserve before sending; if outcome is unknown, investigate using read-only note evidence rather than resending.

## 11. Periodic Rechecks
Normal worker scans reconcile pending delivery/replies. Unchanged rechecks create no new notes and no additional sends. Waiting work releases its active slot.

## 12. Aging / Stale Condition
After 10 days without a proven response, escalate to technician for review; do not send automatic nags without separately approved cadence and text.

## 13. Dependency Handling
Missing authoritative ticket/contact, notification history, provider permissions, or missing prior diagnostic evidence is a blocked dependency. Do not fill gaps from another client or bypass provider governance.

## 14. Documentation Requirements
Persist question ID, ticket ID/number, evidence hash, outgoing note ID, baseline notification ID, reply note ID, state transition and timing. Never record passwords, tokens, private keys or unnecessary client response content.

## 15. Failure Handling
On ambiguous provider write or unavailable readback, preserve send_uncertain state and avoid repeat send. On authorization, cross-company, or contact mismatch, fail closed and notify the owning technician through the existing governed path.

## 16. Escalation Criteria
Unsupported question class, missing contact, suspected duplicate, contradictory client evidence, unverified client reply, unavailable runtime capability or stale waiting duration.

## 17. Verification
Readback of published Autotask TicketNote and later NotificationHistory recipient event for same ticket. A qualifying reply is a newer note with createdByContactID matching the same-company contact.

## 18. Completion Criteria
Client question step completes only when the verified response has restored the original promoted diagnostic phase and its durable resumption marker. Ticket completion is the responsibility of its underlying playbook after independent repair verification.

## 19. Final Resolution Note
Not applicable at this sub-workflow stage. The originating ticket playbook records findings, diagnostics and final disposition.

## 20. Required Capabilities
- Governed observe: service.ticket.read, service.contact.read, service.ticket.notes.search, service.notification.history.search.
- Governed mutation: service.ticket.client.notification.create.
- Exact queue/worker state transitions are local durable ledger transitions, not unapproved PSA writes.

## 21. Acceptance Test
Controlled synthetic same-company ticket and contact; all 120 catalog mappings; correct footer; disabled-profile, unknown-template, mismatched ticket, cross-company, contact-disabled and recipient-override rejection; exact readback; notification delivery; client reply and restart-safe resume; unrelated ticket note rejection; uncertain send no-retry; existing VulScan/Autotask/worker regressions. Real provider acceptance must be separately authorized and verified in preproduction.

## 22. Section Goal Closure
Complete only when implemented branch, tests, CI, owner review, PM inventory, rollback proof, preproduction and authenticated foundational canaries pass. Update operational documentation and mark unresolved production-readiness conditions explicitly.

## 23. Autonomous Execution Eligibility and Owner Review
Owner-approved message content is not playbook promotion. A separate durable owner promotion is required for client_information_request v1.0.0 with exact policy playbook-autonomy:client_information_request and action capability service.ticket.client.notification.create. Only approved routine question text is eligible. Changes to wording, scope, category or capabilities require renewed review and source control.