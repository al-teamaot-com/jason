# Production Manager P0: verified deployment and deferred administrative closeout

## Invariant

Production deployment success is decided only by the exact source/owner authority, protected release and rollback contract, runtime/MCP/host/controller alignment, health checks, authenticated provider canaries where required, post-deployment CCC certification, desired-state drift evidence, and the protected last-known-good commit. A failed GitHub publication, control-board update, or owner notification must not roll back a release that passed those checks.

## Commit and handoff

Once the critical production evidence is verified, the release manager records a **durable pending** `administrative_closeout` queue in the release record before committing the new last-known-good manifest and transitioning the release to `production_verified` and `closed`. The production transaction then exits immediately. No external documentation publisher or notification service is invoked inside the deployment transaction. A failure of either task cannot enter the production rollback handler, reopen the circuit breaker, or keep the production freeze exception open.

The queue contains two independently retriable items: `documentation_control_board` (GitHub documentation reconciliation plus control-board publication, both required) and `owner_notification` (durable local completion-notification event). Each tracks `status`, `attempts`, last attempt time, sanitized failure category/type, and completion time. A completed item is not repeated during later retries. Notification event publication is not an assertion that Teams has delivered the message; delivery remains subject to the existing notifier.

## Scheduled retry

The existing five-minute `jason-release-manager.timer` runs `promote-eligible`. Administrative retry is performed **before** the `automatic_promotion_enabled` policy check, allowing it when automatic production promotion is disabled. Pending closed releases become eligible after the first tick, and unsuccessful items are retried no more often than every 15 minutes. The documentation script has a 120-second execution limit. Each scheduled cycle handles at most one release and uses the same exclusive production transaction mutex to avoid racing active deployments.

The retry proves the exact live release SHA matches the closed record, checks full Runtime/MCP/host alignment, and materializes a private immutable Git worktree of that historical source. An obsolete or rolled-back release is never allowed to publish a false success. Automatic retry never modifies the runtime, MCP, host release, approval state, freeze, or last-known-good manifest. A failure remains durably pending, with a sanitized journal entry, rather than causing a failed release or a failing production service timer.

For a bounded manual retry, use the `retry-closeout --release-id <release-id>` command under a clean checkout pinned to the same release SHA. It returns success only when both administrative tasks have been queued/published successfully; incomplete tasks stay pending.

## Operational visibility and acceptance

Inspect `records/<release-id>.json`: release `state=closed` and `production.health_passed=true` establish deployment success; `administrative_closeout.needs_retry` separately reports outstanding administrative work. `production.documentation_reconciliation`, `control_board_publication`, and `owner_notification` remain `pending` until their respective publication operations succeed. Monitor `RELEASE_CLOSEOUT_RETRY=COMPLETE|PENDING|DEFERRED` in the five-minute service journal. The production freeze can remain active throughout administrative retry.

Regression tests inject failures into both administrative systems, prove a healthy release closes with no rollback or circuit-breaker opening, verify durable pending evidence, idempotent recovery, stale-release refusal, interval gating, and operation with automatic promotion disabled. They also verify that publisher calls never occur within the critical production transaction. All production authorization and disruptive-action restrictions remain unchanged.
