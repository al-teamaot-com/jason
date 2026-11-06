# P0 runtime image import failure: restrictive Git release checkout

**Related:** #1078, #1440, #1055, #1437. Date: 2026-10-18.
**Status:** Source-only proposal; no production release or authority granted.

## Directly verified defect

The canonical isolated Release Manager preparation of protected main source
`6c25663fce4faf4202b975c674ec7733f8dc1b69` built candidate Docker
images, and copied state (after #1573), but the candidate runtime exited
before reaching health acceptance with `ModuleNotFoundError:
usage_ledger.ledger`. A direct **offline, no-network, read-only** inspection
of exact image `jason-runtime:release-6c25663fce4f` proved that the
`/app/implementation/usage_ledger` package exists, but its directory is
root:root 0700 and its `ledger.py` file is root:root 0600. Other essential
runtime modules, including `jason_runtime/composition.py`, are root:root
0600. The application's declared non-root UID/GID 1000:1000 cannot traverse
or read that code. This is a **file-permission bug**, not a missing
repository file. The same import-only probe against the currently working
LKG runtime image succeeded with UID/GID 1000:1000, no network, no mounts,
and read-only filesystem.

The canonical Release Manager builds from immutable Git worktrees under
root/private source-state permissions. Docker COPY inherits restrictive
mode bits and root ownership. Runtime Dockerfile did not normalize
permissions for the declared runtime account; MCP Dockerfile already
contains a separate source read normalization step.

## Narrow remediation

1. After installing the existing Python projects, normalize only the two
   **build-time source trees** `/app/implementation` and `/app/config`
   to owner UID 0, group GID 1000; remove group/other write permission
   and grant group read/traverse. This preserves root-owned executable
   code while allowing runtime user 1000:1000 to import/read it. No
   secrets, host state, or provider credentials are copied/normalized.
   Preserve `USER 1000:1000`, read-only production compose settings,
   no-new-privileges, and existing managed runtime topology.
2. Gate all future Release Manager-built **runtime images**, not just
   their Docker build exit status, on a bounded 45-second container
   import smoke as UID/GID 1000:1000. Use the exact image, no network,
   no mounts, read-only filesystem, no extra Linux capabilities,
   no-new-privileges and explicit memory/PID limits. Import the
   `usage_ledger.ledger` and `jason_runtime.main` modules. Any error
   fails candidate admission and does not imply preproduction success.
3. Classify both runtime Dockerfile and root `.dockerignore` as
   protected `production_control_core` source. Any future changes to
   image security/build context require separate exact-revision Owner
   approval under the existing governed release gate.

## Operational acceptance and limits

Python unit tests verify Dockerfile hardening, fail-closed import smoke,
guarded build ordering/cleanup, and protected core classification.
These source tests are **not sufficient** to close this incident. On the
exact merged SHA, the official Release Manager must build and import
the candidate as non-root, then pass fully isolated runtime health,
state isolation, provider writes disabled, rollback readiness and all
GitHub checks. A fresh exact-revision Owner approval and CCC material
review must precede any protected production promotion.

The previous owner-approved `b1ea8751...` release is FAILED with
`rollback_verified=false`. Subsequent owner-unapproved source
`a11ae28...` and `6c25663...` preparations did not pass preproduction.
Do not reclassify them as deployed or verified. High-risk owner-reviewed
Teams policy and Universal Teams Approver remain OFF. A closed breaker
after independent root revalidation is not proof of successful rollback.
