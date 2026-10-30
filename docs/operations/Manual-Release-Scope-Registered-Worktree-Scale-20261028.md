# 2026-10-28 manual release scope: registered worktree scale and helper install

**P0 source correction only. Production remains frozen.**

The previous owner-approved exact-SHA promotion was blocked safely by the
Production Manager before any production deployment. The native
`review-impact` demanded an exhaustive full-release and overlapping-work
review. Its 600-registered-worktree hard limit rejected the actual
1,020 Git worktrees. The repository contains 26 stale missing worktree
registrations, and 994 present worktrees (before creation of the isolated
P0 fix worktree). Deleting active worktrees to satisfy the limit would
risk interrupting other engineering work.

The reviewer now accepts up to **2,000** registered worktrees and still
iterates **every** one with a targeted, read-only `git status` over
changed release paths. Missing worktrees without Git's exact authoritative stale/prunable
mark, status failures, unacknowledged
dirty overlaps, unacknowledged open PR overlaps, unknown commits,
truncated PR inventories and registrations beyond 2,000 all fail closed.
Regression tests include 1,020 worktrees with the *last* directory
dirty, proving no entries are skipped, and a 2,001-worktree rejection.

The approved controller-only bootstrap also exposed a packaging defect:
the installed Release Manager imports
`tools/production_read_canary_gate.py`, but the normal
`tools/install_release_manager.py` omitted that helper. The installer
now copies the exact source-reviewed gate alongside the Release Manager
entrypoint, so later installations cannot silently lose live-read
acceptance.

**Do not use fake/smaller Git worktree registries or silently omit
unfinished work.** For truly orphaned registrations, the reviewer now
accepts only the exact native Git porcelain marker
`prunable gitdir file points to non-existent location` AND a physically
absent directory; those are included in the release-scope digest and
reported separately. Every existing registered directory, even one at
the end of a 1,000+ entry inventory, still receives a targeted
`git status`. Missing or ambiguous entries without that marker fail
closed. No Git worktree deletion, checkout, source tree mutation,
branch pruning or registry cleanup is required.

Because this fix changes protected main, it requires a **new exact
SHA**, fresh immutable preproduction and a separate Owner authorization
for any production promotion. The old 4822366b approval does not
transfer to a new revision.
