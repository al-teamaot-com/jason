# Jason: verified recovery of invalid exact source selectors

## Evidence and objective

On October 19, 2026, the deployed native worker resumed P0
SUPPORT-OPS-054 after a verified rollback-interrupted reasoning request,
but its model reply mixed two real function names with descriptive prose
inside a read_source query. The old strict selector correctly raised
EvidenceToolError: invalid exact source symbol. The worker persisted a
terminal block instead of continuing its already-approved, read-only
source-evidence turn. The engineering supervisor reported degraded,
zero active, seven approved outstanding.

The actual source request selected the authorized tracked
tools/support_repair_host_worker.py and began with the exact function
names support_id_from_title and sync_support_lifecycle_notification.
There were no requested edits, provider calls, authorization changes,
deployments, or commands. Original request and response identities are
preserved by the spool; the affected branch is pinned at the deployed
source revision ae39bc1d579bf6a07aca031a3a97f317f60a169c.

## Fail-closed source selector

A read_source tool request still requires a tracked, non-symlink source
file inside a clean governed worktree, with normal path policies and
all-batch validation before any read.

A query may be null, a single exact function identifier, or start with
two comma-separated syntactically valid identifiers. In the two-symbol
form, the tool discards a bounded plain-language remainder and checks
that BOTH symbols occur as actual def, async def or class declarations
in the SAME authorized tracked source file. Only the two validated
identifiers are passed to the existing bounded symbol-excerpt routine.
Model strings are never used as shell, path expansion, line expressions,
arbitrary source selectors or provider actions. Control chars, paths,
shell metacharacters, unbounded text, duplicate names and missing
symbol definitions are rejected. Exact single-identifier requests
retain their original semantics. The model prompt separately instructs
using one exact identifier (or null) per read_source request.

## One-time repair of the previously blocked P0

New native recovery is eligible only when all these conditions hold:

- The work is approved canonical P0; the persisted reason is exactly the
  known malformed-selector failure; protected intake and authority holds
  are absent and an existing repair marker or PR is not present.
- The current record is pinned to a prior verified rollback-interrupted
  source request, with exact 64-hex original/request IDs and branch name,
  clean worktree and exact historical source revision.
- The existing request content hash and completed successful response
  match the support ID, edit_plan kind, read-only evidence shape and
  prior rollback-interruption metadata.
- The exact Git source blob of the governed evidence executor has
  changed at authoritative main; the new branch is clean, pinned to
  that same protected main, with available engineering capacity.
- The repaired executor itself validates and runs the original bounded
  read-only requests. Existing evidence turns are not reset: the new
  request consumes the next allowed turn. Prior excerpts are reread
  from tracked current source; new source receipts are content hashed.

On successful readmission, the native worker records one immutable
symbol-read recovery ID, the original request ID, exact source revision
and compatible -context- worktree; it does not edit the original response,
touch protected production, forge an approval, replay a patch or bypass
CI/release governance. Dirty worktrees, invalid or tampered response,
unauthorized tools, stale source, prior recovery, exhausted budget,
competing capacity and invalid symbol syntax fail closed.

Acceptance remains actual SUPPORT-OPS-054 code/test implementation or
a genuine evidence-backed escalation, followed by protected PR checks,
explicit exact-revision release approval where required, independent CCC
and production acceptance. A status of implementing is not closure.

## Active pull-request integration review

Reviewed October 19, 2026 against protected main after PR #1609:
PR #1599 changes acceptance of legacy development model request kinds,
PR #1495 changes transport-error classification, and PR #1434 changes
stale self-heal incident re-admission. All are separate functions/regions
from the bounded exact-symbol parser and its immutable rollback-provenance
recovery. PR #1331 contains a separate model fallback proposal, while
the much older draft #692 touches general finance reconciliation and the
same shared worker/model files without being authoritative main.

No unrelated PR is automatically adopted, closed, deployed or treated as
accepted by this repair. Every overlapping pull request must rebase to
protected main, verify its precise net diff and rerun all required checks.
The protected change-integration evidence explicitly coordinates #692,
#1331, #1434, #1495 and #1599; mere file overlap is not permission to
relax existing authorization, test or release boundaries.
