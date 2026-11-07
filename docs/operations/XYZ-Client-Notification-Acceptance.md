# XYZ Test Company — governed client-notification live acceptance

**Status:** preproduction source only; **not** authority to merge, deploy or send.
Related issue: #2365. This is a single controlled Autotask customer notification
acceptance, not a demonstration of vulnerability remediation.

## Exact target and frozen pre-read

- Autotask client: XYZ Test Company, company ID **1158**, active.
- Dedicated test ticket: **T20260926.0088**, Autotask ID **141431**,
  title **JASON CLIENT NOTIFICATION TEST - XYZ**, contact ID **30683022**.
  The ticket was completed (status 5) at the latest governed read. Do not
  change status, queue, due date, contact or any other ticket fields.
- Contact: **al.bccomputers@gmail.com**, active, company 1158,
  `receivesEmailNotifications=true`.
- On 2026-11-07 the provider notification-history baseline for ticket 141431
  contained one unrelated historical entry, sent 2026-10-09 to
  **Lindsey.Collins@teamaot.com**, template **Tech Ticket Nag**. Different governed reads reported provider record IDs **150** and **147** for that same timestamp and recipient; two later sequential reads both returned 147. Consequently **do not hardcode a historical ID as durable evidence**. It is not
  proof of a live acceptance send or recipient delivery.
- All values must be re-read immediately before execution. The historical
  baseline is not a substitute for a fresh provider read.

## Exact protected template

Workflow: `xyz_client_notification_acceptance`

Template: `xyz-controlled-client-notification-acceptance-v1`

Title: **JASON TEST ONLY - Client Notification Verification**

Body: **This is an authorized Project Jason notification test for XYZ Test Company.
No service request, security incident, vulnerability, or device change is being
reported. No action is required. This message is intended only to verify that a
governed Autotask client notification reaches the designated test contact.**

The active approved-workflow profile normalizes caller arguments against the
exact source-controlled title/body. The provider acceptance-specific scope gate
rejects any mismatched ticket ID or ticket number, company, contact, recipient,
workflow, or template. No cross-customer or arbitrary-email exception exists.

## Pre-execution security gates

1. Verify exact **approved production release** containing this new source and
   approved template. CI and preproduction success alone are insufficient.
2. Resolve the caller's trusted Microsoft Entra binding to the existing Owner
   principal `person-al` through the *separately approved* identity-recovery
   workflow, or use another already-authenticated authorized Owner principal.
   Do **not** edit the identity SQLite store, broaden the Owner allowlist,
   impersonate a technician, or use a direct Autotask provider call as a bypass.
3. From the same authenticated Jason session, `list_exact_authority_grants`
   must succeed for `person-al`. Only then add/confirm an *exact, temporary*
   `service.ticket.client.notification.create` execute grant scoped to company
   1158 with `approval_required=true`.
4. Verify the concrete action is approved by Jason's governed exact-action
   approval check. A conversation instruction alone must not override those
   checks. No re-use of any Gromelski client communication authorization.
5. Re-read company, contact, ticket and notification history. Bind the
   recipient to the contact record, not an arbitrary supplied address. Refuse
   execution if any read is missing/ambiguous, template differs, or a matching
   acceptance receipt is already present.

## Single provider attempt and independent verification

Make **one** exact governed `service.ticket.client.notification.create`
request with `workflow_id`, `template_id` and `payload.ticketID=141431`.
Record the correlation/approval evidence, a fresh pre-send history snapshot, its highest returned record ID, notification timestamp, ticket, template and recipient. If provider IDs or ordering are inconsistent at the moment of the test, stop and investigate rather than inferring a successful new send.
This provider operation is non-idempotent. On a timeout, crash, unknown outcome
or lost acknowledgement, **never blindly resend**.

Independently query `service.notification.history.search` for company 1158,
ticket 141431. Require a new distinct provider notification-history record
after the baseline, with the exact recipient **al.bccomputers@gmail.com**, correct
ticket/company/time/approved-template message. Verify exactly one such new
record. An Autotask history receipt proves provider-side notification creation,
**not necessarily mailbox delivery**; verify actual receipt in the designated
test mailbox independently before claiming delivered.

Finally read the ticket again, confirm unchanged status 5 and all unrelated
fields, verify no duplicates after the worker/check cycle, then revoke any
temporary test grant with exact readback. Record evidence in issue #2365.

## Stop conditions

Missing Owner identity/authority, approval, released test template, provider
receipt, mailbox receipt, cross-client match, or ambiguous provider outcome is
a **fail-closed WAITING/FAILED acceptance**, not success. Keep existing
production freeze, Owner engineering pause and automatic-promotion hold.
Do not claim GAI/VulScan end-to-end complete based on an unrelated printer
ticket, historical Tech Ticket Nag, or synthetic unit test alone.
