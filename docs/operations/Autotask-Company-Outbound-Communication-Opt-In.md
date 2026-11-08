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
- `config/client_communications/approved.json` has the existing fixed
  VulScan message and a bounded XYZ Test Company acceptance message.
  The Owner approved XYZ as the test **client and Gmail recipient** on
  2026-11-08, limited to existing ticket `T20260926.0088` and the
  exact contact `al.bccomputers@gmail.com`. This test approval does
  **not** replace Company UDF enablement, workflow/template approval,
  production release approval or notification readback.
- `config/client_communications/information_requests_round1.json` includes
  120 owner-approved canned questions with 15 categories and eight questions
  each; autonomous sending is **disabled** for all 120 entries.
- `implementation/runtime_service/src/jason_runtime/approved_client_messages.py`
  already reconstructs approved wording, validates the workflow/template pair,
  and permits only a bounded ticket reference in the supported client-question
  path.
- `docs/operations/Approved-Workflow-Client-Communication.md` defines
  the existing recipient, source, approval, and receipt controls.

## Scope: not question-only
The existing 120-question list is only the client-clarification subset.
This Company UDF gate applies **equally** to approved client-facing ticket-note
status updates, work-start/progress/completion notices, scheduling,
resolution confirmations, authorized low-risk instructions, approval requests,
and restricted security or business communications. Each category keeps its
own content, approval and evidence policy. See
`docs/operations/AOT-External-Client-Message-Classes.md`.
No new message is implicitly approved by the Company opt-in.

## One shared, ticket-bound send process
This UDF is checked by **one** TODO-COMM-001 outbound communication process,
regardless of whether the intent came from ticket resolution, onboarding,
documentation upkeep or security workflows. No process sends directly outside
Autotask. Every client-facing notification requires a legitimate, existing
and verified Autotask ticket. If there is no appropriate ticket, a separate
governed ticket-create workflow must create/read back an appropriate ticket
first; otherwise communication remains blocked. A ticket note and an
Autotask-originated email about that note are considered one ticket-bound send.
TimeEntries are only for verified work on the same ticket.

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

## Owner's exact XYZ Test Company opt-in target

**Authorized target:** Autotask Company `1158`, XYZ Test Company.
**Required setting:** Company UDF `enable_jason_outbound_comm=True`.
**Approved acceptance ticket:** `T20260926.0088` (ticket ID `141431`).
**Verified recipient:** contact `30683022`,
`al.bccomputers@gmail.com`, with email notifications enabled.
The Owner approved the controlled XYZ recipient and specifically directed
enabling the Company UDF for XYZ on 2026-11-08.

Do not mistakenly enable all companies or treat the fact that the Owner
approved the test recipient as proof that the Company UDF is already present.
The live read on 2026-11-08 showed **93 UDF definitions and NO target field**;
XYZ's authoritative Company read showed **25 other UDFs and NO target value**.
Do not fabricate a successful write or skip the normal release/approval gates.

An additional source-only, dormant, reusable governed action now supports the
exact Company `userDefinedFields` update:
`service.company.outbound.optin.update`, with
`JASON_AUTOTASK_COMPANY_OUTBOUND_OPTIN_PROFILE=owner-company-outbound-optin-v1`
as a separately enabled profile after deployment. It accepts only
`{company_id, enabled}` with strict Boolean, then constructs the **only**
native PATCH fields: `id`, and
`userDefinedFields=[{"name":"enable_jason_outbound_comm","value":"True"|"False"}]`.
The exact Company record and UDF definition are read before preparation and
again immediately before write; native requester permissions and immutable
exact-action plans are mandatory. One PATCH is followed by provider Company
readback proving the target value and unchanged unrelated UDFs.
The production action remains unexposed until a governed release activates it.

The Companies entity is API-update-capable, but the **current live read
identity** reports `userAccessForUpdate=None`. This is **not** conclusive
proof of the final impersonated technician's rights: the governed write action
queries native permission under the authenticated technician's exact
`ImpersonationResourceId`; if that is None the write must stop before PATCH.
The Owner's instruction does not bypass native provider permission.

**Exact required sequence after authorized release:**
1. Read UDF definition list again, create one Company List definition only
   if still absent, add active `False` and `True` choices, and verify by GET.
2. Verify Company `1158` and exact approved contact and ticket readback.
3. Invoke the governed Company consent update for
   `{"company_id":1158,"enabled":true}`, with provider-native update access
   and bound exact-action approval, then re-read Company `1158`.
4. Assert the Company UDF is uniquely `True`; assert all other clients
   remain OFF (missing is OFF), and no unrelated fields changed.
5. Only after independent class/template authority and approved release may
   the single outbound process send an exact XYZ test TicketNote, verify
   the expected recipient and NotificationHistory, and prevent duplicates.

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


## Engineering integration coordination (draft PR #2375)

This source-only feature composes new consent/schema capabilities into the
existing Jason runtime, but does not replace its authority engine,
communication service, release manager, or any other workflow's provider
adapter.

- PR #2373 owns the distinct technician client-notification authority
  profile. Its own capability gate and our Company UDF opt-in must BOTH pass.
  The two heads are mechanically mergeable; fully integrated approval and
  receipt acceptance remains outstanding.
- PR #2336 owns financial-statement maintenance. Its `composition.py`
  changes are in independent setup/maintenance branches and mechanically
  mergeable with this source.
- KFS PRs #2282 and #2177 touch `composition.py` but do not change the
  Company consent/notification functions. Both KFS heads have six
  conflicts against current `origin/main` itself; none are newly caused
  by this PR's UDF changes. Do not merge their older code into this
  branch or disable their source-level governance to satisfy integration.
- The Pull Request body carries the required `Integration coordination:`
  acknowledgment and retains the independent exact-SHA release gate.

The Owner's exact Company `1158` opt-in remains pending provider write and
readback, irrespective of local/unit or GitHub CI results.
