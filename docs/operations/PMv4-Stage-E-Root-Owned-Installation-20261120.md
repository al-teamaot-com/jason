# Stage E root-owned installation boundary and pre-approval filesystem gate

Status: source-only correction. Stage E production acceptance remains pending.

## Observed live failure

The approved 296be969 candidate passed the earlier root prerequisite checks,
began signed inert bootstrap, and reached trust staging. The installer denied
PMV4_E_ROOT_TRUST_ROOT_TARGET_PARENT_MUTABLE and completed signed inert cleanup.
The native six-unit ledger never began and legacy triggers remained active.

Actual metadata:
- /opt/jason: UID 997, GID 984, mode 0750.
- /opt/jason/releases: root:root, mode 0755.
- /var/lib/jason: UID/GID 1000, mode 0750.
- /usr/local/lib/jason/pmv4-e-bootstrap: root:root, mode 0755.
- Every ancestor of that bootstrap directory: root:root, no group/other write.

The old trust destination required its parent to be root-controlled. Its
immutable source reader also checked every ancestor. Both the old destination
and source under /opt/jason conflict with that actual layout. Changing only
one location would leave a second failure later in the same attempt.

## Corrected installation

Stage E native code goes to
/usr/local/lib/jason/pmv4-e-bootstrap/native.

Its immutable control source goes to
/usr/local/lib/jason/pmv4-e-bootstrap/releases/EXACT_SHA.

The original root bootstrap namespace, signed issuer, generic component
controller, runtime/MCP releases and runtime source links retain their existing
boundaries. This release neither changes /opt/jason ownership nor relaxes
root-directory ancestry checks. Accepted Stage E watchdog and Release Manager
readback distinguish the immutable control source from the runtime baseline.

The initial source installer verifies the exact existing 296be969 installation
tuple, root-owned installation scope record and original signed bootstrap
proof at its historical journal time. This is before-image evidence only:
it cannot grant another release or reuse that consumed approval. A new
exact source/scope still requires its own live independently verified Owner
decision. Old receipts and signatures remain intact.

After that decision, the installer creates only the explicitly scoped missing
release parent and three rollback/audit directories with exact root identities
and modes. It records creation intent before each directory and removes only
its own still-empty directories if source preparation fails.

## Complete installation preflight

The read-only gate runs before the Owner prompt and again under the native
host/freeze boundary before signed bootstrap consumption. It verifies:
- Root-controlled ancestry of both new code and immutable-source locations.
- Actual checked-out revision, clean worktree and every reviewed source byte.
- Existing watchdog, runner, desired policy, shared worker and catalog pin.
- Original generic native module bytes and ownership.
- User/system unit directories and absence of all twelve new unit files.
- Rollback journal parents and public marker directory.
- Existing C/D/A1 evidence, canary, six old/new states, monitoring, unique ticket
  ownership, fresh provider-backed scans, freeze, breaker and protected CI.

A separate preflight-only launcher is required for real-host readback before
the next release approval is requested. The apply mode repeats the same gate.

## Disposable root filesystem verification

The UID0 CI test refuses any host with existing Jason directories. It creates
the actual canonical paths in a disposable runner, including the service-owned
/opt/jason and user-owned /var/lib/jason metadata observed on Jason.

Production=True source staging, trust copying, signed bootstrap, canonical
native imports, manifest attestation, code/policy apply and exact restore,
twelve unit-file staging/removal, and inert cleanup/replay denial use actual
Linux file ownership and permissions. Synthetic signing keys are confined to
the runner. External CI facts and timer observations are explicit synthetic
callbacks. No live Owner, provider, Docker or systemd mutation is represented
as tested production acceptance.

Separate existing native-controller tests continue to verify the seven
six-unit phases and rollback/recovery behavior. Actual cutover and subsequent
independent operational verification remain required.
