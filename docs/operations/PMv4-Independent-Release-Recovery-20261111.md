# PMv4 — Independent release/recovery controls and migration gates

**State:** Source-only, preproduction; no production installation, reconfiguration,
freeze manipulation, signed Owner decision, or host provider mutation.
**Owner intent:** PMv4 can release/rollback independently of PMv3 engineering,
without tying Ticket Processing or Runbook Management to the Production Manager.

## Reused trusted mechanisms, not a competing release system

This work extends the existing PMv4 **isolated shadow** release path from
`tools/pmv4_shadow_release.py` and `pmv4_shadow_docker_adapter.py`.
It still reuses Jason's existing authenticated Ed25519 exact-owner release proof,
immutable reviewed scope, GitHub protected-main/required CI attestor, controlled
Docker namespace, audit receipts, activation and crash-safe rollback.

**New independent host composition:**

- `pmv4_host_release_guard.py` supplies fresh, read-only, direct Docker
  inspection of `jason-runtime` and `jason-mcp-pilot`, their exact current
  production source SHA and the canonical Ticket Core SQLite scan heartbeat.
  It never treats PMv3-generated PASS files as authoritative health evidence.
- The guard acquires BOTH the existing legacy production transaction inode
  (`/var/lib/jason/openclaw/release-manager/production-transaction.lock`)
  and a new trusted PMv4 control inode
  (`/var/lib/jason/pmv4-shadow/control/host-mutation.lock`). It holds both
  until independent shadow promotion/recovery, verification and rollback finish.
  This is a bounded compatibility lock for avoiding parallel PMv3/PMv4 host
  mutation, **not an execution dependency on the PMv3 controller or AI**.
  Verified host metadata: the *existing* PMv3 transaction lock is owned by
  non-root UID `1000`, mode `0664`; a separately provisioned PMv4
  host lock must be root-owned, mode `0600`. The guard intentionally
  authenticates these two different known owners; treating both as root-owned
  would permanently block this migration.
  **Important fail-closed release gate:** During this transition the independent
  host guard also requires the protected Last Known Good manifest to match the
  live runtime and MCP source, the protected circuit breaker to be **closed**
  with the same revalidated revision, and a fresh zero-problem drift
  readback. A fresh drift PASS does not automatically clear a prior open breaker.
  On November 11 the live production breaker remained OPEN with an old
  `undeclared_running_container` reason; `inspect` correctly reported
  `protected_release_control.ready=false` and
  `shadow_promotion_ready=false`. No direct or automatic breaker closure is
  implemented.
  The PMv3 lock must be removed from the contract *only after* proving no
  legacy writer remains; removal before then would permit a split-brain release.
- `pmv4_shadow_release.py` invokes the shared host lock over the complete
  promotion and previously authorized interrupted rollback, not merely at
  the preflight instant. Existing signed approval and freeze remain required.
- `pmv4_shadow_host_runtime.py` binds trusted source and callbacks into a
  separately installable entrypoint: `inspect` (read-only),
  `promote-signed` (a previously signed, immutable, exact release only),
  `reconcile-pending` (a previously authorized interrupted rollback only).
  There are **no CLI options for a raw command, API key, provider write,
  candidate source override, arbitrary host path or unsourced approval**.
  Production mutation subcommands require root and pinned trusted paths.
- A missing independent Owner/Entra authenticator, root-trusted key,
  protected-main CI, project-only Docker adapter, runtime image, freeze,
  dual locks or Ticket Core health **prevents promotion**.

## Verified preproduction evidence

On November 11, 2026, `python3 tools/pmv4_shadow_host_runtime.py inspect`
read the live host without modification and returned:
`status=verified`, `runtime_healthy=true`, `mcp_running=true`,
`worker_scan_fresh=true`, `source_sha=690250b4d21f32cce79cab9f5b4c18cf93e7e94a`,
`production_mutation=false`, `cross_release_lock_ready=false`,
`independent_release_installed=false`.

`cross_release_lock_ready=false` and `independent_release_installed=false`
are **deployment NOT-READY flags**: no trusted PMv4 control root/host lock or
independent Entra Owner issuer exists on the live host yet. Never report the
standalone release as deployed or production-ready based on its source tests.
The existing PMv3 Owner pause, promotion hold and protected desired-state
have not changed.

Offline acceptance includes signed exact Owner proof, expiry/replay denial,
source/scope/bundle/freeze tamper rejection, full-transaction shared lock
lifetime, zero unauthorized provider mutation, cross-container shadow isolation,
forced failed activation rollback and recovery of interrupted authorized
transactions. Fake signer keys/host callbacks are **test-only**, never a live
production authorization.

## Exact governed migration in ordered component releases

### M0 — Stage and verify immutable source (no production mutation)

1. Retain a single protected source SHA baseline and archive current
   `jason-runtime` / `jason-mcp-pilot` OCI image IDs, root controls,
   freeze/pause/hold bytes, ticket worker ledger metadata/scan and all
   required user/root units. Record the live LKG/rollback SHA separately.
2. Build the final **merged protected-main** PMv4 source revision and
   complete all required CI checks; a draft PR SHA is *not* an approved
   production candidate SHA.
3. Bind exact reviewed file scope, image digest, rollback revision, freeze
   digest and manifest to one authenticated Owner decision. No reused or
   multiple-purpose approval proof.
4. Provision trusted PMv4 control directories, frozen manifests, keys,
   dual control locks, and root-installed binary **in the governed release**
   only. Every file requires independently reviewed source and Owner scope.

### M1 — Standalone shadow release/recovery acceptance

1. With both host locks and protected freeze, deploy only isolated
   `jason-pmv4-shadow-gateway` via the scoped Docker adapter.
   No provider network, write mounts, API keys or Ticket Core mutation.
2. Exercise exact SHA/manifest Owner approval, provider-free health,
   direct protected Ticket Core scan readback, deliberate offline
   activation failure and safe rollback; verify the immutable receipt.
3. Verify interrupted transaction recovery from a previously signed
   receipt only. Restore the prior shadow package or the explicitly signed
   empty baseline; prove no PMv3 state, root controls or ticket ledger changed.

### M2 — Ticket Core independence cutover (separate authorized Core release)

1. Release the lock-aware **embedded** ticket worker first using the
   current governed production-release boundary, retaining the same
   ledger and ticket provider identity. A legacy worker without this lock
   MUST NEVER overlap a new external worker. Pin both candidate and rollback.
2. Validate current provider-backed scan, active claims and waiting jobs.
   Drain/reconcile in-flight work before the exact cutover.
3. Install separately versioned, independently supervised Ticket Core
   using the **existing** worker engine and SQLite ledger. Verify the shared
   lock inode, secret projection, exact grants, zero duplicate claims,
   continuity across two separate real scheduled scans, readback of a
   controlled test ticket, MCP status and outbox notifications.
4. Prove that stopping/rolling back PMv4 engineering or Runbook
   Management does NOT stop the Ticket Core, and that Ticket Core rollback
   restores an exact verified image without replay or data loss.

### M3 — Runbook Management independence

1. Deploy the existing JSON playbook control plane/registry separately.
   Use its immutable staged versions, atomic generation/actor/fingerprint
   receipts, and existing exact Owner/capability policy.
2. Validate→stage→activate→readback→retire on a controlled playbook while PM
   engineering is intentionally unavailable. Do not automatically promote
   existing Markdown/code playbooks without per-playbook parity.

### M4 — Replace legacy release/engineering and retire PMv3 implementation

1. Migrate state consumers (Owner approvals, host recovery/drift, MCP,
   Grafana/alerts, TODO/PR workboard and provider health) onto explicit
   PMv4 component interfaces. Preserve historical PMv3 readback.
2. Prove a governed *component-scoped* release (Ticket Core not touched)
   and its rollback, then an approved independent Ticket Core release and
   recovery, including production failure injection with no collateral change.
3. Only then remove obsolete PMv3 user/systemd timers, installer assertions,
   required desired-state entries and PMv3 release runner through a separately
   authorized, exact-unit-delta transaction. Preserve all historical evidence
   and authenticated Owner/tenant/disruption/audit protections.
4. Retire the transitional PMv3 transaction lock only after proving zero
   PMv3 writers. Keep the PMv4 component-scoped transaction lock.
5. End only when all production services, providers and functional smoke
   readbacks are healthy, drift and freeze restored, LKG advanced
   correctly, and rollback verified.

## Remaining boundaries (explicit NO-GO)

**A.** This commit implements and tests independent **shadow** release and
host recovery admission, **not yet** a deployed multi-component PMv4 release
manager. A final release controller for ordinary provider-connected
Ticket Core/Runbook deployments needs a separately scoped trusted adapter,
validated component images/secrets and governed cutover.

**B.** Actual Owner Entra issuance middleware, trust root and independent
PMv4 host control root/locks are not currently provisioned. These must be
installed with exact independent approval rather than created ad hoc.

**C.** The current production image's embedded ticket worker does not claim
the new lock; the separate worker must never run against it until M2.

**D.** Production freeze/hold and exact-release authority remain unchanged.
An Owner's approval of engineering preparation is not permission to deploy
a still-untested runtime, disable a production service, bypass root drift
or issue an approval proof on their behalf.

## November 12 independent circuit-breaker recovery scheduler (source-only)

Root-cause observed on Jason: the breaker opened at 2026-11-12T06:59:34Z
for an undeclared running container; subsequent root drift observations passed,
but the durable recovery tracker remained at its November 8 closeout. The
installed `jason-support-repair-worker.service` is skipped because its separate
PMv3 engineering Owner pause is active, so its `release_breaker_recovery`
stage cannot accumulate the new breaker observations.

The proposed `jason-release-breaker-recovery.service` and matching timer
invoke **the existing pinned native recovery manager**, not a new breaker
writer, under the same unprivileged identity. This removes its dependency
on engineering admission and Owner pause without touching either hold.
The manager still validates exact installed LKG policy and distinct root
drift observations; only the preexisting independently privileged transition
worker may revalidate and close the breaker. It does not have an emergency
override, signing key, direct root-state writer or independent deployment path.

**Source-only acceptance:** focused unit assertions and `systemd-analyze
verify` must pass. These units are not installed or activated by this PR.
The trusted release installer must explicitly add them to protected desired
state in a later exact-scope Owner-authorized release, after comparing their
interaction with existing root transition timers and proving no overlapping
transaction. The first live recovery requires at least three distinct fresh
root PASS observations and guarded root readback. Never manually edit the
breaker to manufacture readiness.

**Coexistence race protection:** The existing bounded manager now serializes both
PMv3-pipeline and independently scheduled invocations using a persistent
same-inode, no-follow, mode-0600 unprivileged advisory lock in its existing
recovery spool. Contention skips the second invocation without consuming a
root revalidation attempt or editing protected release state. The lock file
is not unlinked. Focused contention and existing manager regression tests
exercise both busy and uncontended paths. The installer must deploy the
updated manager and independent timer together, never the timer alone.
