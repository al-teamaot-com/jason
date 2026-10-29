# Jason - Unsupported Read-Only Triage Note Pilot

playbook:
  id: unsupported_readonly_triage_note
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

Goal: publish a precise, factual internal Autotask investigation note on a tiny controlled pilot, with no customer-visible communication. Success requires exact readback, no duplicates, and no writes outside two listed tickets. Note publication is not ticket resolution.

## 2. Trigger

Use a durable unsupported-triage note_draft on a queue-admissible ticket with exact internal ticket ID 143305 or 143272. Require a matching source-version snapshot; do not trigger writes from historical ledger rows alone.

## 3. Scope and Boundaries

Only internal Autotask notes through the governed Central Orchestrator, with direct_provider_access=false. No remote commands, client messages, endpoint modifications, ticket closure or status changes. Registration does not grant execution authority.

## 4. Initial Identification

Check exact ticket ID, number, positive company, current queue and assignee, note-draft source version and provider status. For referenced endpoints verify exact same-company CI and RMM identity before including details.

## 5. Expected State

One internal note titled Jason - Governed Read-Only Investigation, noteType=3 and publish=2, truthfully stating evidence, outcome, and next action. The ticket stays open and unresolved.

## 6. State Model

Persist states note_drafted, waiting_owner_promotion, prewrite_recheck, write_pending, readback_verified, documentation_complete, or stale_draft, authorization_blocked, identity_blocked, retry_pending, escalated. Source and note fingerprint survive restart.

## 7. Diagnostic Workflow

Read authoritative queue-search ticket snapshot; gather exact Autotask note history with service.ticket.notes.search and conditional same-tenant CI and passive RMM audit. Compare fixed note body; never execute endpoint code or copy unrestricted provider text.

## 8. Decision Gates

Require pilot allowlist, allowed queue/assignment, exact ticket number and source version, verified company, non-transient diagnostic outcome, valid note draft, separate owner-promoted exact scope, and approved note capabilities. Fail closed on any missing gate.

## 9. Remediation

After independent promotion only, create managed internal note if absent. Update a previously proven Jason-owned managed note only if its current content fingerprint matches the last verified fingerprint. Never overwrite an external note with the same title.

## 10. Retry Policy

At most two note publication attempts per scan. Use durable 5-60 minute backoff after any unverified write or readback failure. Re-read note before retry to suppress duplicates. Escalate after bounded failures.

## 11. Periodic Rechecks

Recheck stored note-delivery records during the normal worker cadence. Honor source-version changes and next_due_at, and stop when ticket becomes closed, human-owned, or otherwise inadmissible.

## 12. Aging / Stale Condition

After repeated provider or authority failures, or an unmatched stale note, require technician review instead of unbounded retries.

## 13. Dependency Handling

Missing CI, missing identity, offline device, stale audit, denied governed note permission, or unresolved external dependency must be recorded. No invented company or ticket associations and no unauthorized dependency-ticket creation.

## 14. Documentation Requirements

Include ticket number, verified customer/device identity when known, diagnostic source, any audit freshness caveat, selected finding, expected next action and explicit statement that no remediation or resolution occurred. Do not log secrets.

## 15. Failure Handling

On denied write, unsafe source version, note collision or failed readback, preserve evidence and typed error for bounded recheck. Do not report a posted note until confirmed by Autotask.

## 16. Escalation Criteria

Escalate for identity mismatch, stale source, human-edited note, repeated write failure or actions requiring a separately approved capability. A different playbook controls human-review handoff.

## 17. Verification

After write, read service.ticket.notes.search for the exact ticket and require exact managed title and full body. Persist SHA fingerprint only after readback.

## 18. Completion Criteria

Completion of documentation only: accurate internal note proven, durable fingerprint, no duplicate, no unauthorized updates. Do not mark ticket complete.

## 19. Final Resolution Note

Not applicable to incident resolution. This produces an investigation note, not a final customer-facing resolution.

## 20. Required Capabilities

Read: governed queue search, exact ticket notes, optional CI/device/passive audit. Write: service.ticket.note.create and service.ticket.note.update only under scope unsupported_readonly_triage_note version 1.0.0.

## 21. Acceptance Test

Pilot tickets 143305 (Space Issue, passive disk evidence) and 143272 (missing CI). Test two owner-promoted note posts, source/tenant checks, owner collision, idempotency, restart, provider denial and nonpilot rejection. Include 143073,143270,143314 as no-write or evidence-only controls.

## 22. Section Goal Closure

Only close this Section Goal after exact-SHA controlled release, independent note-scope promotion, two real Autotask note readbacks, no unexpected customer activity, zero unrelated writes, audit evidence and issue #770/Grafana update.
