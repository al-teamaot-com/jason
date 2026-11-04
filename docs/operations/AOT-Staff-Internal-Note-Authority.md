# AOT staff internal ticket-note authority — isolated preproduction candidate

**State:** Source-only, opt-in disabled by default. No PMv3.1, production, provider configuration or live runtime changes.

## Scope and intended behavior

An authenticated active AOT human may directly ask Jason to create an internal Autotask ticket note under existing JKD-001 governed execution. This is **only** `service.ticket.note.create`. It does not authorize ticket create/update, note update, deletion, customer notifications, endpoint actions or service-principal autonomy.

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

This change repairs Jason's **organization-wide authority matching**, not Autotask security. Current write connector requires an authenticated AOT staff identity to map uniquely to an eligible Autotask Resource; requester TicketNote permissions and provider-native impersonation must permit the operation. AOT personnel without such a Resource will not be able to write with this path until a separately approved role/attribution model is implemented. Do not silently impersonate an unrelated resource or expand the API user permission ceiling.

Internal-note visibility metadata is not enough to ensure no customer notification: existing Autotask workflows have triggered on internally published notes (tracking issue #1298). No Autotask workflow rules are changed by this PR. A separate provider-backed verification must confirm no unintended customer-visible notifications, and any rule change requires a reviewed scope/rollback.

## Preproduction acceptance and release gates

1. Validate the production/main SHA, complete diff, PMv3.1 workstream separation, and target/rollback SHA under Production Manager.
2. Run targeted authority/composition regressions, including AOT technician and front desk positive cases; disabled/nonhuman/foreign/client-scope/inactive-provider/cross-capability negative cases.
3. Confirm no new source config setting enables grants when unset, and legacy routine RW remains disabled when its own profile is unset.
4. Test an exact controlled XYZ Test Company internal note with two **real** staff identities, provider-native resource mapping/permission preflight, exact approval, immutable audit, impersonator/creator attribution, idempotency, and independent note readback.
5. Verify **zero unintended customer notifications**, including Autotask workflow and outbound message history, without suppressing legitimate customer replies. Issue #1298 is a release blocker if unresolved.
6. Test an AOT staff member who lacks an Autotask Resource; verify safe denial until identity/role coverage is separately approved.
7. Release is high risk (authorization policy), requires exact-revision Owner authorization; freeze stays in effect. No direct production deployment or live host editing from this development branch.

## Rollback

With PM-controlled release and approved restart, unset `JASON_AOT_STAFF_INTERNAL_NOTE_PROFILE` and verify the matcher denies new note actions even if the exact grant remains stored. Revoke the stored grant through governed authority administration if necessary. Do not modify other grants, PMv3.1 or the routine RW profile.
