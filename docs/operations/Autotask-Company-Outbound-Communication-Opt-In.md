# Autotask Company outbound communication opt-in (preproduction)

## Section Goal
Use a single Autotask **Company** UDF as an additional fail-closed gate on the
existing TODO-COMM-001 approved external-communication framework, never as
standing permission to invent wording or contact an arbitrary recipient.

**Field:** `enable_jason_outbound_comm`
**Entity:** `UserDefinedFieldDefinitions`, `udfType=1` (Account/Company).
**Data:** `dataType=3` (List); approved values `True` and `False`.
**Default:** `False` (or absent/null interpreted as disabled).
**Visibility:** no client-portal exposure. No client automatically opted in.

These numeric picklists are grounded in live governed Autotask
`service.entity.fields.describe` reads from 2026-11-08, not assumptions.

## Existing source to reuse
- TODO-COMM-001 / GitHub #947 is the canonical communication framework.
- `config/client_communications/approved.json` has the existing approved fixed
  VulScan message; obsolete XYZ test text is **not** a send authorization.
- `config/client_communications/information_requests_round1.json` includes
  120 owner-approved canned questions with 15 categories and eight questions
  each; autonomous sending is **disabled** for all 120 entries.
- `implementation/runtime_service/src/jason_runtime/approved_client_messages.py`
  already reconstructs approved wording, validates the workflow/template pair,
  and permits only a bounded ticket reference in the supported client-question
  path.
- `docs/operations/Approved-Workflow-Client-Communication.md` defines
  the existing recipient, source, approval, and receipt controls.

## Global communication decision
1. Identify exact Autotask ticket, its company, ticket contact, and approved
   workflow/template, using governed source reads.
2. Verify that the Company UDF is **exactly present once** and explicitly
   `True`; absence/null/duplicate/invalid/mismatched company is **OFF**.
3. Independently require the approved source-controlled template,
   workflow/playbook authority, native ticket-contact permissions, and
   information-release rules. This UDF never substitutes for an approval.
4. For a permitted message, use a client-facing Autotask ticket note with the
   existing server-controlled visibility; do not write arbitrary prose.
5. Persist send fingerprint, create once, verify ticket-note readback and any
   required matching `NotificationHistory` receipt. No blind retries.
6. For a reply, match the real ticket/contact and correlate to the awaited
   question before resuming the worker. Human-review ambiguous answers.

## Time entry boundary
A customer-visible time entry is not interchangeable with a customer-facing
ticket note. Current Autotask TimeEntries metadata includes `summaryNotes`,
`showOnInvoice` and billable-time attributes, but no general client-notification
send contract. Do not create artificial time or billing solely to deliver a
message. If later approved, a separate governed time-entry class must verify
actual work, native visibility and billing behavior first.

## Activation and release
The new gate is coded in `client_outbound_opt_in.py` and called from the
existing client-notification connector. It is *inactive* until the exact
`JASON_CLIENT_OUTBOUND_OPT_IN_PROFILE=autotask-company-udf-v1` profile is
set in a **separately authorized governed release** after the field exists.
An unknown profile fails closed.

The UDF definition/create and list-choice/create operations have now been
implemented **as dormant, source-only governed capabilities**:
`service.company.udf.definition.create` and
`service.company.udf.choice.create`. They use the existing native
requester-impersonated Autotask write credential and exact execution plans;
neither is active or exposed in live Jason MCP. The API integration credential
already has native `userAccessForCreate=All` for the relevant entity metadata.
Source construction and tests are not evidence of field creation or operational
send authority. Existing Company records have
`userAccessForUpdate=None` for the observed API identity, so enabling individual
clients is a separate provider-permission prerequisite.

Production freeze, engineering Owner pause and automatic-promotion hold remain
unchanged. No customer message, time entry, UDF change or customer opt-in occurs
from merging the preproduction source.

## Acceptance
- Provider-backed definition creation and readback proves one exact Company UDF
  with only active True/False choices and fail-closed default.
- Authorized administrator can set a client value, with post-write readback.
- Missing/False/mismatched/duplicate Company UDF fails before contact read/send.
- True does not bypass the approved source template, contact, identity or
  playbook authorization.
- One approved note sends once; matching notification receipt is verified where
  required; duplicates/unknown delivery remain pending.
- Rollback and exact source SHA pass separate production-release gates.
