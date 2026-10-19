# Engineering pipeline stall health

A pipeline stage returning zero is not proof of progress. When approved work is outstanding and no workers are active despite available capacity, the pipeline marks operational health degraded and includes the exact blocker in its event. A stage failure still exits nonzero. A blocked backlog alone is not an execution failure and does not force the controller unit into a failed state. It does not automatically retry an exhausted reasoning request or grant additional execution authority.

Transport failures are classified into bounded non-secret categories such as DNS resolution, connection refused, timeout, TLS failure, and unreachable network. These diagnostics must never include raw connection exception contents, endpoint URLs, credentials, or headers.

Operators must still repair the underlying failure and re-admit work through existing governed processes. Deploy only through protected CI, independent review, CCC and Release Manager verification.

## Native ownership of an existing approved implementation

The owner-approved development worker now accepts exactly one `Development pull
request: #number` selection in an already Owner-authored and approved issue. It
verifies same-repository source, target main, immutable head identity and actual
PR state. A stale reasoning failure can then be replaced by the real implementation
and CI stage without resetting retry counters or replaying old model requests.
Prior blocked-request and retry evidence is retained. Drafts are monitored, not
reported production-ready. Green checks mean awaiting governed integration, never
production success. Existing active editors are not preempted and this adoption
path does not mutate source or grant review/deployment authority.

The versioned `config/owner-approved-development-focus.json` restricts admission of
new discretionary development to #1440 and its specifically authorized blockers
#1493/#1458. Existing active engineering can reach a safe checkpoint; critical
support remains under its existing separate priority lane. This implements the
Owner's sole-priority instruction without creating another worker or dashboard.


## Correction after actual supervisor inspection

The live user service has `Restart=no` and no `OnFailure` action. The earlier
proposed nonzero exit for every degraded backlog would not recover anything;
it would instead introduce a failed critical service and could prevent CCC from
releasing the actual repair. That change was removed before deployment. The
pipeline keeps truthful degraded operational evidence, while the native
owner-selected-PR reconciliation advances stale work to its real implementation
and validation state. A process exit code is not a substitute for recovery.

## Primary billing failures must not disappear behind fallback errors

The 2026-10-16 authenticated synthetic runtime probe returned HTTP 429,
`insufficient_quota`, `credit_balance_exhausted`. This is distinct from transient
rate limiting and cannot be repaired by retrying the same request. The reasoning
maintenance now preserves that allowlisted primary error code and a specific
Owner action even when the configured local fallback fails. A successful fallback
may complete bounded work, but the primary billing dependency remains visible.
Persisted billing/spend/quota failures are non-retryable until the external
condition is corrected and recovery is explicitly re-evaluated. No billing changes,
credential disclosure, request-counter reset, or new execution authority is added.

The official provider error taxonomy distinguishes credit exhaustion, organization
and project spend caps, and provider-assigned usage limits. Ordinary 429 rate limits
retain bounded retries and the existing fallback policy. Tests cover both paths.

## Reconciled worker and CI dependencies

The exact #1518/#1522 source pair originally conflicted in the runtime-validation
workflow. The engineering continuity check now runs after dependency installation
but before runtime compilation, preserving both it and the universal approval
trust/persistence suite. No required test was dropped to resolve the conflict.

Existing proposed repairs #1300 and #1296 were reviewed against this worker and
reconciled with their original regressions: rediscovering a PR must not overwrite
ci_repair_needed/ci_repairing, and current authoritative production identity must
match CCC review/report identity before readmission. Four negative regressions
failed before source reconciliation; all 123 targeted worker, focus, pipeline,
reasoning and transport tests passed afterward. This is source-level evidence,
not a claim that the installed worker or production release is already updated.

## P0 support admission and blocked-repair projection (2026-10-18)

`critical_support_blocker` is a separate, read-only pipeline health field.
The coordinator reads fetched `origin/main:SUPPORT.md` rather than trusting a
locally checked-out developer branch, compares canonical P0 support rows with
existing repair states, and records bounded blocked IDs/counts. The worker's
`support_open_issue_not_open` mismatch evidence suppresses stale rows whose
GitHub issue is actually closed; this health projection does not reopen them.
Open P0 issues
missing a canonical row are surfaced from the existing admission audit. When
canonical source evidence is unavailable, health is degraded as
`support_health_unknown` rather than guessed from stale source.

The health projector neither retries exhausted reasoning requests nor reopens
issues. `failed_or_skipped_stages` still describes process execution failures;
a successful systemd unit does not override `critical_support_stalled` or
`approved_work_stalled`. Review and recovery remain under Jason's existing
engagement, evidence, and protected release rules.

## Single verified reasoning transport readmission (2026-10-18)

The P0 support worker may generate one **new** deterministic reasoning request
only if a prior blocked transport response is still verified as failed, the
original request fingerprint matches, and a newer successful request of the
**same schema/kind** is independently present in the protected reasoning spool.
For historical HTTP 400 results, the successful request must be at least as
large as the failing one. A fresh success is evidence of transport viability,
not proof of billing/account recovery or a successful code repair. Known
billing/authorization errors and admitted governed repair handoffs are excluded.

The fresh request adds a recovery-evidence binding to its context, so it is not
a blind replay. It preserves the original failed request, original attempt
budget and immutable audit history, cannot requeue recursively, and remains
subject to P0 eligibility, two-item support capacity, J-CHANGE-002 exact edits,
regression tests, protected CI and separate production owner/CCC authority.
An invalid, stale or missing proof leaves the existing blocked record intact.

## Verified source-context readmission for P0 support admission (2026-10-19)

When a verified P0 support issue-admission repair reports missing exact source
excerpts, the native support worker may produce one new bounded request from
reviewed source files and regression tests. It uses an isolated clean worktree
created from the latest fetched main revision under a distinct -context- branch.
The previous worktree and original successful-but-blocked response stay intact.

The worker verifies the canonical support ID, P0 eligibility, completed prior
edit-plan response, original request fingerprint, exact missing-source reason,
source and test path eligibility, current worktree revision and worker capacity.
New request input binds the original request and source revision. It does not
modify provider records, waive governance, reset the retry budget or authorize a
production deployment. Ordinary J-CHANGE-002, test, CI, owner and CCC release
controls remain mandatory. A missing prerequisite fails closed.
