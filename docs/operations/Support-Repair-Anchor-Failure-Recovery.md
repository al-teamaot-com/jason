# Governed SUPPORT exact-anchor recovery

This is a bounded continuation of the existing Project Jason SUPPORT repair
worker, not a second engineering queue and not an authorization shortcut.

## Trigger and scope

The host worker may encounter a successful edit_plan whose later exact-text
anchor is absent or ambiguous. Previous worker revisions applied earlier edits
before rejecting that later anchor; the resulting isolated worktree can contain
an incomplete proposal. The all-or-nothing validation fix (#1589) prevents new
partial writes, but cannot retroactively undo legacy partial edits.

The worker may readmit a currently eligible open SUPPORT item from a legacy
blocked exact-anchor failure only when:

- Its recorded failure matches the exact-anchor validator error and it has an
  existing, matching successful edit_plan response with the same item identity
  and content-addressed request ID.
- The original branch and worktree are the canonical per-item SUPPORT branch.
  The worktree is not a symlink and has only tracked, unstaged modifications
  contained within the original model proposal. No untracked or staged files
  are accepted.
- Deterministic, in-memory replay from the original HEAD proves the modified
  bytes are exactly the original proposal's prefix before the first failed
  anchor. A technician's unrecognized edit, a mismatched response, or unknown
  files stop readmission.
- Existing worker capacity and the two-proposal-retry limit are respected. No
  open-issue, authority, J-CHANGE-002, or release gate is relaxed.

## Evidence and continuation

The original worktree and branch are never stashed, reset, deleted, or changed.
The worker writes a private, durable, content-addressed evidence document
under /var/lib/jason/openclaw/support-repair/recovery-evidence/ containing
the failed request identity, original commit, changed paths, patch bytes and
patch digest. A differing existing evidence record fails closed.

A separate repair/<item>-anchor-<request-prefix> branch and worktree are
created from current origin/main. Only a clean, aligned new worktree is
eligible for reentry. A new content-addressed edit_plan is queued with the
exact host-validation error and fresh policy-eligible source excerpts.
Readmission is recorded once; repeat worker cycles do not resubmit it.

Existing patch/test/CI, GitHub integration review, Release Manager, CCC,
exact-SHA owner approval, production verification, and support-closure
requirements remain unchanged. A successful reasoning reply or queued request
never constitutes acceptance or approval.

## Operator checks

1. Read support-repair/state.json: verify the item points to the new
   -anchor- branch, contains anchor_preserved_recovery_id, and has a bounded
   proposal_retries count.
2. Verify recovery-evidence/<original-request-id>.json exists and the old
   worktree is unmodified, retaining its historical patch.
3. Verify the replacement worktree is clean and pinned to a known GitHub
   revision, and the new reasoning request is bound to the same SUPPORT item.
4. Follow the ordinary worker until it produces a valid regression-tested PR.
   Reject any change that treats SUPPORT-DEV-* as independently
   owner-approved DEV-* work.
5. Accept completion only after protected CI, governed release, runtime/MCP/host
   alignment, independent detector acceptance, and audited issue closure.

Failure: Missing or changed evidence, a dirty replacement worktree,
unexpected branch identity, exhausted retry budget, provider/authority change,
or a failed regression test requires normal governed support escalation.
Do not manually reset the preserved branch or override approval gates.
