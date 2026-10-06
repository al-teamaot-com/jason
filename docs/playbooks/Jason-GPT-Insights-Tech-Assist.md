# Jason GPT Insights - Help Desk Tech Assist

**Version:** 0.2.0
**Status:** Production scope; exact durable owner promotion required
**Mode:** Advisory, internal-note only

## 1. Section Goal
**Goal:** Give AOT technicians evidence-grounded assistance on every eligible **Help Desk I / New** ticket without claiming, moving, remediating, or communicating externally from this scope.

**Success means:** one living internal `GPT Insights` note exists when useful evidence is available; material evidence changes refresh that same Jason-owned note; recurring-source tickets never enter the scope; no client notification or unrelated ticket mutation occurs.

## 2. Trigger
Autotask queue **Help Desk I**, PSA status exactly **New**, ticket source not **Recurring**. The augmentation is independent of whether a separate promoted remediation playbook also matches.

## 3. Scope and Boundaries
In scope: ticket evidence, authoritative provider reads, bounded same-client correlation, read-only endpoint diagnostics, internal GPT Insights note create/update. Out of scope: Help Desk II, non-New tickets, recurring-source tickets, client communication, ticket ownership/status changes, remediation, disruptive actions, and editing any note Jason cannot prove it created.

## 4. Initial Identification
Identify the exact ticket, company, and associated configuration/device when one is authoritative. Do not guess a device. GPT Insights itself does not run the global work-start lifecycle because it is an augmentation, not ticket ownership.

## 5. Expected State
A technician can open the ticket and see one current, concise, evidence-grounded `GPT Insights` internal note. Unknown facts are labeled unknown rather than invented.

## 6. State Model
`eligible -> evidence_collected -> base_note_created | living_note_current -> material_change -> living_note_updated`. Persist the material evidence fingerprint. Unchanged evidence performs no write.

## 7. Diagnostic Workflow
Collect only evidence that reduces technician effort: associated device, online/offline state, OS, active wired/Wi-Fi evidence for network complaints, bounded related-ticket evidence, and relevant provider state. For unknown requests, say classification is uncertain.

## 8. Decision Gates
Require Help Desk I, status New, non-recurring source, exact durable promotion, internal-note capability, and authoritative evidence. Existing `GPT Insights` updates additionally require exact note ID, internal visibility, Jason autonomy creator identity, unchanged title, and current-description SHA-256 match.

## 9. Remediation
Not applicable. GPT Insights is advisory only.

## 10. Retry Policy
Provider writes are maximum one attempt per governed execution. Failed ownership/concurrency/readback gates do not retry as a write.

## 11. Periodic Rechecks
The normal autonomy scan may reassess while the ticket remains eligible. Only a material evidence fingerprint change can update the living note.

## 12. Aging / Stale Condition
When the ticket leaves `New` or Help Desk I, GPT Insights stops updating it. Historical note content remains intact.

## 13. Dependency Handling
Missing/ambiguous device association is documented as a limitation. Jason does not fabricate or borrow client data.

## 14. Documentation Requirements
Create at most one note titled exactly `GPT Insights`. On material change, replace only the body of that same Jason-owned note through governed `service.ticket.note.update`. The provider path must pre-read ownership and internal visibility, bind the expected current body hash, PATCH once, and read back the final state. Jason's audit trail preserves revision history.

## 15. Failure Handling
Any ambiguous note identity, non-Jason creator, customer-visible note, stale body hash, read failure, provider rejection, or readback mismatch fails closed with zero unverified follow-up writes.

## 16. Escalation Criteria
GPT Insights itself does not escalate tickets. Failures are operational evidence for Jason support/repair; ticket handling continues under its normal playbook or technician workflow.

## 17. Verification
Successful creation/update requires authoritative TicketNotes readback matching note ID, title, description, `noteType=3`, `publish=2`, and Jason creator attribution.

## 18. Completion Criteria
The augmentation cycle is complete when the current material evidence fingerprint is persisted and the living note is verified or no write is needed.

## 19. Final Resolution Note
Not applicable; this scope does not own incident resolution.

## 20. Required Capabilities
- `service.ticket.notes.search`
- relevant governed evidence reads
- `service.ticket.note.create`
- `service.ticket.note.update`
- persisted augmentation state

## 21. Acceptance Test
Prove: Help Desk I/New gets one note; matching remediation does not prevent augmentation; non-New and recurring tickets do not get it; material evidence updates the same note; unchanged evidence writes nothing; technician-owned/stale-hash/customer-visible targets produce zero PATCH calls; create/update readback verifies internal visibility and Jason ownership.

## 22. Section Goal Closure
Close only after source tests, governed provider tests, exact v0.2 owner promotion, production deployment, and controlled Help Desk I/New verification succeed.

## 23. Autonomous Execution Eligibility and Owner Review
Autonomy is limited to `gpt_insights_tech_assist@0.2.0`, policy `playbook-autonomy:gpt_insights_tech_assist`, and capabilities `service.ticket.note.create` + `service.ticket.note.update`. No other mutation is authorized.
