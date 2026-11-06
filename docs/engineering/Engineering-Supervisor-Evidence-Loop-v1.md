# Project Jason: governed engineering supervisor and source-evidence loop v1

## Goal and non-goals

Move approved engineering beyond a one-shot code-excerpt response while
retaining Project Jason governance. This first vertical slice adds two
read-only source tools that a reasoning result can request, and a durable
supervisor projection to distinguish internal recoveries from external holds.

This is not arbitrary remote shell access for the AI model. The reasoning
worker cannot independently run commands, access credentials, call providers,
approve production, merge protected pull requests or deploy anything.
The host remains the deterministic authority over discovery and patch validation.

## Architecture

1. Existing approved GitHub/Autotask admission remains authoritative. Native
   Support Repair and Owner-approved Development workers own job state.
2. For an edit_plan, the model returns either exact edits and regression tests,
   a genuine blocked_reason, or a read-only evidence_requests array with
   search_source or read_source; these modes are mutually exclusive.
3. The host verifies tracked repository source, J-CHANGE-002 path gate,
   symlink/containment boundary, clean worktree and original request identity.
   It refuses arbitrary model commands, provider calls, untracked/ignored files,
   secret/authority paths and invalid or oversized tool requests.
4. Authorized excerpts are reread from the pinned worktree, prioritized over
   stale previous context and returned as a new content-addressed model
   request. Prior evidence and worker retry budgets remain immutable, with
   source revisions and non-secret SHA receipts recorded.
5. The item remains implementing and consumes existing capacity. Two additional
   evidence turns are allowed by versioned configuration; exhausted, invalid or
   denied tools become explicit blocked states, never implicit authorization.
6. The independent Engineering Supervisor summarizes existing support,
   development and approved TODO states after each pipeline cycle. Its file
   engineering-supervisor-state.json records category, accountable action,
   source progress fingerprint and unchanged cycles (0600, atomic). It
   neither changes admission status nor grants any release rights.

The existing 24/7 pipeline still reconciles release state independently if
other stages fail. The supervisor stage also runs when a prior worker fails.
A healthy systemd invocation is not synonymous with approved-work progress.

## Configurable settings

config/engineering-supervisor-policy.json, read from fetched origin/main,
controls enablement, tool kinds and upper-bounded limits. The policy cannot
enable shell, provider, or deployment tools; only two fixed read-only source
operations exist. Never trust an unreviewed dirty local policy checkout.

## Deterministic acceptance tests

- New model requests missing source, host reads relevant code and test, then
  queues a distinct follow-up; exact patch/test still pass normal validation.
- Two evidence requests are possible; a third is rejected.
- Mixed edits and requests, denied source, symlinks, ignored/untracked files,
  dirty worktree, stale/mismatched request, unsupported tool, corrupt policy
  and absent source fail closed without mutation.
- Supervisor differentiates internal source/transport errors from credential,
  dependency and approval gates; no-progress resets only on a real change.
- No work is considered production-complete before exact-SHA Owner/CCC
  release, rollback readback and real production acceptance.

## Next integration milestones

This is a working first phase, not the full autonomous coding-agent replacement.
Follow-on governed work must add clean-worktree refresh for legacy blocked tasks,
native worker-triggered readmission with authoritative proof, bounded iterative
test-feedback tools, Teams escalations only for human-actionable holds, and a
production acceptance run on a real P0 item. Do not enable arbitrary process
execution in the reasoning service or bypass the release manager.

## October 19 explicit-read starvation incident and controlled recovery

The first live P0 exercise showed that source discovery still could become
unproductive: SUPPORT-OPS-054 explicitly requested
tools/support_repair_host_worker.py, but two broad source searches consumed
the response capacity first. The requested file was missing from the next
reasoning context. Later searches occupied additional turns and the worker
exhausted its two-turn evidence budget. The generic supervisor correctly
detected the resulting stall but could not itself reopen authority.

The corrected evidence executor now validates the whole batch of requests
before any read, then prioritizes authorized read_source requests in their
original relative order, limiting each broad search to two matching files.
Exact file reads may include a bounded Python function-name query to select a
relevant excerpt without returning entire modules or executing model text.
Every path remains tracked, within the isolated worktree and J-CHANGE-002
path gate; denied or unknown tools fail closed.

The cumulative per-item evidence budget is raised from two to four turns,
without clearing history. A separate P0-only recovery may queue ONE fresh
edit-plan when the original content-addressed request chain proves an exact
read was starved, the previous host code blob differs from fetched main, a
new clean worktree exists at that exact revision, and the missing source and
test files pass the host path gate. It preserves old request/response data,
the original exhausted-turn counter, existing owner/governed handoffs, the
two-active-repair cap and exact-SHA deployment gates. It never blindly replays
an old request, increases authority, or marks a job resolved without proof.

A second evidence starvation cannot invoke this recovery again. Unverified
or out-of-scope jobs remain blocked with a distinct next action for review.
Live acceptance requires recording SUPPORT-OPS-054 as actively diagnosing or
implementing on the corrected worker revision, then observing a code/test PR,
verified existing repair, or explicit evidence-backed terminal disposition.
