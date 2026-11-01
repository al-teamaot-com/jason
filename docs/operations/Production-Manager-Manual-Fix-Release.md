# Production Manager — Manual Fix Without Disturbing Other Development

**Phase 1 (2026-10-27).** This is the supported *manual, single-release* process using the existing governed Release Manager. It does not create a second deployment path or authorize a deployment. The Owner-ordered production freeze remains ACTIVE until an **exact-SHA, one-transaction** Owner exception.

## Goal and boundaries

Ship a reviewed fix through protected GitHub `main` with no modification to another developer's dirty/unmerged worktree, no silent inclusion of unrelated merged changes, exact artifact and rollback identity, and reliable core-ticket canaries.

- Every independent fix has its **own branch and worktree**. No hard resets, clean operations, branch deletion, forced pushes, or edits to other developers' worktrees.
- GitHub PR review and required CI precede merge to protected `main`.
- **The existing Production Manager currently deploys the complete exact protected-main SHA, not an individually cherry-picked PR.** If unrelated changes have already merged since the installed production SHA, they WILL be included in that candidate. The scope reviewer makes this explicit and blocks unacknowledged commits. Do not treat the release as a single-fix deployment unless the inventory confirms it.
- The global deployment-freeze marker and the unattended incident hold are separate. Technician scope review, isolated preproduction and a signed Owner release approval are **not** permission to remove either hold without a new exact-release exception.

## Manual sequence

1. Work only in a dedicated development worktree/branch based on the verified remote protected main. Edit and commit the intended fix there. Run focused unit and integration regressions. Open the PR; obtain reviews and required CI. Never work directly in `/opt/jason/current` or an existing developer's workspace.
2. Before merging, check whether another active PR touches the same implementation paths and resolve actual integration conflicts with the other developer. Merge only approved fixes into protected `main`; leave unrelated branches unmerged.
3. With the new protected main SHA and separately observed root LKG/baseline SHA, use the native PM `prepare` command. PM must check required CI, immutable Docker artifacts, rollback readiness, exact SHA, independent CCC and isolated preproduction, without touching production.
4. Use the **read-only** native `review-impact` command for that release ID. Its output lists every first-parent commit since the running baseline, every changed file, all overlapping open PRs and any overlapping dirty local worktrees. Do not assume an omitted PR file list means no conflict: truncated GitHub results are retrieved with complete pagination or the review blocks.
5. A technician must explicitly name **all** intended merged PR numbers (or exact standalone commit SHAs) and acknowledge each investigated overlapping PR/worktree. Re-run `review-impact` with those selectors and `--record` only after the review is complete. This stores a version-bound scope digest under the existing exclusive release transaction lock. It does NOT mark the release Owner-approved.
6. Obtain an independently authenticated Owner approval bound to the exact candidate SHA and the full reviewed file scope. The Owner must separately authorize one temporary freeze exception before the native `promote` transaction; do not infer blanket authorization from this procedure.
7. Native PM acquires the release lock, rechecks protected main and the reviewed scope (including active PRs/worktrees), then performs its normal CCC, root/host/controller alignment, audited promotion, independent verification and known-good rollback on failure. If a new PR overlap, dirty worktree overlap, merge, or review digest appears, **stop and re-review** rather than deploying.
8. Before and after promotion, require **real authorized** ticket count, full search pagination and exact-ticket read (same fixed window and tenant scope); expected denial and HTTP health alone are NOT success. The separate ticket-gate implementation work is tracked under #2075 and PR #2074; do not label this step fully automatic until the release controller uses an authenticated read port and verified receipt.
9. Observe subsequent scheduled approval-only and independent drift-watchdog cycles. Mark acceptance complete only when no failed units, circuit breaker closed, drift PASS, immutable LKG aligned, ticket canaries successful and unrelated developer files unchanged.

## Native commands (examples; replace exact values)

Only the release review is read-only. The recording command changes the **release record only**, never worktrees. These commands are for an authorized technician on Jason, and production promotion is prohibited while frozen.

```sh
python3 /opt/jason/current/tools/release_manager_host_runner.py prepare --candidate-sha <exact-protected-main-sha> --change-class release_blocker

python3 /opt/jason/current/tools/release_manager_host_runner.py review-impact --release-id <release-id>

# After reviewing the entire reported scope and overlapping work:
python3 /opt/jason/current/tools/release_manager_host_runner.py review-impact --release-id <release-id> --include-pr <reviewed-merged-pr> --acknowledge-overlapping-pr <verified-open-pr> --record

# Owner approval and 'promote' are SEPARATE governed steps and remain
# prohibited without a new exact-SHA Owner freeze exception.
```

If more than one merged PR appears, add a separate `--include-pr` for **every** intended PR. Use `--include-commit <40-character-sha>` for reviewed non-PR commits. Repeat `--acknowledge-overlapping-pr` and `--acknowledge-dirty-worktree` for every separately investigated overlap. The preview identifies their exact numbers/paths; there is no `--include-everything` shortcut.

## Fail-closed conditions

- Exact candidate is not latest protected main, or does not descend from installed production.
- Scope review incomplete, newly changed, or hash does not match the recorded candidate/baseline.
- Required CI, authority, material change review, preproduction, provider reads or rollback image unavailable.
- Unacknowledged merged commit, overlapping open PR, changed developer worktree or incomplete GitHub PR pagination.
- Release freeze still active, circuit breaker open, drift present, root controller mismatch, storage insufficient or transaction already running.

**Known design limitation:** This is a safe manually *selected release batch*, not yet a selective-release-branch/cherry-pick deployment facility. A standalone hotfix can ship alone only when protected main's baseline-to-candidate inventory contains only that fix (and its reviewed dependencies). Developing a separate signed hotfix-source lane must be a distinct governance decision, not a workaround that disables the current main ancestry safeguard.

## Signed Teams one-transaction freeze exception

A production recovery may itself require code that cannot be activated while the global Owner deployment freeze is active. The bootstrap remains fail-closed: a source merge, ordinary exact-SHA release approval, chat instruction, shell command, GitHub comment, or direct marker edit is **not** a freeze exception.

For the bounded provider-identity/authority recovery, protected source may contain `config/production-deployment-freeze-exception.json`. That declaration is incident-specific and short-lived. It binds the exact rollback SHA, reviewed recovery-profile ID, automatic freeze restoration, no standing authority, and a human-readable purpose beginning `ONE-TIME PRODUCTION FREEZE EXCEPTION`. The exact declaration and its digest are copied into the immutable release record/manifest, so the existing signed Teams release card binds the exception intent through both the manifest fingerprint and purpose hash.

The exception is eligible only when the release is still `production_eligible`, protected main is the exact candidate, the complete manual scope digest is current, fresh drift matches the declared open-breaker recovery profile exactly, rollback/LKG alignment passes, and `owner_approval.source` is an authenticated signed Teams release approval for that exact candidate. The production transaction lock is acquired before any freeze state is changed.

Under the lock, Release Manager verifies the active 0600 freeze marker against the private exact backup, writes a durable per-release receipt, removes the marker only for that transaction, and runs the normal native recovery deployment. Ordinary retention, CCC, rollback, provider canaries, host reconciliation, drift and postflight gates are unchanged. The identical freeze bytes, ownership mode and SHA-256 are restored in `finally` before the production lock is released on success or rollback. The receipt records `standing_authority=false` and grants no additional provider or endpoint authority.

If the process terminates while the marker is absent, the next release transaction must first restore the freeze from the exact backup and stop, requiring a fresh retry. Multiple or mismatched unfinished receipts fail closed. The declaration expires and is bound to the incident rollback; it is not reusable for later releases.
