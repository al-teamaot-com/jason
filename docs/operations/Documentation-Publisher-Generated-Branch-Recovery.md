# Generated documentation branch recovery

The existing publisher reuses one generated branch and opens a reviewed documentation PR. Rewriting that branch is expected; its local remote-tracking ref must accept the exact branch update. Protected main is fetched normally.

When no documentation PR is open, the publisher checks the branch's own changes against its merge base with main. Later accepted main changes are not pending branch changes. A branch containing unrelated changes still denies publication. Existing revision ancestry checks and compare-and-swap pushes remain required.

Existing worktrees must be clean before reuse. Dirty or unregistered worktrees stop publication and preserve their contents. The reconciler exposes only fixed publisher gate codes, while arbitrary provider diagnostics remain private.

Disposable Git tests cover rewritten tracking refs, later main changes, an already-merged generated branch, rejection of foreign changes, and preservation of local work. They exercise the normal publisher through a synthetic remote and command adapter; they do not contact GitHub or change production.

Deployment remains separate from source acceptance. The scheduled service must execute the reviewed publisher before the operational repair is complete. Generated source validation state must remain distinct from actual production deployment state.
