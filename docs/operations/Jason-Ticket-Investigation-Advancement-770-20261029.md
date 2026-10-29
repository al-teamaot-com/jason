# Ticket investigation and governed advancement — #770

## Production problem and purpose

The worker admits zero of many unsupported tickets despite maintaining healthy scan
heartbeats. After October 29 #2142 release it can safely collect evidence and
record durable next steps, but disk-space ticket T20261028.0048 could not
launch an autonomous endpoint PowerShell quick job. This is an authorization
boundary, not a reason to widen standing execution privileges.

## First diagnostic: passive Datto RMM audit

For verified, same-company online devices with a disk-capacity question, use
endpoint.audit.read (already-governed passive endpoint audit) before any
remote execution. Normalize a bounded list of Local Fixed Disk logical drives
with exact identifier, free bytes, total bytes and computed free percentage.
Ignore other fields, drive categories, invalid numeric values and output.
A passive audit is a snapshot; it does not establish current directory usage
or identify files safe for deletion.

The existing Autotask ticket search and exact company identity remain
mandatory for every investigation. An Autotask CI is optional for user-only,
service and infrastructure investigations, and must never be an admission
prerequisite for those cases. For endpoint diagnostics, same-company active
CI, exact Datto UID and hostname verification remain mandatory; a device
mentioned in a ticket title is a search hint, never an association by itself.
Missing essential endpoint identity, unavailable audit and offline devices
are explicit outcomes, not inferred from ticket titles.

Endpoint PowerShell uses a Datto Quick Job that executes a command on a managed
endpoint, even if the script is classified read-only. It is not included in
passive standing-read permissions. Windows licensing and RocketAgent service
diagnostics therefore require a separately governed executable diagnostic or
technician review. No new PowerShell or provider credentials are granted.

## Durable note proposal and owner-promoted publication

Every completed unsupported triage record contains a bounded note_draft in the
existing autonomy_unsupported_triage.evidence_json ledger. It contains only
verified company/device observations, disk audit values, fixed diagnostic state
and next action. It explicitly disclaims remediation or ticket completion.

Drafting never posts to Autotask. To publish an internal note, the distinct
scope unsupported_readonly_triage_note version 1.0.0 must be owner-promoted
with service.ticket.note.create and service.ticket.note.update. This does not
inherit a remediation or GPT Insights scope. After promotion Jason:

1. Confirms the ticket remains eligible, unassigned or Jason-owned and the
   company identity is verified.
2. Reads exact Autotask ticket notes and checks the fixed managed title
   Jason - Governed Read-Only Investigation.
3. Issues a separately owner-promoted note.create or note.update only when
   the proposed body differs, with noteType=3 and publish=2.
4. Reads back the note, requiring the exact managed title and full body.
5. Records the fingerprint only after readback. At most two note publication attempts run per worker scan. Failed writes retry with
   durable 5-60 minute backoff and avoid duplicate notes after restart.

Human-review handoff is a second independent promotion, scope
unsupported_triage_human_review version 1.0.0, allowing service.ticket.update.
Only Jason-owned work in needs_human_review with a verified internal note may
be handed to Help Desk I / Human Review, with provider readback of queue and
status. Already-Help-Desk tickets are not requeued, and notes are not closures.

Neither note publishing nor handoff becomes permitted just because code is
deployed or a release SHA is approved. Owner playbook promotion is separate.

## Acceptance and measurements

- Tests: tenant/CI/UID consistency; disk telemetry allowlist; no endpoint
  execution; promotion-gated notes; idempotent note creation/update; failed
  handoff recovery without duplicates; no writes absent promotion.
- Following controlled release, verify at least two real ticket triage records,
  including one disk-space ticket and one missing-identity case. Require two
  consecutive worker scans and governed source readback.
- Track actual notes and handoffs only when the exact promotion is active and
  provider post-mutation readback proves completion.
- Leave #770 open until real eligible ticket resolutions or escalation are
  verified. Preserve protected production freeze, last-known-good rollback
  and no disruptive endpoint changes without specific approval.


## October 29 contact-first correction — draft PR #2146

Ticket T20261028.0015 / Autotask ID 143272 has a verified company
association (827), contact ID 30683105, and no attached configuration item.
Its title is 202315PC14 -; the actual network-disconnection and Windows
screen/sleep timeout problem is in its description. Live governed reads on
October 29 confirmed the contact belongs to company 827. An exact
same-company Autotask CI search for 202315PC14 returned zero results; a
Datto hostname search also returned no matches. Neither result proves that
a device is nonexistent. Do not infer or bind an endpoint from the title.

The revised generic unsupported triage now:

1. Classifies title **and description**, distinguishes device, user/device,
   user/service, infrastructure, general and security investigations.
2. Verifies ticket company, reads prior notes, and processes contact ID as
   optional identity context. A conflicting contact-company read is rejected;
   an unavailable optional contact read cannot block unrelated safe reads.
3. Runs same-company CI name search for bounded user/device title hints.
   This is evidence collection, not permission to attach or access a device.
4. Avoids mandatory CI/Datto access for user-only and service/infrastructure
   investigations, even when an irrelevant CI is attached.
5. Records needs_diagnostic_evidence rather than needs_device_identity
   solely because a combined user/device ticket has no CI. It cannot assert
   network/power setting resolution until authorized diagnostics verify them.
6. Uses a bumped triage logic version to reassess prior persisted outcomes.

**Contact-read authority:** The production worker's general read policy is
intentionally **not** widened. service.contact.read is allowed only through
the separate governed policy autonomous-ticket-contact-context-read-v1,
requiring exact service identity, JKD-001 authority context, observe mode,
and explicit JASON_TICKET_CONTACT_CONTEXT_PROFILE=approved-v1. The
profile is disabled by default; contact lookup is then recorded as
unavailable while the existing ticket/contact ID and other safe evidence
continue. Contact enumeration/search remains forbidden to this profile.

**Promotion boundary:** Source and regression tests in PR #2146 are
preproduction-only. No permission/profile activation, merge, Production
Manager release, playbook promotion, internal note update, ticket
reassignment, endpoint command, or production deployment is implied.
The existing note 30532713 can only be corrected after the separate
governed note scope is active and its source-version/ownership/readback
preconditions pass. unsupported_triage_human_review remains unpromoted.

**Acceptance still required:** Validate the worker's actual contact-read
profile and real ticket/company/provider evidence, complete triage and
worker regression suites, assess current intake/disposition coverage,
and verify sustained actual eligible-ticket advancement. Do not close
issue #770 merely because this investigation correction passes.
