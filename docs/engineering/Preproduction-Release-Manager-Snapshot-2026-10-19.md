# Bounded preproduction state: preserve authority, exclude recursive scratch

## Observed failure

On 2026-10-19, the governed Release Manager prepared exact candidate
73d4123e92966f84fb32cf98dd2f09894e73ef07, containing the protected
P0 source-read and release-loop fixes. Isolated preproduction then stopped
before any production mutation with:

  ReleaseManagerError: isolated preproduction state exceeded bounded disk capacity

The source controller correctly limited each new clone of production
/var/lib/jason/openclaw to 4 GiB, preserving a further 3 GiB free reserve.
It already omitted the >16 GiB top-level append-only orchestration event
journal. But it recursively copied Release Manager's OWN nested
preprod and worktrees directories into each new isolated clone.
Live read-only inspection showed around 857 MiB of historical nested
preprod artifacts and about 712 MiB of source/build worktree caches; repeated
archives may contain duplicate/hardlinked files that Docker cp expands.

## Narrow source correction

When cloning ONLY the top-level release-manager directory, enumerate its
direct children from the existing production Docker container with the same
bounded name/traversal validation used for all other OpenClaw entries.
Require the exact critical names records, protected-readback and
production-control-state.json to exist. Copy every child EXCEPT the two
reconstructable directories preprod and worktrees.

This preserves production release records, root-protected evidence copies,
identity-bound owner approvals, receipts, host-reconcile metadata, runtime
authority databases, WAL transaction logs, support repair state and every
other OpenClaw top-level source. It does not delete the live caches; it
does not replace protected state with empty files or copy from the mutable
developer checkout.

The original 4 GiB maximum copy size, 3 GiB disk reserve, Docker-only
production-state source, separate writable isolated volume, no production
provider mutation, no weakening of CCC/owner approval and cleanup-on-failure
remain mandatory. Each nested child copy is measured against the SAME
cumulative upper bound and reserve.

## Verification and acceptance

Unit tests verify the exact required copied children, rejection on missing
protected state or unsafe paths, failure for exceeded disk budget, and
absence of both reconstructable cache paths in the clone. Existing
release-manager, rollback, CCC and production-governance tests remain
mandatory.

A source PR or isolated test is not release acceptance. After protected
CI and the appropriate exact-owner release review, the native Release
Manager must reprepare the current protected candidate, perform real
isolated preproduction and prove complete fresh smoke tests, rollback
readiness and no inherited writable production mounts before eligibility.
Only then may independently authorized production promotion occur.

Related release/engineering incidents: #1304, #1517, #1526, #1609, #1611.
