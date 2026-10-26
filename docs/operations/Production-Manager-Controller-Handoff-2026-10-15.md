# Production Manager Controller Self-Update — N to N+1

Status: source repair and regression tests; NOT a declaration of production acceptance.

## Observed root cause (issue #1102)

On October 14, 2026, governed release `release-514edda3eff4f53e` passed immutable preproduction and host reconciliation, including all ten exporter socket checks. The running controller was still the immutable N code from revision `2087dd3898b17638659c8f975006290e4f2951c2`, while the host installed candidate N+1 from revision `514edda3eff4f53e2f7eed784a3bfe27603e3ae5`. The post-install `verify_controller_identity(...,installed_candidate=True)` compared the *executing old controller's* digest to candidate source bytes and raised `installed Production Manager controller differs from candidate source`. Runtime and MCP were restored to N, but root host rollback verification failed and the circuit breaker opened. This is not a QuickBooks provider failure.

## Repair

During one serialized production transaction, the controller must preserve these distinct identities:

- **Executing controller N:** pin the immutable release source, parent revision and digest before mutation. For a manually launched release, this is the canonical `/opt/jason/releases/<SHA>/tools` source. For the user systemd timer, `CONTROLLER_SOURCE` is an installed **copy** which is allowed to be replaced during handoff: the executing N must instead be pinned via the pre-mutation `~/.local/lib/jason/release-manager-source` symlink to its immutable host release, with byte-for-byte comparison of the installed copy at entry. After N+1 is installed, validate the pinned old immutable source rather than re-reading the legitimately replaced installed copy.
- **Candidate controller N+1:** digest of `tools/release_manager_host_runner.py` from the exact materialized source, pinned with the transaction before mutation. Candidate source changes fail closed.
- **Installed controller N+1:** `~/.local/lib/jason/release_manager_host_runner.py` after the existing governed installer has independently required `/opt/jason/current` and `release-manager-source` to match the candidate SHA and checked installed file bytes against its immutable host copy. Verify installed digest equals pinned candidate digest; never assume running Python has loaded N+1.
- **Policy:** candidate release-manager policy digest remains pinned; changes during the transaction fail closed.

The exclusive existing production transaction `flock` stays held through live Runtime/MCP validation, host reconciliation, controller installer, CCC, smoke tests, drift verification, rollback readiness, closeout, and last-known-good publication. The installed N+1 becomes the effective controller only at the next invocation, after the current transaction has released the lock. Log both running and installed controller digests and the `staged_for_next_transaction` handoff marker in the durable production closeout.

No ungoverned process spawning, direct provider access, writable control-state replacement, disabled health check, or changed approval policy is introduced.

## Bootstrap requirement for installed legacy N

**Important:** merging this code does not alter the already-running old N controller, nor does it retroactively change its byte comparison. The original installed N cannot self-host this repair by attempting another ordinary candidate rollout. A one-time bootstrap is necessary *unless* the installed controller has been independently upgraded through an already-authorized versioned handoff.

For bootstrap, use an **explicitly Owner-approved and audited** narrowly scoped release-control restoration operation under the existing protected/root-governed authority. Validate before execution: protected exact source SHA, CI evidence, candidate-controller digest and installer digest, no concurrent release transaction, last-known-good production manifest, and rollback copy of the original installed controller and unit configuration. Install only the reviewed controller entrypoint via the canonical installer (no alternate production deployment path); verify installed digest/source link/timer and fresh root/drift/CCC readback. A failed preflight must not mutate anything. On failed install, use the protected rollback procedure and record evidence. Do not edit the root control state or close a historical failed release by hand. Never treat generic chat consent or an old exact-SHA CCC review as automatic authority for break-glass.

Once N+1 is installed and independently healthy, prepare a **new SHA** for Stage 1, require exact source review as the approval policy demands, perform immutable preproduction and complete post-deployment CCC/rollback/host verification. Keep `quickbooks-sandbox-read-v1` until Stage 1 is actually closed. Only then handle the draft QuickBooks Production-read profile separately.

## Regression acceptance

Tests exercise old executing bytes != new candidate bytes; matching installed N+1 succeeds, old executing identity remains N, tampered pinned immutable source, tampered candidate, altered installed bytes, changed policy and missing installer artifact all fail closed. The actual user-systemd copied runner path is tested independently: N's pinned immutable bytes survive replacement of the installed copy and release source symlink, while a fresh subsequent invocation selects N+1; a mismatching installed copy at transaction entry fails closed. All mandatory runtime, host, rollback and security tests must run on the protected branch and main merge.


## Concurrent release-control change (#1112)

PR #1112 modifies the host rollback reconcile worker and release-specific
scheduled-control checks, whereas this patch changes the executing-versus-
installed controller identity verification. Both touch the Release Manager
source/tests, but their functions and safety assertions are independent. The
integration owner must preserve #1112's historical rollback timer contract
and this patch's immutable N / staged N+1 digest contract if both are merged.
Re-run the combined protected tests on the final merged SHA before any
controlled bootstrap or production promotion.
