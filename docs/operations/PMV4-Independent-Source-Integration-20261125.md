# Governed independent source integration — November 25, 2026

The Owner approved correcting the legacy integration policy, not a blanket
production deployment. Native engineering acceptance of the predecessor
lock-retry release completed two distinct normal cycles. The legacy queue
still inferred a release lock from main != verified production, even with
the actual production mutex free, native drift passing and breaker closed.
Deploying the accumulated source changes merely to advance engineering is
not an acceptable recovery.

The existing integration queue now distinguishes undeployed source backlog
from a real production transaction. It archives the old advisory queue
lock, preserves verified production identity, continues the existing
Owner-admitted bounded non-overlapping trains, and keeps the native
release manager and all approval records untouched. The installed source
reconciliation uses an exclusive queue lease and acquires a shared lease
on the original production mutex only for final mutation; missing, replaced, unsafe or busy locks,
unknown LKG and Owner pause deny mutations. All required protected checks,
strict main reconciliation and fresh open-PR overlap review remain required.
Refresh exact PR state, draft, head, files, admission, current main and LKG
immediately before a branch update or merge. Checkpoint a successful merge
before fallible advisory GitHub status writes. The existing overlap
validator is reused through the authenticated GitHub REST client, without
printing or extracting a token. No branch protection is changed.

Independent source progress does not authorize promotion. A prepared
native release must still satisfy its original exact-source and scope
rules; a newly advanced main may require fresh release review. Never
silently change a candidate, reuse a stale approval, mark source as LKG,
remove the freeze/hold, or use an alternate production lane.

The existing native PipelineSuccessor transaction binds precisely these
two replacement workers, exact protected source, reviewed predecessor and
two-cycle operational acceptance. It must verify the completed predecessor
receipt including bounded retry. The same authenticated exact-action
Owner approval, peer/health checks, before-images and rollback apply.
Acceptance requires two real scheduled cycles observing the independent
policy and preserved source backlog, plus the existing native guard,
quarantine and dependency evidence. Restoring the previous worker/pause
does not revert already authorized source merges. A source merge may
happen during normal acceptance; no production or provider write is
authorized. This PR is source-only until exact activation is approved,
installed and verified. Do not merge around the existing legacy lock:
use only its existing explicitly admitted bounded release-recovery path.
