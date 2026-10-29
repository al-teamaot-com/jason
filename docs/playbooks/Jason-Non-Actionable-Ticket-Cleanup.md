# Jason Playbook: Non-Actionable Ticket Cleanup

```yaml
playbook:
  id: nonactionable_ticket_cleanup
  name: Non-Actionable Ticket Cleanup
  version: 1.0.0
  owner: AOT Service Management
  target_type: ticket
  trigger:
    provider: Autotask
    match: New Email-source ticket with exact high-confidence administrative classification
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 1
  recheck:
    enabled: true
    cadence: next ordinary ticket-worker scan
    stale_after: 1 day
  verification:
    authoritative_source: Autotask ticket/notes/company and status readback
    success_condition: Exact site-bound non-actionable ticket completed with internal audit note
  completion:
    terminal_disposition: Complete
  autonomy:
    allowed_branches: [verified_vendor_promotion, out_of_office_auto_reply]
    approval_bound_branches: [new_sender_class, new_message_class, unsubscribe]
    disruptive_branches: []
```

**Activation:** This source entry nominates no unattended authority. The exact
`nonactionable_ticket_cleanup@1.0.0` scope must be independently reviewed,
accepted, and granted durable Owner promotion. Production requires its own
exact-SHA release authorization, successful health checks, and protected rollback.

## 1. Section Goal

**Goal:** Remove genuinely non-actionable incoming-email tickets from help
desk queues without creating new playbooks for each sender or requiring a device
association. **Success means** deterministic high-confidence classification,
verified company **and Autotask site/location**, no user/client/technician
activity, one audited administrative closure, and verified PSA completion.
Ambiguous, security, backup, financial, transactional, or actual support
messages remain available for human action.

## 2. Trigger

Autotask Email-source (`source=4`), **New** ticket in the governed discovery
queues, without an applicable promoted technical playbook. Initial version
supports only exact sender `Network Solutions <info@eml.networksolutions.com>`
with percentage-discount offer subject, and explicit `Automatic reply:`
messages with out-of-office/vacation language. The classifier is deterministic
and conservative. A subject or body containing an Autotask ticket reference
excludes cleanup. Transactional or incident-related subjects exclude cleanup.

## 3. Scope and Boundaries

**In:** Autotask identity, company/site, note history, internal resolution note,
ticket status/queue; no endpoint/user must exist for administrative email.

**Out:** genuine support requests, monitoring alerts, Duo/VulScan problems,
EDR/security evidence, backups/reports, payment and billing confirmations,
delivery failure/NDR evidence, unsubscribe links, arbitrary sender domains,
ticket deletion, user email, and endpoint/component execution. No device/service
changes, direct provider access, or disturbance of other tickets. No external
emails are sent intentionally; native Autotask workflow notifications must be
reviewed during acceptance. No attempts to suppress or bypass native workflows.

## 4. Initial Identification

Read the exact Autotask ticket fresh and match its ID, number, source,
classification, company, location, and open status to the queue candidate.
Verify a positive companyID and companyLocationID; require an active company
with matching ID from `service.company.read`. Check complete ticket note
history; reject substantive technician/client notes and unknown note types.
A site is **required**; a device and user are **optional** and cannot be
fabricated. An existing configuration item excludes this administrative
cleanup flow; the regular global device association rule still applies to
technical cases. Before ticket-specific work, claim queue **Jason** and status
**In Progress** with verified readback. Do not assign billable Remote Support
work type to administrative junk email.

## 5. Expected State

The item is administrative mail only, with an exact active customer/site link,
no unresolved technical or human request, and no manually contributed work.
It should leave an internal auditable resolution and PSA terminal `Complete`.

## 6. State Model

`discovered -> classified -> identity_verified -> claim -> cleanup_finish
-> complete`. Missing identity, human activity, unexpected provider status,
or denied authority fails closed into a durable blocked/human-reviewed state.
The existing operational-work store persists the work/phase, original company,
ticket, site (as the site marker rather than a false hostname), and completion.
Existing runtime slots, scans, audits, deduplication, and restart recovery apply.
A terminal `complete` ticket is not reprocessed.

## 7. Diagnostic Workflow

1. **Classification:** Read Autotask title, bounded description and source;
   compare exact sender and message rules. Unsupported/ambiguous -> ordinary
   ticket process and no cleanup action.
2. **Identity:** Read ticket, active company, company-location ID; no guesses,
   cross-client inheritance or use of unmatched RMM sites.
3. **Human activity:** Read notes; system-generated workflow entries only.
   Client/technician entries or unrecognized notes exclude cleanup.
4. **Readback:** Immediately prior to completion, repeat authoritative ticket,
   company/site and note-history checks. Compare source ticket number, company
   and site to persisted work and verify Jason queue/In Progress status.

## 8. Decision Gates

Require all: high-confidence deterministic trigger; Email source; New status;
valid same-company Autotask site/location; active company; no CI; original
ticket number/ID and source unchanged; system-only notes; exact playbook/version
Owner promotion for note create + ticket update; spare bounded active slot;
fresh pre-write re-read; no existing action in progress; correct requester
authority. A failure means **no automatic completion**.

## 9. Remediation

One governed Autotask administrative sequence:
1. Update queue `Jason` and status `In Progress`; verify queue/status readback.
2. Create a **publish=2** internal note with classification, company/site,
   evidence, changes, and required next action. Deduplicate by durable fingerprint.
3. Update status `Complete`; require provider verified-fields readback.
No deletion or unsubscribe in v1. A follow-up verified unsubscribe branch
would need independent safety review and separate Owner scope.

## 10. Retry Policy

At most one new claim attempt per ticket evaluation; no repeat blindly.
A provider failure after claim persists blocked state for review/recovery.
A previously created internal note is not recreated when its matching
fingerprint is present. No repeated endpoint jobs because none are used.

## 11. Periodic Rechecks

Normal one-minute ticket-worker reconciliation handles new tickets; an
already-claimed interrupted job resumes its persisted phase. Do not resubmit
completed tickets or scheduled cleanup work. Unchanged unsupported candidates
do not create repeated notes.

## 12. Aging / Stale Condition

A claimed ticket not able to complete after one day needs technician review.
Tickets that lose source identity, site, promotion, or queue/status consistency
must not silently move to Complete.

## 13. Dependency Handling

If company or location cannot be verified, leave the original ticket intact
for human classification. Do not create arbitrary new sites or false CI/device
associations. If approval or notes capability is unavailable, keep the exact
blocked state and escalate through existing shared runtime. No new provider
credentials, APIs, or user privileges should be requested for v1.

## 14. Documentation Requirements

Internal note title: `Jason - Non-Actionable Ticket Cleanup - Resolution`.
Use a technician-scannable summary: STATUS, NEXT STEP, KEY EVIDENCE,
WHAT JASON DID, CHANGES MADE, JASON STATE. Include Autotask ticket,
companyID, companyLocationID, classification, no unsubscribe action, and
no endpoint remediation. Do not embed email tracking links, secrets, or
unnecessary contact details.

## 15. Failure Handling

Missing site, company mismatch, status drift, new human reply, unexpected
Autotask note, denied write, invalid provider readback, or unpromoted scope
fails closed. Preserve an audit reason without claiming that the ticket was
resolved. Preserve unrelated tickets and their active work.

## 16. Escalation Criteria

Escalate for client/technician activity, sender ambiguity, technical
alerts, financial/transactional notices, missing company/site, repeated
provider failures, or an interrupted administrative claim. Do not
auto-close an ambiguous email just to reduce queue counts.

## 17. Verification

The authoritative Autotask mutation response must confirm `status` was
written and read back; the internal note is created through the same
governed scope. The runtime completion record reflects PSA verification
and sends the existing completion notification if configured. Provider
write acceptance alone is not closure.

## 18. Completion Criteria

Exact ticket, company/site, source and classification verified; no human
activity; internal note persisted; Autotask status `Complete` verified;
durable terminal state recorded; no external unsubscribe/endpoint changes.

## 19. Final Resolution Note

Document category and why no technical or customer action was necessary,
verified company/site, the time and status disposition, the fact no client
system was modified, and that no unsubscribe link was followed.

## 20. Required Capabilities

Governed `service.ticket.read`, `service.company.read`,
`service.ticket.notes.search`, `service.ticket.note.create`,
`service.ticket.update`; existing queue discovery, durable owner
promotion, note fingerprinting, workflow status and lifecycle notifications.
No DRMM read/write or user account capability is needed.

## 21. Acceptance Test

Preproduction tests must show: known marketing and out-of-office examples
classify correctly; backup, security, payment and client request examples
do not; missing site/company or active CI do not trigger changes; human
notes block; unpromoted scope does zero writes; promoted scope claims, notes,
completes with exact readback; restart and unchanged-scan duplicate
suppression; verification failure leaves the ticket open for review;
no customer communication triggered by our note in the real test policy.
The final controlled production test needs a dedicated non-client-impact
ticket and exact Owner authorization; no real cleanup without it.

## 22. Section Goal Closure

Record reviewed source SHA/PR, CI tests, preproduction outcome, Owner
promotion ID, two or more live controlled ticket receipts, any Autotask
workflow side effects, Grafana/Project Jason status, and outstanding cases.
Do not mark operationally complete based on unit tests or a merged PR.

## 23. Autonomous Execution Eligibility and Owner Review

The proposed autonomous branch is bounded to
`nonactionable_ticket_cleanup@1.0.0` with exactly
`service.ticket.note.create` and `service.ticket.update`. No privileged
provider access, scripting, unsubscribe, ticket deletion, endpoint service
change, customer contact, or broadened sender classification is allowed.
This scope must receive its own immutable Owner approval/promotion bound to
the playbook version, policy, allowed capability set and source fingerprint.
An unpromoted code path performs **no housekeeping writes**.
