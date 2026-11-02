# P0: Native release self-invalidating scope review — 2026-10-28

## Verified production release blocker

An exact-SHA owner-approved release of the Autotask dynamic schema reader
(`3e326ba71d01749538c3bde3498488498b61e889`) passed native
preproduction, an independently reviewed manual scope, and initial CCC
pre-mutation checks. Production remained on the healthy v10 revision
`8559cbb84aba2d9acb636ac57fbdab9f00dbda78`.

The native release command did **not** deploy. It failed at the final
`require_current_manual_scope_review()` guard with
`manual release scope changed: repeat review of merged and unfinished work`.

The reviewer computes its SHA-256 scope fingerprint over exact source
history, changed files, open PR overlaps, dirty worktree overlaps, verified
stale registrations **and total registered worktree count**. The native
release manager materializes a fresh detached worktree under
`/var/lib/jason/openclaw/release-manager/worktrees/{candidateSHA}-{12hex}`
**after** the owner records that fingerprint and **before** the final review.
Thus the release's own worktree increments the count, invalidating the
review and blocking the release before any production change. Re-approving
the same work repeatedly cannot solve this deterministic issue.

## Source-bound, narrowly scoped resolution

The manual reviewer now recognizes ONLY an exact-candidate native worktree
under the canonical private release-manager root with an exact
40-character SHA plus 12 lowercase-hex run identity. It independently
requires:

- Git's registration to identify the **same detached candidate SHA**;
- a real directory owned by the executing identity, with no path symlinks;
- `git rev-parse HEAD` matching the reviewed candidate SHA;
- a completely clean `git status --porcelain=v1 --untracked-files=all`,
  including files outside the release's changed-file list;
- if missing, Git's **specific verified prunable registration** and no
  conflicting lock, branch or untrusted metadata.

Only these pristine internally generated checkouts are normalized out of
the **digest-bearing registered worktree count**. All raw registrations
remain bounded by the existing 2,000-worktree ceiling. All unrelated
developer worktrees, dirty changes and PR overlaps remain inspected and
counted. Any malformed native checkout **fails closed** instead of being
silently exempted. The reviewer does not modify checkout contents, prune
registrations, create synthetic approval, or bypass production controls.

The isolated source test suite proves the unchanged scope SHA with a new
clean native worktree, a verified stale candidate registration, rejection
of dirty/untracked native content and wrong revisions, and continued
detection of an unrelated clean developer worktree.

## Deployment contract

This is a new source SHA; prior exact-SHA approvals are not automatically
transferable. Follow protected GitHub CI, native isolated preproduction,
fresh full concurrent-work review, owner exact-SHA authority, CCC
material review, matching source-bound v13 controller/read canary and
**a new one-time supervised production exception with rollback**.

Final acceptance must include one real Microsoft-connected AOT requester
completing an Autotask ticket count, first 50 plus cursor continuation,
exact ticket readback, Projects read and v13 ActionTypes read. Failures
restore the old v10 production revision.

No production application, Autotask records, developer checkouts or
root-governed freeze state were modified by this source correction.
