# Jason Ticket Advancement — Five-Ticket Controlled Acceptance Plan

Date: 2026-10-29. Issue: #770. Baseline production revision:
7d27807b590f92b8242576ee61c68dda1abf5615.

## Section Goal

Demonstrate that Jason advances tickets through evidence, internal
documentation and safe handoff rather than merely counting scans. No ticket
may be marked resolved without an approved remediation workflow and
authoritative healthy-state readback.

## Five real-ticket acceptance targets

| ID | Ticket | Current verified facts | Intended outcome |
|---|---|---|---|
| 143305 | T20261028.0048 — Space Issue | Company 261, CI 75, RBH-50445, passive Datto audit shows C: 24.8% free | Exact pilot note after separate note promotion; one note and verified readback; no cleanup or closure |
| 143272 | T20261028.0015 — 202315PC14 | Company 827, no Autotask CI, currently in Jason queue | Exact pilot identity-gap note after separate note promotion; eligible for distinct Human Review handoff approval if still Jason-owned |
| 143073 | T20261023.0043 | Verified company, no exact CI; prior generic triage evidence | Evidence-only negative control: no note, no queue update |
| 143270 | T20261028.0013 — RocketAgent stopped | Ticket company ID 0, CI 1125; company mismatch not reconciled | Identity-blocked negative control: do not infer company and do not write |
| 143314 | T20261029.0003 — Windows license status | Company 827, CI 1626, assigned to Help Desk technician, not in Jason queue | Technician-ownership negative control: no note or handoff; approved separate endpoint diagnostics if later requested |

## Authority gates

- The production release, playbook registration, durable playbook approval
  and per-ticket pilot allowlist are independent gates.
- The controlled pilot permit list is exactly Autotask resource IDs 143305
  and 143272; max 2 new note attempts per normal worker scan.
- The note-scope approval grants only internal note.create and note.update
  for exact production-registered playbook
  unsupported_readonly_triage_note v1.0.0.
- Handoff-scope approval is separate, allowing only service.ticket.update
  for unsupported_triage_human_review v1.0.0, after a verified note.
- If ticket status, queue, owner, source version, company or note ownership
  changes, do not write. Never run endpoint commands, reboot, clean up files,
  send client-facing messages or close a ticket under this pilot.

## Procedure and evidence

1. Record pre-read of the two controlled tickets, current queue, status,
   assigned technician, source version, existing exact managed notes,
   and permitted Autotask company association.
2. Deploy a separately exact-owner-approved release through Production
   Manager with verified rollback, full scope, independent CCC and freeze
   restoration. The release alone does not activate write scopes.
3. Receive separate explicit owner promotion of only the note scope.
   Observe a bounded worker cycle and verify the two exact managed notes
   through Autotask notes.search. Check body and note type, duplicates and
   client-visible activity. Verify no writes on the three negative controls.
4. Only after (3) passes, separately promote the handoff scope, and only
   if ticket 143272 still qualifies as Jason-owned and has a verified
   needs_device_identity or other review-required state. Confirm Help Desk I
   queue ID 29682833, status Human Review ID 37 by provider readback.
5. Verify two consecutive worker scans, note-delivery and handoff ledgers,
   no duplicate writes after restart and no unauthorized changes.
6. If any condition fails, stop the pilot, revoke the relevant promotion
   through the governed owner workflow and preserve signed evidence. Use
   Production Manager rollback when a release or foundational check fails.

## Exit criteria and remaining gap

Initial pilot success: two exact verified internal notes, zero unrelated
writes, one genuine handoff if naturally eligible, and safe exclusion of
three controls. This is not five resolved tickets. Full #770 closure still
requires enough approved diagnostic and remediation playbooks to demonstrate
actual verified ticket resolution and appropriate escalation across five
eligible reactive tickets.

Maintain original production freeze, independent incident hold, durable
owner audit and Project Jason Grafana evidence throughout.

