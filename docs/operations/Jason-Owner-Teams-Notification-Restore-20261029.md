# Owner Teams notifications: verified Entra identity and bounded delivery retry

## Live incident evidence (2026-10-29)

Both autonomous ticket lifecycle cards and Production Manager lifecycle notices
use communication.teams.autonomy.completion.send. Profile person-al-v1
is active in runtime; notification send is NOT intentionally disabled.

The existing invoker required an active Teams identity binding with the
historical alias person-al. The authoritative production
microsoft_identity_bindings table has **zero** such rows. It has exactly
one active record for the AOT owner al@teamaot.com, whose Jason identity is
person-entra-(Microsoft Object ID). The old hard-coded alias therefore
fails before outbound Teams transport.

This change resolves the owner only through the same persisted active Teams
binding store. It prefers the existing person-al alias when available; when
absent, it requires an unambiguous active AOT owner-email match, a non-client
binding, and a Jason identity exactly derived from the verified Microsoft object
ID. No caller-provided email or arbitrary recipient is accepted. Missing,
ambiguous, revoked, cross-client or identity-mismatched bindings fail closed.
The governed capability's exact execution plan records the resolved identity
rather than a misleading legacy alias. Authentication and Teams gateway provider
checks remain required and unchanged.

The native Release Manager retry-closeout was used to publish the pending
production_queue_completed event for release release-73904298b17c4dcb
and to complete the documentation/control-board postflight. This DID NOT send
a Teams message or alter live runtime. The release notifier still needs the
new recipient fix deployed.

## Delivery reliability boundary

The release notification worker stores failures with bounded exponential retry
and never claims them delivered on errors. If Teams returns a synthetic gateway
acceptance without an actual provider message ID, the existing unverified
marker remains terminal until independently reconciled.

A restored notifier must not dump months of failed historical release messages
into the owner's Teams conversation. Events with an authoritative created-at
older than 24 hours are recorded as expired_without_delivery, not dropped and
never falsely marked delivered. Newer events are processed at no more than
eight sends per tick, with durable retry not earlier than five minutes.
The source event remains unchanged; the independent error, expired,
unverified and delivered ledgers stay available for operator audit.

## Evidence / acceptance

- Source compilation and focused owner-notification tests pass, including
  legacy owner, exact Entra owner fallback, absent, revoked, duplicate,
  wrong-client, spoofed recipient and wrong-principal denial.
- Using a private SQLite snapshot of the actual production Teams binding DB,
  the revised invoker builds an owner-pinned execution plan without sending.
- Release notification expiration, backoff and confirmed-receipt dedupe tests pass.
- No production sends, database changes, profile activation, release deployment
  or owner-account rebindings are part of preproduction engineering.

**Production acceptance after separate exact-SHA approval:** send one governed
ticket-start and one governed release-complete message, verify provider-backed
receipt and human Teams arrival, check queued event reconciliation, ensure no
historical notification flood and no regression in governed ticket processing.
A green CI run alone is not a production Teams delivery guarantee.

## Concurrent presentation changes

Review of still-open PR #1971 confirms its changes to the notification
renderer are visual presentation-only; it does not change recipient identity
resolution, send governance, or durable release notification retry. Keep the
two PRs separate and preserve the prior card renderer until #1971 is
independently reviewed and accepted.
