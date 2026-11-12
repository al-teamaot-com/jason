# PMv4 Ticket Processing Core — independent lifecycle seam

**Status:** Preproduction source only; no new Docker container, timer or service is activated. Production Ticket Processing still runs inside `jason-runtime`.

## Actual existing design reused

- `jason_runtime.autonomy_worker_runtime`: deterministic ticket admission, playbooks, durable SQLite work, provider receipt verification and governance.
- `jason_runtime.autonomy_worker_supervisor`: liveness and bounded process recovery.
- `jason_runtime.maintenance_process`: existing ticket-only composition separate from notifications and auxiliary tasks.
- `/var/lib/jason/openclaw/autonomy-operational-work.sqlite3`: canonical ticket work ledger, never copy/erase or replay blindly.
- All current Autotask, Datto, approval, identity, disruption and client-isolation rules remain binding.

## Source-only additions

- `JASON_TICKET_WORKER_HOSTING` defaults to `embedded` and accepts only `embedded` or `external`; default installation remains unchanged.
- The **actual ticket-dispatch child process** (in embedded or external hosting mode) claims a persistent, non-blocking exclusive OS file lock beside the canonical SQLite ledger **before constructing its runtime**. The supervisor/HTTP parent never owns the lock. This prevents an orphaned child from continuing to dispatch after its supervisor dies while a new owner acquires the lock. Another instrumented worker using that **same underlying inode** is rejected before dispatch.
- `python -m jason_runtime.ticket_worker_service` provides an independent non-HTTP supervisor entrypoint, requiring `JASON_AUTONOMY_WORKER_ENABLED=true` and explicitly selected `JASON_TICKET_WORKER_HOSTING=external`.
- In external hosting mode, `jason_runtime.main` does not spawn its own ticket worker; it continues serving HTTP and auxiliary maintenance.
- No PMv3 engineering controller, release runner or Teams approval is invoked by the ticket-only entrypoint.

## Zero-downtime migration constraints

1. **Do not activate the external worker against the current old embedded production worker.** The old deployed image does not claim this new lock. An external worker started now could duplicate ticket actions despite the new code's local tests.
2. Before a cutover, deploy the lock-aware embedded version only under a separately governed exact-SHA release that preserves the legacy behavior and authoritative ledger. Verify existing scan/claim/notification and native readbacks.
3. Prepare independent image and service deployment using the existing runtime code and secrets, with isolated component-owned lifecycle and its own LKG/rollback. Verify *the exact same* mounted SQLite and `.owner.lock` filesystem inode is visible to both candidates. No new provider capability or standing authority.
4. During a governed serialized cutover, stop creating new embedded claims, wait for any active in-flight provider job/claim to settle or remain safely reconcilable, and use the verified ledger/receipts to determine outstanding work. Do not kill the existing worker opportunistically.
5. Enable the existing HTTP runtime in `external` mode and independently start the external service **only** within the approved transaction after confirming the embedded owner released its file lock. Any second owner must fail closed.
6. Verify two distinct scheduled scans, exact work counts/phase carry-over, a controlled test-ticket diagnostic/readback, **zero duplicate jobs/notes/claims**, and unchanged MCP/runtime health and protected freeze.
7. Roll back through an exact verified image/service state and preserved SQLite work ledger, not by deleting the owner lock or restarting unrelated PM services.
8. Keep Ticket Core in PMv4's protected service registry. Unrelated Release Controller/Engineering Work/Runbook Management updates must leave its process and data untouched.

## Minimum offline acceptance

The new source tests verify the default embedded hosting path, illegal mode rejection, an exclusive kernel lock across independent OS processes, rejection of untrusted lockfiles, absence of duplicated ticket supervisor in external HTTP mode, and a standalone supervisor that starts only in explicitly selected external mode.

**Not yet accepted:** Live host/container separation, two-scan functional continuity, governed cutover, host-level release evidence or any production deployment.


## Concurrent development review (source-only)

Reviewed current open PR file patches on November 11, 2026:
- #2405 and #2373 add unrelated runtime composition behavior.
- #2336 adds financial-statement maintenance settings and validation near, but not on, the Ticket Core hosting insertion points.
- #2384 adds Constant Contact credential wiring outside the Ticket Core worker-hosting boundaries.
- #2393 and #2395 both change the release-mobile approval-mode enumeration and may conflict with *each other*; this Ticket Core change does not select or reconcile their competing governance behavior.

The Ticket Core patch adds three distinct fields/guards (hosting default, environment parsing and validation) and does not modify the competing hunks. Rebase and rerun full composition regression after whichever active PR changes reach protected main. Do not merge if source changes break the single-owner guarantee.


## Isolated-container acceptance evidence — 2026-11-11

Executable, repeatable test: `python3 tools/pmv4_ticket_core_container_acceptance.py --acceptance`.
It runs three **synthetic** scan recordings in throwaway Docker containers using the
new source-only exclusive worker owner and shared temporary SQLite ledger, never
any live Autotask/DRMM data. First two scans run under the initial owner; a
second isolated container is rejected from taking the active lock; after the
primary voluntarily stops, a new independent container acquires ownership and
records a third scan without creating a duplicate ticket claim.

Observed PASS: network `none`, read-only filesystem, dropped Linux capabilities,
`no-new-privileges`, non-root UID 1000:1000, read-only source/script mounts,
no provider secrets or metered AI keys, no production mounts or provider writes,
three unique synthetic scan timestamps, one unique synthetic ticket claim,
contender exit code 11, successful post-stop reacquisition.
Runtime base image ID: `sha256:186977467897e6944f5c5f0d51c0d465b3515174c44fda1e390ccd5d2b18bff7`,
label source `690250b4d21f32cce79cab9f5b4c18cf93e7e94a`.
Tested new worker implementation fingerprint (two source modules concatenated):
`8c0127bf074ef2ff61e8858411ab6bcd4e199ee375b622023cad15c835c5c07d`.

Run `python3 -m pytest -q implementation/runtime_service/tests/test_ticket_core_lifecycle.py
tests/test_pmv4_ticket_core_container_acceptance.py` to regression-check
the cross-process lock and Docker isolation attestor. This evidence is offline
acceptance only. **Production acceptance is still a NO-GO** until exact release
authority, lock-aware embedded deployment, live worker migration and two
post-cutover provider-backed scan/readback observations are completed.

## November 12 child-owned lock and preproduction bootstrap acceptance

The earlier parent-owned lock had a split-brain risk if the supervisor failed
but its spawned dispatch process survived. This source revision moves the
exclusive kernel flock into `run_autonomy_maintenance_process` for the
`ticket_worker` profile. Both embedded and standalone modes construct the
same worker under that lock. The lock is never unlinked; a terminated child
releases only its file descriptor and a legitimate replacement may reclaim
the same inode. HTTP and auxiliary maintenance do not hold or acquire the
ticket lock. A competing child fails **before application construction**.

Local tests verify lock ownership during an actual synthetic worker tick,
rejection of the competing process before runtime setup, no duplicate
embedded dispatch when hosting is external, and supervisor lifecycle.
The reviewed GitHub Actions preproduction workflow separately builds the
candidate runtime image and performs three synthetic Docker scan cycles,
competing-owner rejection and reacquisition **on a disposable GitHub runner**.
Do not run undeclared acceptance containers on the protected Jason host:
its live desired-state watchdog may open a production circuit breaker.

**Still required before a live Ticket Core claim:** Exact Owner-authorized
protected release B, verified production LKG and root breaker, existing
embedded worker quiescence, unchanged durable SQLite ledger and notifications,
the new child lock held through the real scheduled scan, no parallel external
service, two separate provider-backed readbacks and exact image rollback.
An offline child-lock test is not proof of production admission or release.
