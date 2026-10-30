# Jason Issue #770: owner escalation and independent Teams delivery

## Production evidence (October 29, 2026)

Autonomous ticket-worker scans continue, but many tickets are classified
unsupported, blocked, waiting for human review or missing device access.
Issue #770 expressly requires every ticket Jason cannot advance to generate a
proactive, actionable Owner notification with a bounded failure record.
Previous pickup/completion notifications used a single recipient identity and
a synchronous Teams send inside the ticket worker; either a wrong binding or a
slow provider call could break the intended user experience or stall a scan.

The earlier Issue #770 source work added a durable SQLite notification outbox.
This change makes outbox delivery a distinct **auxiliary** maintenance
operation, never a ticket-worker execution dependency. The existing runtime
starts a separately supervised ticket-worker process and auxiliary process.
Only the auxiliary process can call the governed owner-notifier transport.
Ticket pickup, completion and patch-completion operations now persist a
notification intent and return without waiting for Teams.

## Owner attention rules

After each full discovery cycle, Jason stores its classifications, scan
metrics and independent owner-attention intent for:

- Unsupported tickets lacking an applicable promoted playbook or possessing
  unsupported Windows licensing requirements.
- Governance and execution failures, including missing authority, worker
  blocking and failed handoff.
- Tickets requiring human review or approval.
- Device-access waits and specific dependency/capacity blockers.

Each notice identifies the exact Autotask ticket number and issue; the
authoritative company ID or verified company display name when available; a
linked CI ID or known worker hostname when available; the classification,
the checks performed, and a short next action. No company/device is invented.
The source ticket number is preserved; a UI deep link is omitted unless an
authoritative provider URL is available. No client notification, approval or
remote endpoint execution can be triggered by the Teams message itself.

A unique event key is derived from the ticket, category and reason, not the
minute of the scan. Repeated scans do not duplicate an existing message.
A later classification change cancels a queued-but-undelivered owner-action
message rather than sending an obsolete blocker.

## Delivery state and operational isolation

The auxiliary worker reads the shared WAL SQLite outbox, attempts at most
four governed sends per auxiliary cycle, and retains attempts, next due time,
last error type, event identity and provider receipt. Explicit provider send
errors receive bounded retry; an accepted-only synthetic Teams receipt is
marked unverified and is not automatically sent again or called delivered.
Messages older than 24 hours expire as undelivered evidence rather than
becoming misleading historical Teams notifications.

The ticket-worker process no longer makes synchronous Teams POSTs while
discovering candidates, updating PSA tickets, verifying patches, or
recording a scan. Notification transport cannot consume the two ticket
remediation slots. If Autotask discovery fails, auxiliary delivery can still
advance previously queued notifications. Teams delivery failure never
reverts a readback-verified ticket completion.

Delivery reports must distinguish durable queueing, provider message-id
acceptance, acceptance without a message ID, and owner-confirmed arrival.
The presence of a queued or delivered marker alone does not demonstrate that
the Owner read the message.

## Acceptance and deployment boundaries

- Unit integration: one attention intent per unsupported, blocked,
  human-required or access-limited ticket; status/creator/client boundaries
  unchanged; no emits for already-active or technician-owned non-actionable
  tickets.
- Backlog: 65 independent unsupported tickets all enter the outbox without
  first-page starvation; only four governed sends per auxiliary tick.
- Repeated scans and process restart do not duplicate durable events.
- Changed PSA classification prevents obsolete attention requests.
- Missing company/device identity is explicit instead of silently skipping
  the ticket or inventing details.
- Delivery failure records and retries persist; synthetic receipt is not
  recorded as a verified Teams message.
- A normal full ticket-worker scan that discovers a previously unsupported
  ticket writes the durable owner-action message without calling Teams.
- Existing diagnosis, ticket writes and playbook execution are still governed
  by the pre-existing exact approval, readback and non-disruption rules.

Production deployment remains subject to Production Manager exact-source
acceptance, reviewed full release manifest, valid rollback and explicit
Owner deployment approval for the exact SHA. Live acceptance must show
continuous worker scans while Teams is slow, actual human Teams delivery,
a real available-device promoted-playbook ticket being fully resolved, and
verified PSA/worker agreement. Green tests alone are not closure of #770.

## Concurrent integration review

PRs #2125 and #2128 register routine read/write capabilities and provider
invokers in separate composition blocks. This source only installs a
ticket-notification maintenance lane, with no new routine RW activation.
PR #2126 separately adds optional Windows Time JSON shadow configuration and
existing shadow constructor inputs. This notification fix does not depend on,
enable or change the JSON pilot. Protected main merge and Production Manager
must preserve all unrelated changes; none is silently included in the
bounded ticket-notification scope.


## Production activation defect and correction: 2026-10-29

The exact protected release 3d62c211bbc861636658e0d7b6cbb5363d12a47e
passed native deployment and CCC, and the ticket worker resumed normal
scans. It queued more than 100 owner Teams notification intents, but every
one was still pending with zero attempts.

The root cause is a cross-process settings mismatch, **not a lack of
Autotask or Teams account permission**. In
auxiliary_maintenance_runtime_settings(), the auxiliary process sets
autonomy_worker_enabled to False to avoid duplicate ticket admission.
The new TicketOwnerNotificationMaintenance constructor also required
that flag to be True, so the sender was omitted from the auxiliary
composition. The main HTTP process also has that flag disabled, and the
ticket worker correctly does not send Teams, leaving no active sender.

The correction binds owner-notification delivery to the **auxiliary
maintenance profile**, independent of the ticket-admission flag, while
retaining the previous single-process compatibility rule. Exactly one
auxiliary sender is created; neither HTTP nor the ticket worker receives
a duplicate sender. No new provider access, mutable control authority,
client notification or permission has been added.

Existing durable outbox state is preserved. A second fix prioritizes
work_started, work_completed, and patch_completed events above existing
work_blocked backlog notifications, preventing a new ticket-start update
from waiting behind roughly 100 older blocker alerts. The bounded
four-per-cycle delivery limit and recorded retries/receipts remain
unchanged.

### Mandatory regression and live acceptance

- Test the *actual* auxiliary_maintenance_runtime_settings transformation:
  it disables autonomous ticket admission, yet build_runtime_application
  in auxiliary profile must create a TicketOwnerNotificationMaintenance.
- Queue a synthetic ticket lifecycle intent in isolated SQLite and tick
  that actual auxiliary maintenance instance; verify exactly one provider
  receipt, one delivered marker and no duplicate send.
- Verify ticket_worker and HTTP-only profiles create no second sender.
- Queue 100 older blocked-owner intents plus new ticket-start/completion
  events; verify lifecycle events are selected first, without changing
  backlog retention or suppressing legitimate owner-action messages.
- After separately approved controlled deployment, verify real Teams
  provider receipts and owner arrival for actual pickup and release
  notifications, a continuously advancing ticket-scan heartbeat and
  no forbidden endpoint/Autotask mutations.

The previous source merge and CCC PASS did **not** prove ticket notification
delivery. This exact defect was discovered through live outbox evidence and
requires a fresh exact-SHA release and owner authorization before production
activation.
