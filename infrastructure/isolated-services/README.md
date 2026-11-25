# Isolated shadow service units (not installed)

These **source-only** template units are proposed for independent scheduling.
Each timer instance runs exactly one evidence worker. State is owned by the
isolated worker under `/var/lib/jason-isolated-services/`. No instance can
approve, merge, deploy, change GitHub permissions, reset a breaker, or write a
provider object. Existing PMV3 remains the sole production mutation authority.

Before these templates can be deployed, the native Production Manager must
include every Python companion module in its immutable host-unit manifest,
verify the dedicated state directory and read-only source access, and present
the exact merged candidate SHA and rollback SHA for Teams owner authorization.
The host source repository must be pinned to the intended immutable source
revision; a local `origin/main` tracking ref is not a substitute for a fresh
remote baseline proof. The shadow runner's source-baseline service deliberately
returns `unknown` until an immutable expected SHA is supplied by an approved
release-specific configuration. Timers must never be enabled merely because
these files exist in a branch.

Independent instances: `documentation_assurance`, `provider_health_monitor`,
`test_evidence_collection`, `work_reconciliation`, `dependency_conflict`,
`source_baseline_monitor`, `rollback_readiness`, and
`operational_acceptance`. The test, dependency, source-baseline, rollback and
acceptance instances require an authoritative input/configuration integration
before their results can be used beyond advisory `unknown`/`pending` state.

A separate ledger and supervisor can be run after independent service samples;
no global PMV3 gate is installed by this design.

## Independently scheduled native engineering lanes (source only)

Four additional user-service/timer pairs are staged for `support`, `todo-intake`,
`development`, and `supervisor`. They call **the existing governed worker
entrypoints** and use their native approved-work, support-first, bounded-claim,
recovery and evidence rules. They do not create a second engineering queue.
Each instance has its own timer/failure domain and must pass the existing
`pmv3_worker_release_gate.py` production-transaction admission check. These
units require the durable old-controller owner-pause receipt to be present;
they cannot start alongside a resumed old monolithic controller.

The read-only inspection on November 4 found that the production-transaction
gate exists in source but is not present at the prospective installed path.
The unit templates therefore explicitly require that source to be installed
by the governed immutable release. The full companion-source and unit inventory
is in `installation-manifest.json`. All new units remain **disabled** unless
and until exact-SHA production authorization, host rollback, production safety,
worker-capacity/concurrency acceptance and migration checks pass.

Do not copy these units or gate manually onto the Jason production host.


**Reuse existing independent publishers:** Jason already has a governed documentation reconciliation service and provider-health canary timer. The new Documentation and Provider Health workers are advisory consumers of those authoritative outputs, not competing documentation merge or provider-probe writers. Preserve those existing units unless a separately authorized manifest replaces them.

## Ticket-processing continuity is a deployment NO-GO

The independent worker lanes must remain disabled until the release's `ticket_continuity_release_gate` has fresh, governed evidence for ticket intake, Autotask queue routing, notes, device association, claims/retries, alert-ticket handling, and notifications. Require controlled test-ticket read/write verification, no duplicate ticket actions, and two independent post-cutover observations. Do not shut down the existing ticket runtime, bypass existing authorization, or treat read-only success as proof of ticket lifecycle functionality. Any missing, stale, or failed receipt stops the cutover and invokes the authorized rollback path.

## Native Stage A: disabled provider-health shadow (release-owned)

The first deployable preparation slice is two **system** units under the
previously recognized, LKG-compatible canonical source path:

- `infrastructure/openclaw-operations/systemd/jason-isolated-provider-health.service`
- `infrastructure/openclaw-operations/systemd/jason-isolated-provider-health.timer`

Both are **allowed but not required** by `config/production-desired-state.json`.
`tools/reconcile_production_host_services.sh` invokes the fixed-path root
`tools/stage_isolated_provider_shadow_units.py` inside the exact-SHA native
release transaction. The stager refuses an enabled, active, modified or
symlinked unit; validates all companion sources and the explicit disabled
inventory; copies exactly those two identical files atomically into the
canonical systemd directory; reloads the daemon; and verifies both remain
inactive/disabled. It never enables, starts, stops, or restarts a service.
The new service is read-only, advisory-only, runs as `al` with reduced
privileges, and reads the existing provider-canary snapshot without calling
providers or modifying the Autotask ticket processing path.

**Rollback:** The prior LKG `reconcile_managed_unit_delta.py` already
recognizes this source directory and can remove the two byte-matching
candidate-only units before rollback; two is below the native eight-unit
removal limit. The disposable test suite exercises the actual LKG planner.
No source-only commit installs these units; they can only be staged upon
independently approved exact-SHA production release and do not self-activate.
Future service activation or native engineering-worker cutover is a separate,
explicitly authorized release phase and must pass the ticket-continuity gate.

## Independent engineering lanes — governed support-first handoff

The four source-only engineering-lane timer definitions now invoke
`tools/independent_governed_lane.py`, a small admission/worker wrapper rather
than calling the native write-capable worker scripts directly. The wrapper
**does not** create a new work queue, approval mechanism, or provider API.
Support, TODO intake, and development share a nonblocking local engineering
lease, so they cannot concurrently claim the same approved work while moving
out of the old sequential pipeline. TODO intake and development require a
recent successful support-worker receipt **from the same exact source SHA**;
missing, failed, future or stale receipts defer those lanes and are recorded.
The independent, read-only supervisor is not serialized behind support work.

Each native worker execution also retains a shared lock on the existing
production transaction file for its full duration, preventing the old
release/worker race that a one-time `ExecCondition` check alone could miss.
This guard reuses the installed managed source and checks exact bytes against
the currently managed native worker before invocation. Worker failures are
recorded as local degraded outcomes, not silently reported as successful work.
The existing native worker still owns approved claims and all provider
permission checks; no extra ticket or provider writes are granted.

The wrapper and all independent engineering units remain **source-only**.
No new engineering timer is installed/enabled by Stage A. Any later cutover
requires complete source installation under the native release, exact-SHA
Owner authorization, ticket-continuity proof and independently verified
rollback. Do not replace or resume the old engineering loop merely because
this guard passes unit tests.

The admission wrapper double-checks that the old PMV3 engineering service has
an Owner-approved systemd no-start drop-in **and** that systemd's actually
loaded `ActiveState=inactive` / `ConditionResult=no` is observed before any
new engineering worker is admitted. A stale pause file alone is insufficient;
this prevents hidden duplicate controllers after native reconciliation.
