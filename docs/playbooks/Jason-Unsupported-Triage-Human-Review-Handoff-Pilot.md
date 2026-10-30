# Jason - Unsupported Triage Human Review Handoff Pilot

playbook:
  id: unsupported_triage_human_review
  version: 1.0.0
  owner: AOT Service Manager
  target_type: ticket
  trigger:
    provider: Autotask
    exact_ticket_ids: [143305, 143272]
  ownership:
    while_open: conditional
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 0
  recheck:
    enabled: true
    cadence: 60 seconds
    stale_after: 1 day
  verification:
    authoritative_source: Autotask
    success_condition: exact governed post-action readback
  completion:
    terminal_disposition: documented or escalated, not closed
  autonomy:
    allowed_branches: [read_only_evidence]
    approval_bound_branches: [exactly_promoted_ticket_write]
    disruptive_branches: []

**Registration is not approval.** Owner promotion is separate from the
approved production deployment SHA. Source-scoped pilot IDs prevent all
other Autotask ticket mutations.

## 1. Section Goal

Goal: move an eligible Jason-owned unsupported case needing human action to Help Desk I with status Human Review, following a verified internal note. This is escalation, not incident resolution.

## 2. Trigger

Trigger only for pilot ticket IDs 143305 or 143272 with source queue Jason, owned_by_jason=true, persisted state needing technician assistance (needs_human_review, needs_device_identity, needs_execution_authority, needs_security_review, needs_playbook_review, needs_diagnostic_evidence, or read_only_assessed), and verified note. The last two outcomes indicate insufficient evidence or a completed read-only assessment without verified resolution; neither permits autonomous closure. No forced state changes to manufacture pilot eligibility.

## 3. Scope and Boundaries

Autotask ticket queue/status only, via Central Orchestrator and direct_provider_access=false. No device changes, client messages, priority/due date edits, ticket closure or reassignment of technician-owned cases.

## 4. Initial Identification

Revalidate exact ticket number/ID/company, current queue Jason, owner, source version, diagnostic state and managed note readback before any update.

## 5. Expected State

Unresolved ticket remains open, in Help Desk I queue ID 29682833, with Human Review status ID 37 and exact diagnostic evidence.

## 6. State Model

States identified, needs_device_identity or needs_human_review or other review-required outcome, note_verified, waiting_handoff_promotion, update_pending, readback_verified, escalated or blocked, retry_pending. Persist to survive worker restarts.

## 7. Diagnostic Workflow

Read governed queue snapshot, exact internal notes, prior diagnostic evidence and post-update provider verification; a note or queued action alone does not prove a handoff.

## 8. Decision Gates

Require exact pilot ID, Jason queue and ownership, one of seven explicit unresolved technician-review outcomes, verified internal investigation note, separately owner-promoted scope unsupported_triage_human_review 1.0.0, unchanged source and valid target queue/status. Hand off only if current ticket still needs human follow-up; never treat read_only_assessed as incident resolution.

## 9. Remediation

Submit one governed service.ticket.update for exact ID with queue Help Desk I and status Human Review; require jasonVerification.readbackVerified true for queueID and status. Never modify any other fields.

## 10. Retry Policy

Bound to one handoff per eligible ticket state. If provider readback missing, re-read current ticket and retry with bounded backoff; no repeated unsafe moves.

## 11. Periodic Rechecks

Recheck only while eligible and state still requires handoff. Stop if the ticket moved to human queue, changed owner, closed or became inadmissible.

## 12. Aging / Stale Condition

Age unresolved handoffs to human oversight after limited retries. Never loop or retry indefinitely.

## 13. Dependency Handling

Missing note, missing promotion, conflicting owner, company mismatch or unavailable Autotask read is a dependency. Do not borrow a remediation playbook's permission.

## 14. Documentation Requirements

Preserve note fingerprint, original queue/status, exact handoff reason, action correlation and post-update field verification. Do not print secrets.

## 15. Failure Handling

Any mismatch, denied action or unverified queue/status is a failure and must not be treated as completion. Preserve retry state and escalate safely.

## 16. Escalation Criteria

Technician review if there is incompatible ticket status, not-Jason ownership, repeated provider failure or disruptive action required.

## 17. Verification

Readback must prove exact ticket now belongs to Help Desk I queue/status Human Review. Verification of only one field is insufficient.

## 18. Completion Criteria

Complete only the handoff; retain ticket open for technician response and authoritative resolution.

## 19. Final Resolution Note

Not applicable. Human Review is not ticket closure or verified issue resolution.

## 20. Required Capabilities

Governed ticket search and notes search; exact separately promoted service.ticket.update for unsupported_triage_human_review v1.0.0. No endpoint permissions.

## 21. Acceptance Test

Test a controlled simulated Jason-owned needs_human_review ticket, evidence-only read_only_assessed and needs_diagnostic_evidence cases, unpromoted denial, partial readback and retry, duplicate suppression, and human-owned exclusions. Live handoff only when a permitted pilot ticket naturally qualifies and the exact Owner promotion is present.

## 22. Section Goal Closure

Close only upon controlled release, independent handoff promotion, real exact provider readback (or explicit deferred pilot because no eligible ticket), and issue #770/Grafana evidence. Leave broader resolution goal open.
