# PMv4 meaningful Teams event notifications — Owner directive 2026-11-11

**Status: source-only, tested locally; NOT installed/activated in production.**

## Desired behavior

When J-Man observes a verified, meaningful change in an existing PMv4 objective, the **existing** OpenClaw Teams sender should notify the licensed AOT Owner. Notify only three classes:

1. **Verified accomplishment** — a substantive milestone with independent readback (e.g. a reviewed PMv4 component passes its acceptance scope). Report the *actual stage*, not whole-PMv4 completion.
2. **Material problem** — a verified blocker, failed important test, stalled owner-assigned work, or operational degradation that prevents the next reasonable step.
3. **Owner decision required** — a genuine exact decision/authorization or external dependency. State what is needed, the reason and next safe action. A Teams message is **not** a release approval, approval card, or Owner identity proof.

No notifications for task starts, trivial tests, ordinary commits, short retries, housekeeping, repeated unchanged warnings, or every scheduled status run. No additional routine monitoring channel, approval gate, worker, scheduler, database, subscription, or service.

## Existing-system integration

- The **existing** OpenClaw J-Man agent is accountable for decisions and review, and Workboard/PMV3 provides durable work evidence. Do not trust the agent's success assertion alone.
- Use `config/openclaw-specialists/reporting/status_report.py:send_meaningful_event` as the handler for a **trusted native task/work-engine event** after independent status verification. The same reporting source retains read-only status rendering, while its legacy `--send` path suppresses routine scheduled Teams reports.
- `meaningful_events.py` handles a strict `PMv4.11112026.1` event, three allowed kinds, material threshold, required evidence reference, stage-accurate text, explicit next action/Owner action and overall percent only as an estimate.
- A trusted coordinator MUST bind `trusted_evidence_check` to fresh authoritative GitHub/provider/native ledger readback. A caller-supplied flag, model text, task record alone, or mocked callback is NOT acceptable production evidence. Without the trusted adapter, events must not be sent.
- The sender uses the current `JMAN_TEAMS_TARGET` verified `user:<Entra OID>` route and invokes the existing `openclaw message send --channel msteams`. Never change recipients automatically or send an approval card.
- Notifications append an **at-most-once delivery reservation** and any gateway receipt to the **existing** J-Man `TASKS.md` objective register, under a file lock. The event id must uniquely identify the meaningful transition/work generation; repeated events are suppressed, conflicting payloads rejected.
- Provider outcome without a positive message reference stays **delivery unverified**; it is not automatically resent. Notification failure must not change the underlying task, promote a release, restart a service, or expand execution authority.

## Source-only acceptance performed

`python3 -B -m unittest discover -s tests -p test_pmv4_meaningful_teams_events.py`

`python3 -B -m unittest discover -s tests -p test_pmv4_evidence_status.py`

Tests cover the three event classes, routine-event suppression, unverified evidence denial, stage and Owner-action bounds, at-most-once duplicate/conflict suppression, uncertain delivery, synthetic receipt rejection, existing Teams sender and licensed Owner address format, and the existing status reporter's event hook. GitHub protected CI must pass on the exact candidate.

## Remaining gates before calling operational

1. Connect the **existing** J-Man native event return and Workboard/PMV3 completion/blocker/Owner decision records to a trusted read-only evidence adapter. Do not add another background worker.
2. Validate the real materiality decision and immutable event IDs using completed, blocked and decision-required PMv4 work scenarios. Include at least one routine test that causes **no** Teams message.
3. Run a controlled end-to-end test against the licensed Owner Teams route, verify actual provider message IDs, deduplicate across an agent restart, and validate that an uncertain send does not repeat.
4. Review the final integrated source and CI, then deploy only with the applicable governed PMv4 exact-release approval and rollback; verify unrelated production Ticket Processing Core remains undisturbed.

Nothing in these source-only tests constitutes a production Teams notification or permission to modify a live gateway or protected Core.
