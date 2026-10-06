# Jason Playbook: Jason Activity - Living Internal Work Log

## 1. Section Goal
Maintain a concise, chronological, technician-readable internal activity log in each ticket Jason meaningfully works, while preserving full audit history separately.

## 2. Trigger
A meaningful Jason operational event occurs on an exact ticket: diagnostic attempt, device-access wait, resume, remediation attempt/result, dependency/approval transition, verification, escalation, or other material state change.

## 3. Scope and Boundaries
Internal Autotask notes only. Never edit technician/client/workflow notes. Never use activity logging as authority for the underlying operational action. Preserve Central Orchestrator, exact grants, provider/client isolation, approval rules, and `direct_provider_access=false`.

## 4. Initial Identification
Require exact ticket identity. For update, require one exact `Jason Activity` note created directly by the configured Jason autonomy resource.

## 5. Expected State
The ticket contains a living `Jason Activity` note whose entries are chronological and concise. Unchanged polling does not add noise.

## 6. State Model
`no_log -> base_log_created -> current -> material_event -> appended -> current`; `rollover` creates the next numbered Jason Activity note when bounded size is reached. Full runtime transitions remain in Jason SQLite activity history.

## 7. Diagnostic Workflow
No independent diagnostics. Consume already-authorized operational results and render only the facts needed for ticket history.

## 8. Decision Gates
Exact ticket; material event; exact promotion; internal note only; Jason creator identity; current-body hash match; append preserves full previous body as prefix.

## 9. Remediation
Not applicable. This scope documents work; it does not authorize the work being documented.

## 10. Retry Policy
One provider mutation attempt per governed execution. Stale hash or ownership failure stops with no retrying PATCH.

## 11. Periodic Rechecks
Unchanged rechecks stay in persisted runtime state only. Append when state/result materially changes or a real retry/action occurs.

## 12. Aging / Stale Condition
Not applicable. Historical activity remains on the ticket.

## 13. Dependency Handling
Log meaningful dependency/approval transitions without exposing secrets.

## 14. Documentation Requirements
Title `Jason Activity`; append timestamp, event, result/interpretation, and next state. Update is semantically append-only. If the living note approaches the source-controlled bounded size threshold, create `Jason Activity 2`, then 3, etc. Never erase prior entries.

## 15. Failure Handling
Ambiguous note, non-Jason owner, external visibility, stale hash, failed provider update, or failed readback: fail closed and retain durable local activity history.

## 16. Escalation Criteria
Logging failure is a Jason support condition; it does not authorize repeating the operational action being documented.

## 17. Verification
TicketNotes readback must verify exact note ID/title/body/internal visibility and Jason creator attribution.

## 18. Completion Criteria
Event is present in a verified Jason Activity note or no write is required because it is an unchanged duplicate.

## 19. Final Resolution Note
Not applicable; the activity log is the chronological work record.

## 20. Required Capabilities
`service.ticket.notes.search`, `service.ticket.note.create`, `service.ticket.note.update`, persisted operational activity history.

## 21. Acceptance Test
Create base log; append offline device check; suppress unchanged duplicate; append online/resume transition; reject technician-owned/stale-hash rewrites with zero PATCH; prove rollover remains Jason-owned/internal.

## 22. Section Goal Closure
Close after provider contract tests, runtime tests, exact owner promotion, production deployment, and controlled ticket verification.

## 23. Autonomous Execution Eligibility and Owner Review
Autonomy is limited to `jason_activity_log@0.1.0`, policy `playbook-autonomy:jason_activity_log`, and internal note create/update. It grants no authority for the documented operational action itself.
