# Generated documentation branch recovery

The existing publisher reuses one generated branch and opens a reviewed documentation PR. Rewriting that branch is expected; its local remote-tracking ref must accept the exact branch update. Protected main is fetched normally.

When no documentation PR is open, the publisher checks the branch's own changes against its merge base with main. Later accepted main changes are not pending branch changes. A branch containing unrelated changes still denies publication. Existing revision ancestry checks and compare-and-swap pushes remain required.

Existing worktrees must be clean before reuse. Dirty or unregistered worktrees stop publication and preserve their contents. The reconciler exposes only fixed publisher gate codes, while arbitrary provider diagnostics remain private.

Disposable Git tests cover rewritten tracking refs, later main changes, an already-merged generated branch, rejection of foreign changes, and preservation of local work. They exercise the normal publisher through a synthetic remote and command adapter; they do not contact GitHub or change production.

Deployment remains separate from source acceptance. The scheduled service must execute the reviewed publisher before the operational repair is complete. Generated source validation state must remain distinct from actual production deployment state.

The regression suite belongs to the documentation CI job. Separate proposed additions for Owner-plan and sparse-source tests belong to the runtime job and must be reconciled independently; this repair does not replace those tests or authorize their release.

The exact deployment helper reuses the reviewed Owner verifier, protected-source CI attestor and production host locks. Its full root preflight runs before the Owner decision. It installs only immutable copies of the existing publisher scripts and a service override, then starts the existing documentation service. Actual generated-source readback, live drift and unchanged protected services are required before acceptance. Partial installation restores only its own exact override and retains private approval evidence; a consumed attempt is not silently replayed.

The publisher supplies GitHub authentication through the coordinator's existing environment input, avoiding credentials in process arguments. An already-open generated PR must be reconciled before the one-use service installation starts, so waiting on an older PR is not mistaken for acceptance of the new source.
