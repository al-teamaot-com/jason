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

## Authorized native workflow correction — 2026-11-04

After the Owner explicitly requested the proposed update, native Autotask administration split the original rule into two active rules. Rule `17` is now **Notify customer - time added by Autotask resource**, with Time Added by Autotask Resource only and the original conditions/actions. Rule `59` is **Notify customer - public note added by Autotask resource**, with Note Added by Autotask Resource only and an added condition **Note Publish To Equal to All Autotask Users** (`publish=1`). Native options were verified as All Autotask Users (1), Internal Only (2), and Internal & Co-managing (4). Both internal visibility values are excluded from rule 59.

Saved configuration readback confirmed the original CW_TicketID, Help Desk I/II, status and source filters; Ticket Contact and Ticket Creator recipients; Ticket - Update ticket notification 12082024 template; internal workflow audit note; and create-note-from-notification-content behavior. Autotask's copy operation did not preserve auxiliary action settings, which were reviewed and the audit-note/email-note settings restored. **Known exception:** the original rule references a Datto RMM Teams destination, but the native Microsoft Connector selector returned no selectable items. The time-entry rule retains its existing Teams action; the new public-note rule has no Teams action. Teams parity remains unresolved and must not be reported as preserved.

These authorized native changes are separate from Jason runtime deployment. PMv3.1 was not modified. Saved configuration is verified, but controlled internal/public/time-entry notification and outbound-delivery acceptance is still pending. This update does not satisfy the hard provider-backed acceptance gate or authorize production activation of this PR.

## Branch reconciliation — 2026-11-04

The candidate at `3a58c57211625aa7e51f306dc2532b6ab6bd6cfa` passed the authority/runtime/security tests but failed the concurrent integration check because it was behind current main. Reconcile the branch with main `d4e15a01f7a2ac996948f220c738244bb5a6ae14`, preserving all intervening PMv3.1 changes exactly. No PM files belong to the note-authority diff. Re-run CI on the resulting exact branch revision; prior passing results are not acceptance of the reconciled revision.

## Controlled native acceptance evidence — 2026-11-04

Native Autotask workflow tests were executed as the authenticated Al Davis administrator on **XYZ Test Company**, ticket **T20261030.0042** (ID `143421`), using its established owner-controlled test contact. The ticket had a populated contact, issue/subissue and work type; it was temporarily reopened from Complete to In Progress in Help Desk I (queue `29682833`), with empty CW_TicketID and Email source. The older T20260925.0051 fixture was inspected but not modified because it was closed in Jason queue and did not meet the rule scope.

| Case | Provider evidence | Result |
|---|---|---|
| Internal note | `30537361`, title `JASON-NOTIFY-20261104-INTERNAL`, `noteType=3`, `publish=2`, created 20:54:05.143Z | No workflow notification followed the internal note. Independent notification history had no new sent record during the internal-only observation window before the public note at 20:55:06.047Z. Later readback also showed no internal-note notification. |
| Public note | `30537364`, title `JASON-NOTIFY-20261104-PUBLIC`, `publish=1`, created 20:55:06.047Z; rule-fired note `30537366` and notification note `30537367` | Rule 59 fired at 20:55:25.870Z; notification history recorded Ticket - Update ticket notification 12082024 sent to the owner-controlled test contact at 20:55:33.470Z. |
| Time entry | Time entry `15309`, summary marker `JASON-NOTIFY-20261104-TIME`; rule-fired note `30537369`, notification note `30537370` | Rule 17 fired at 20:56:17.537Z; notification history recorded the expected test-contact notification at 20:56:20.567Z, linked to time entry 15309. UI readback confirmed 0.0833 hours (five minutes of actual verification), **Non-Billable**, not posted, with Show on invoice unchecked. |

Reopening generated a public reason note `30537357` and its own expected rule-59 notification at 20:52:29.307Z; that pre-baseline event is not evidence of an internal-note failure. The final notification-history read showed only the reopen/public/time-entry records for the acceptance period. Do not interpret a notification-history sent timestamp as proof of delivery into the recipient's mailbox.

Notification history now works with `company_id=1158`, `ticket_id=143421`, and bounded `page_size`; this supersedes the earlier invocation-failure blocker for these exact reads. Time-entry search returned `CAPABILITY_INVOCATION_FAILED` (correlation `corr_mcp_7ab7b99d0c284e3883d4cfacf9b9436e`), so time-entry state was verified through the authenticated native UI and independent notification history, without redispatching the entry.

**Fixture restoration verified:** ticket readback returned `status=5` (Complete), original queue `29682833`, and original resolution `Acknowledged, closing`. No real customer ticket or endpoint was modified. Test notes and the non-billable test time entry remain as audit evidence.

**Remaining release boundary:** these are native Autotask workflow tests, not Jason end-to-end authorization acceptance. Live discovery still reports `service.ticket.note.create` denied for the authenticated Jason caller. No production profile/grant was enabled, no provider permissions were expanded, and no Jason release was deployed. Governed staging activation, two real staff identity/provider-mapping tests, audit/idempotency acceptance, current production-health evidence and a verified immutable rollback target are still required before presenting an exact-revision production authorization package. The unavailable public-note Teams destination remains a separate unresolved integration dependency.

Reconciled engineering revision `f081bf600726836368a5df64e22ed27da82bd2c8` was mergeable and passed all eight GitHub Actions workflows. This evidence-only documentation commit requires its own current checks; it does not alter the four code/test blobs. PMv3.1 files and runtime were not changed by this work.


## Existing-account live-acceptance constraint (2026-11-05)

The AOT Owner has explicitly **declined any additional Autotask license or new credential-administrator access**. Test with the **existing AOT Al and Lindsey sessions** through the existing Jason/Autotask governed integration. Do not block routine test preparation on purchasing an API user, provisioning a new staging OpenBao AppRole, or copying existing provider credentials into another runtime. The unused private staging directory is not a prerequisite for this existing-account pilot.

A real signed-in test caller successfully read XYZ Test Company controlled ticket `T20260914.0026` and its baseline notes, then attempted an exact internal-only note, `ChatGPT - governed execution test`. The live Jason action stopped at `NO_MATCHING_AUTHORITY_GRANT`, before any provider mutation, client notification, or note readback. This is consistent with **current runtime profile disabled** and draft #2306 unmerged, not evidence the provider denied the authenticated human's TicketNote permission. The user-reported note text is a test marker; it is not proof of identity mapping for Al or Lindsey.

Use the existing `discover_capabilities` -> `execute_governed_capability` path. An eligible AOT human must receive an approval-required authorization decision, not an automatic execute bypass. Exact per-action identity, ticket, note text, approval TTL, no replay, native Autotask Resource permission, internal visibility (`noteType=3`, `publish=2`), independent readback, and **no customer notification** remain mandatory. Do not enable broad routine writes or changes to unrelated tenants. The negative case above is not a substitute for provider-backed positive acceptance.

The controlled fixture ticket `T20260914.0026` is already Complete. Do not change its queue, status, SLA, due date or assignment during note testing. The first deployment of #2306 must remain gated by PM high-risk governance and a separately authenticated exact-SHA Owner release authorization. Live acceptance using Al and Lindsey's existing sessions can proceed only after the approved feature canary is enabled in a controlled release. Treat **provider-backed real-staff testing and production activation as distinct release phases** when predeployment access cannot test the new authority, and stop rather than silently widening the release authority.


## Source-bound activation and protected rollback (November 5)

- The reviewed activation file `config/aot-staff-internal-note-profile.json` declares `internal-note-v1` **for the controlled candidate**. This does not turn on the currently running release. Activation is an authorization-impacting production change and requires its own exact-SHA, complete-scope, immutable-build, CCC, Owner, one-transaction-unfreeze and rollback gates. The production freeze remains active until that independently approved transaction.
- The **existing** PM v3.1 host runner now reads the exact source declaration, attests the selected setting as part of the native deploy contract digest and rejects a mismatched host override. Both existing runtime and MCP deployment scripts independently parse the same immutable config and refuse unreviewed values or host overrides. No new execution daemon, one-off ticket script, API credential or generalized wildcard grant is introduced.
- PM's actual isolated preproduction environment forces `JASON_AOT_STAFF_INTERNAL_NOTE_PROFILE` to **empty** and retains `JASON_AUTOTASK_MUTATION_ENABLED=false` while running normal no-write probes. On either native `rollback-current` path, the staff-note setting is explicitly **empty**, even if candidate source declares `internal-note-v1`. The matching organization's durable authority grant, if persisted, is inert when the profile is disabled.
- Positive live acceptance **must** be demonstrated using Al Davis and Lindsey Collins in separately authenticated existing Microsoft/Jason sessions and their existing active, licensed Autotask Resource identities, not with a new paid account. Read-only provider queries confirmed both existing human identities are active in their respective systems. Neither technician's successful Entra mapping is by itself evidence of TicketNote provider create permission. That permission remains enforced by Autotask native `ImpersonationResourceId` and `TicketNotes/entityInformation` preflight. An earlier impersonation HTTP 500 affecting some Autotask reads means the specific TicketNote write operation must be tested; do not assert provider acceptance before a real signed-in write/readback.
- If authorization is allowed, create **one** internal-only note (`noteType=3`, `publish=2`) on the controlled XYZ Test Company ticket, verify exact content/note ID and native human attribution, zero client notification, no unrelated ticket mutations, and no replay; repeat with the other technician using a distinct note and approval. Requester/Resource mismatch, wrong client, unapproved/replayed/expired action, provider inability, and service/nonhuman principal must fail closed.
- **The P0 technician Request-to-Execution Gap is broader than this first internal-note slice.** It only closes on evidence of dynamic discovery, policy-constrained action selection, governed execution with continuation/readback, documentation, and unfamiliar ordinary technician tasks without adding a task-specific script. Do not label source merge or an isolated note trial as overall completion.


## General AOT technician request-to-execution acceptance

**This note-write capability is an initial safety canary, not the project objective.**
The P0 technician Request-to-Execution Gap (#2104) must work with AOT's existing
licensed technician accounts, including future authorized staff not known when
this source was written. Never use a hardcoded Al/Lindsey allowlist, a per-user
script, an extra paid Autotask seat, a new approval engine, or a provider API
bypass to satisfy an operator request. Existing registered provider-neutral
capabilities, discoverable argument contracts, signed human identity, provider
resource permissions, exact-argument approval, asynchronous job handling,
independent readback and auditable ticket evidence are the reusable mechanism.

The note-policy source test uses **five different simulated active AOT humans**
against one organization-scoped standing grant. Each requires their own approval;
approvals cannot be reused by another human. Service principals, disabled and
foreign humans are denied, while unknown identity yields an indeterminate
fail-closed decision. These are source tests only, not Autotask provider-backed
human permission proof.

The wider acceptance suite for #2104 must include unfamiliar requests involving
at least Autotask evidence plus an existing governed endpoint or Microsoft 365
read, and a technician-authorized action where the provider supports it. Jason
must select existing capabilities dynamically instead of adding one-off code,
continue after routine read/diagnostic failures using permitted alternatives,
monitor any async provider job to a terminal state, perform post-action provider
readback, and record exact findings in the original ticket. Wrong user, client,
approval, arguments, replay, unsupported operations or potentially disruptive
actions without technician-specific consent must remain fail-closed.

**Release sequencing:** merge and preproduce the source only after all required
checks are green; obtain an independently authenticated, exact-SHA Owner release
authorization for any production activation; verify one controlled XYZ Test
Company ticket with Al and Lindsey separately; then verify the general reusable
path and negative cases before claiming the larger objective complete. Any
newly discovered issue must be resolved through the existing generic layer,
not an account-name exception or new collection of scripts.
