# PMv4 shadow OCI memory: signed per-release acceptance

**November 18, 2026. Source-only. Nothing deployed.**

The candidate shadow Compose profile now requests 4 GiB after cgroup OOM.
The pre-existing Docker adapter incorrectly pinned every inspected shadow
container to exactly 2 GiB. Without correction a healthy 4 GiB release
would be rejected at the first strict root postflight and consume another
one-time Owner authorization.

Only two memory budgets are permitted: the prior reviewed 2 GiB generation
and the new bounded 4 GiB generation. The initial Docker inspection accepts
either when transitioning between versions, while still enforcing every other
isolation and runtime control: sole shadow project/service, network none,
read-only FS, UID 1000, no capabilities, no-new-privileges, pids 256, CPU 1,
no automatic restarts, no host bind or secrets, exact image/provider boundary.

The candidate-specific post-Compose and health verification read the
immutable root-owned candidate Compose and compare its SHA-256 to the exact
release manifest. Only a single anchored mem_limit value of 2g or 4g is
allowed. The resulting effective Docker Memory field MUST equal the memory
budget in that signed manifest. On rollback, the prior immutable release
manifest selects 2g and verifies the restored container at 2 GiB. Unexpected
values including 0, 3g, 5g, missing/duplicate values and hash tampering
are fail-closed. A candidate asking 4 GiB with a Docker container still at
2 GiB cannot pass even if health reports healthy.

The tests cover old-to-new and new-to-old transitions, wrong effective
limits, prohibited values and duplicated YAML selectors, image/source hash
binding, unchanged isolation and the legacy native zero-baseline test path.
No Docker start/stop/compose operation was performed against the host.

Production remains at the existing root pointer
75f2b4c0c48a15bd17d700b9f039fe56623e3f52 with its shadow container
stopped, OOMKilled and a 2 GiB cap. The accepted rollback receipt for older
c999216a3df9d2422833b90403c31530c323f467 is historical, not a current
empty-baseline authorization. A new governed A1 recovery must preserve the
current exact 75f2 prior-release root pointer, root-only final receipt,
container rollback and existing freeze. No one-time Owner proof is reused.

This fix does NOT authorize a release, modify protected desired state, alter
Ticket Core/MCP/Runbook Management, permit provider access, or retire PMv3.
