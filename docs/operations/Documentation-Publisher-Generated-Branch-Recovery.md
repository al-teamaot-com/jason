# Generated documentation branch recovery

The existing publisher reuses one generated branch and opens a reviewed documentation PR. Rewriting that branch is expected; its local remote-tracking ref must accept the exact branch update. Protected main is fetched normally.

When no documentation PR is open, the publisher checks the branch's own changes against its merge base with main. Later accepted main changes are not pending branch changes. A branch containing unrelated changes still denies publication. Existing revision ancestry checks and compare-and-swap pushes remain required.

Existing worktrees must be clean before reuse. Dirty or unregistered worktrees stop publication and preserve their contents. The reconciler exposes only fixed publisher gate codes, while arbitrary provider diagnostics remain private.

Disposable Git tests cover rewritten tracking refs, later main changes, an already-merged generated branch, rejection of foreign changes, and preservation of local work. They exercise the normal publisher through a synthetic remote and command adapter; they do not contact GitHub or change production.

Deployment remains separate from source acceptance. The scheduled service must execute the reviewed publisher before the operational repair is complete. Generated source validation state must remain distinct from actual production deployment state.

The regression suite belongs to the documentation CI job. Separate proposed additions for Owner-plan and sparse-source tests belong to the runtime job and must be reconciled independently; this repair does not replace those tests or authorize their release.

The exact deployment helper reuses the reviewed Owner verifier, protected-source CI attestor and production host locks. Its full root preflight runs before the Owner decision. It installs only immutable copies of the existing publisher scripts and a service override, then starts the existing documentation service. Actual generated-source readback, live drift and unchanged protected services are required before acceptance. Partial installation restores only its own exact override and retains private approval evidence; a consumed attempt is not silently replayed.

The publisher supplies GitHub authentication through the coordinator's existing environment input, avoiding credentials in process arguments. An already-open generated PR must be reconciled before the one-use service installation starts, so waiting on an older PR is not mistaken for acceptance of the new source.

## Failed installation readback continuation

A failed verification may leave the approved publisher code installed while restoring the original service configuration. Preserve its private approval and failed-attempt records. Repair Git data only after verifying its owning repository; preserve a foreign worktree through that repository rather than deleting its files or forcing removal.

The separate readback continuation does not replay the installer. It requires the original root-owned approval, exact scope digest, unchanged approved publisher bytes and override, a trusted original Owner, a decision within two hours, the recorded restored failure phase, and no prior recovery attempt or acceptance. It rechecks protected source CI, production gates, protected service identities and repaired worktree ownership under the existing locks before writing one exclusive recovery record.

Only the original override is restored and the existing documentation job started. Successful generated-source readback, clean production drift and unchanged protections are required for acceptance. A failed job restores that exact override and retains both original evidence and the consumed recovery record. No signing operation, new provider authority, nonce reset or code replacement is available through this continuation. Root execution remains required.

## Fresh exact Owner decision after the bounded recovery window

The November 20 failed installation left the immutable approved publisher payload intact and the original service override restored. Its two-hour continuation window has expired. The prior receipt is historical evidence only, never a current grant. `tools/documentation_publisher_successor.py` reuses the exact sealed payload, reviewed native Owner verifier, original override implementation, protected-main CI attestor, and current post-Stage-C production health checks. It requires a fresh exact candidate-bound Owner decision. The new receipt resides in a unique successor directory; prior approval and failure records are not rewritten. Before approval it checks clean registered worktree ownership, the existing generated branch's accepted ancestry, and absence of pending generated PRs and foreign service overrides. Only the original exact override is installed; no runtime, provider, scheduler, freeze, or engineering-pause change is permitted. Successful acceptance requires a new service invocation, exact generated revision and remote branch readback, unchanged protected production evidence, and verified override bytes. On failure the original override is removed using the existing rollback implementation; generated Git evidence and prior receipts remain intact.
