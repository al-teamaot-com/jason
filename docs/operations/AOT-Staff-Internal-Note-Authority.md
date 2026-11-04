# AOT staff internal ticket-note authority — isolated preproduction candidate

**State:** Source-only, opt-in disabled by default. No PMv3.1, production, provider configuration or live runtime changes.

## Scope and intended behavior

An authenticated active AOT human who has an active, authorized Autotask login/Resource may directly ask Jason to create an internal Autotask ticket note under existing JKD-001 governed execution. This is **only** `service.ticket.note.create`. It does not authorize ticket create/update, note update, deletion, customer notifications, endpoint actions or service-principal autonomy.

The exact standing grant requires `PermissionMode.EXECUTE` **with `approval_required=True`**. Existing MCP authenticated-imperative approval processing must record an exact, short-lived, audited approval for the instruction and bind the provider execution plan; the grant does not bypass this control.

The existing `autotask_internal_note` connector still enforces `noteType=3` and `publish=2`, bound ticket identity, Autotask requester authorization/impersonation, at most one provider mutation, and verified post-write readback. This source change neither grants provider permissions nor alters credentials.

## Isolated activation

Configure on the *runtime service* only **after** approved source/release validation:

```text
JASON_AOT_STAFF_INTERNAL_NOTE_PROFILE=internal-note-v1
```

Any other value, including unset, leaves the new matcher disabled. On enabled runtime composition, one idempotent policy grant is seeded:

- Policy `routine-write:aot-staff-internal-note-v1`
- Grant `grant-aot-human-internal-ticket-note-v1`
- Subject `organization:aot`; mode `EXECUTE`, `approval_required=True`
- Accepted identity type `human` or `person`, active, same organization
- Accepted provider `autotask_internal_note` only, active approved/pilot external connector
- Accepted capability `service.ticket.note.create` only, active MCP action-enabled

`JASON_AOT_ROUTINE_RW_PROFILE` and its broader ticket-write grant are **unchanged** and are not prerequisites for this opt-in.

## Explicit dependencies and exclusions

This change repairs Jason's **organization-wide authority matching**, not Autotask security. **Owner decision (2026-11-04):** AOT staff without an Autotask login are not eligible to use Jason; there is no requirement for a non-Resource fallback. For this note-create capability, deny when the authenticated person cannot map to exactly one active authorized Autotask Resource. The existing connector must enforce the user's TicketNote permissions and provider-native impersonation; never silently impersonate another person, use the API user as substitute requester, or expand permissions. Broader Jason admission policy is a separate existing governance control and is not modified by this note-only PR.

Internal-note visibility metadata is not enough to ensure no customer notification: existing Autotask workflows have triggered on internally published notes (tracking issue #1298). **Live 2026-11-04 evidence:** ticket T20261009.0068 (Autotask ID 142386), internal note 30520891 (`noteType=3`, `publish=2`) at 2026-10-10T02:31:36Z. Notification-related notes 30520892, 30520893, 30520894 appeared about 17 seconds later. The workflow named **Notify customer when AutoTask resource updated a ticket** reported its event **Note Added By Autotask Resource, Time Added By Autotask Resource**; UDF `CW_TicketID` empty; queue Help Desk I/II; several status and source allowlists; and actions sending `Ticket - Update ticket notification 12082024` to Ticket Contact and Ticket Creator, creating notes, and posting to Teams. The notes establish the workflow ran and generated a notification record; they do not independently prove delivery to a specific customer mailbox.

**Required change, outside this source-only PR:** Use an authorized Autotask administrator to inspect the exact rule and the available native condition/filter controls for note visibility/type. Modify only the intended customer-facing rule so **internal technician notes are excluded** while legitimate public/customer-facing notes and time entries retain their intended notification behavior. If the rule designer cannot distinguish internal notes natively, design a separate explicit customer-update trigger/condition or a safe route; do not assume a Jason-only note title, note type, or `publish` value prevents workflow evaluation. Capture a before/after rule snapshot and rollback. Inspect other customer-facing rules that also use Note Added By, not only the named rule. Do not disable the notification rule globally, suppress ordinary client replies, or edit provider configuration without approval.

**Release acceptance** requires a controlled provider-backed end-to-end test using an authorized AOT Resource and test company/contact: create an internal note on a ticket meeting the prior workflow criteria; independently confirm the note is correctly private, no customer-facing workflow notification occurred and no outbound message was sent. Then create an explicitly public customer update and verify ordinary notifications still work. Confirm notification-history read health or independently observe provider notification/outbound mail evidence. Earlier `service.notification.history.search` calls failed, including on 2026-11-04 (`INVALID_CAPABILITY_ARGUMENTS`), so ticket-note history is currently the strongest available indication, not definitive delivered-email proof. This is a **hard production activation blocker** until independently accepted.

## Preproduction acceptance and release gates

1. Validate the production/main SHA, complete diff, PMv3.1 workstream separation, and target/rollback SHA under Production Manager.
2. Run targeted authority/composition regressions, including AOT technician and front desk positive cases; disabled/nonhuman/foreign/client-scope/inactive-provider/cross-capability negative cases.
3. Confirm no new source config setting enables grants when unset, and legacy routine RW remains disabled when its own profile is unset.
4. Test an exact controlled XYZ Test Company internal note with two **real** staff identities, provider-native resource mapping/permission preflight, exact approval, immutable audit, impersonator/creator attribution, idempotency, and independent note readback.
5. Verify **zero unintended customer notifications**, including Autotask workflow and outbound message history, without suppressing legitimate customer replies. Issue #1298 is a release blocker if unresolved.
6. Test an AOT staff member who lacks an active authorized Autotask Resource; verify safe denial with no fallback, according to Owner's 2026-11-04 policy.
7. Release is high risk (authorization policy), requires exact-revision Owner authorization; freeze stays in effect. No direct production deployment or live host editing from this development branch.

## Rollback

With PM-controlled release and approved restart, unset `JASON_AOT_STAFF_INTERNAL_NOTE_PROFILE` and verify the matcher denies new note actions even if the exact grant remains stored. Revoke the stored grant through governed authority administration if necessary. Do not modify other grants, PMv3.1 or the routine RW profile.

## Integration coordination — 2026-11-04

The active draft PR was compared with other open changes to `composition.py`: #2282 and #2177 (KFS copier/SharePoint evidence), #2178 (Datto patch reads), #2125 and #2128 (routine Autotask RW registration), and #2126 (Windows Time JSON shadow). Those patches add separate import/configuration/invoker lines, while this branch adds a separate note-only authority import and grant seed. Preserve all changes during release reconciliation; do not merge this branch over those changes or alter PMv3.1. See the PR's `Integration coordination:` acknowledgement for the reviewed overlaps.

## Live Autotask rule editor inspection — 2026-11-04

Using the Owner's already-open authenticated browser tab, read-only inspection confirmed the exact Autotask ticket Workflow Rule Editor: `Notify customer when AutoTask resource updated a ticket`, workflow rule ID `17`. The rule is ACTIVE. In **Events**, BOTH `Note Added by: Autotask Resource` and `Time Added by: Autotask Resource` are checked. **Conditions** already include `UDF: CW_TicketID Is empty`, `Queue Name In List [Help Desk I, Help Desk II]`, `Status In List [...]`, and `Source In List [...]`. The UI's condition-attribute dropdown explicitly offers `Note Publish To` (value `387`) and `Note Type` (value `388`), currently not among the populated conditions. **Actions** include `Create Ticket Note` (Internal Only) and `Post in Microsoft Teams Channel`; customer email action was independently confirmed by live rule-fired ticket note `30520893`. The browser read did not select `Note Publish To`, so its exact available comparison values are **not yet verified**.

**Recommended narrow correction for provider-administrator review:** Separate note-added and time-added triggers into distinct rules while preserving current scope, recipients and notification template. Keep the existing time-entry behavior separately so a `Note Publish To` filter does not inadvertently suppress time-entry alerts. For the **note-added** rule, set `Note Publish To` to an explicitly customer-visible/public value (after verifying option values in the UI), and verify an internal note (`publish=2`) is excluded. Evaluate whether other note types require inclusion based on existing AOT policy. Preserve rule snapshots and rollback; inspect whether rule cloning is supported before altering existing configuration. Do **not** simply uncheck `Note Added by` on the existing rule and assume public note notifications remain.

These are **read-only browser observations**. No live workflow edits or save actions have occurred. This confirmation narrows design but does not satisfy the provider-backed internal/private and public/notify acceptance gate.
