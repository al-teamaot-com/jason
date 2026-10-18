# First Teams shared-service adoption: autonomous status (shadow-only)

**Date:** 2026-10-18
**Parent:** P1 TODO-COMM-SHARED-001 #1566; architecture ADR-013; usage-led consolidation #1535.
**Current state:** SOURCE-ONLY compatibility adapter / no-send preview, not a production switch.
**Source base:** GitHub `faaac51ab2c6be2d71d1aabae5b38a2701ffcff7`. No customer/provider changes and no Teams cards sent during this work.

## Why this is the first producer

Live read-only inventory of `/var/lib/jason/openclaw/orchestration-events.sqlite3`, rolling last seven days as of 2026-10-18, counted:

| Event class | Recorded events |
| --- | ---: |
| `communication.teams.autonomy.completion.send` capability completed | 684 |
| Same capability failed | 1 |
| Same capability requested | 686 |
| General governed `communication.teams.message.send` capability completed | 2 |

The observed Teams gateway's available Docker logs contained 64 proactive-send accepted events during the requested lookback. **These different counts are not directly comparable**: the event ledger measures orchestration invocations, Docker log retention and sampling may differ, and provider accepted is not user-visible Teams delivery. Source analysis also shows the autonomous notification capability covers unrelated high-risk production/owner-action notices. The first adapter therefore intentionally targets **only three nonapproval status types**, not the entire capability:

- `work_started` — progress / informational.
- `ticket_status_updated` — progress / informational.
- `work_completed` — verified completion / success.

The exact invocation split by these three event types is not proven by the current event-store rows. Measure it before enabling a live canary.

## Compatibility contract

Added `implementation/runtime_service/src/jason_runtime/autonomous_completion_teams_compatibility.py`:

1. **Same source of truth:** call the existing `autonomous_completion_notification._render` with its existing bounded arguments; do not duplicate work/ticket/business fact generation.
2. **Canonical normalization:** turn the verified existing text, title and `FactSet` into a provider-neutral `Interaction` v1 with `InteractionKind.PROGRESS` or `NOTICE`; reuse `ExistingTeamsInteractionAdapter.informational_card` and its semantic `Accent` / `Good` colors. Canonical card is a pure preview; it never has approval buttons, form fields, or a client recipient.
3. **Stable scope:** preserve the original orchestration execution ID as interaction ID, original correlation ID, exact AOT organization, original `jason-autonomy-worker` principal, and fixed `person-al` recipient. Never generate a new random ID on retry.
4. **Exact facts and content:** complete existing legacy notification text is retained as the canonical summary, with identical structured facts and title. New visual layout (1.5 instead of 1.4) is a **preview**, not silently deployed. Any unrecognized or changed legacy card structure fails closed.
5. **Single channel boundary:** `GovernedAutonomyStatusInteractionPort` delegates to the **existing** `UniversalInteractionService.dispatch` with an AOT owner-only route guard that pins permitted purpose, executive audience and `teams` channel. That existing service owns authorized route, one durable send claim, approval separation, audience review and provider-accepted receipt. The port is not constructed in live composition.
6. **Out-of-scope events:** `work_blocked`, `production_owner_action_required`, self-heal escalation, production release notices, patch/deployment confirmations, and procurement/billing actions remain on their existing paths until their own separate review.
7. **No new transport/ledger:** no additional Teams bot, direct HTTP, Microsoft tenant, provider credential, approval store, webhook or retry mechanism is introduced.

## Inert rollout states (not enabled by this PR)

```text
LEGACY_ACTIVE (live and unchanged)
    -> SHADOW_NO_SEND (call pure adapter on same arguments; compare title,
       canonical summary, facts, semantic status; no Teams POST)
    -> REVIEW_PARITY (independent user-facing/mobile review of templates,
       real invocation frequency and route/recipient authorization)
    -> CANONICAL_SINGLE_SENDER (separately approved feature-flagged source cutover,
       exact one durable claim and one provider send, never both)
    -> LEGACY_RETIRED (only after proven zero consumers and rollback plan)
```

A future rollout configuration must be restricted to exactly one sender per workflow, require an explicit approved exact-SHA release, and fail closed if it cannot guarantee this. Shadow errors must be measured without suppressing the existing legitimate notification. Unknown delivery states must NOT trigger a blind retry.

## Required next acceptance before any live migration

- Count true `work_started` / `ticket_status_updated` / `work_completed` producer events and identify actual active consumers and potential recipient duplication. The current 684 count is broad and not a per-event send count.
- Verify feature flag + ownership for a limited canary in an existing authorized internal owner Teams conversation (not a client). No changes to procurement/release approval authority.
- Compare old/new actual Teams mobile/Desktop message meaning and exact facts, with at least normal, failure, cross-tenant, wrong-recipient, unexpected event, unknown gateway delivery and no-duplicate cases.
- Keep source `communication.teams.autonomy.completion.send` request/permission/plan fingerprint, original business action result, recipient bindings and event/spool markers unchanged until a governed plan-parity migration is separately reviewed. A card-format change cannot invalidate execution-plan approval silently.
- Verify preproduction, CCC, root host, healthy release, a previously verified rollback image and automatic old-path reinstatement before enabling canonical-only.
- Never treat `provider_accepted` as proof the owner saw the message, and never treat a status notice as an approval. All high-impact approval workflows remain separate.

## Evidence and tests

`implementation/runtime_service/tests/test_autonomous_completion_teams_compatibility.py` covers semantic content/title/fact/color equivalence for three status types, proof of **no network send** in preview, rejection of all five high-risk/unsupported event examples, fixed original AOT organization and owner recipient, malformed IDs and arguments, guarded single-channel route, wrong tenant/recipient/purpose, actual `UniversalInteractionService` one-attempt/duplicate rejection, and no approval buttons. The pre-existing notification, communications, interaction and Owner UAT tests remain unchanged and passing.

**Production/CCC:** This source-only PR requires normal GitHub review/CI. It does **not** independently authorize the new source revision for production; production remains on the last approved release.
