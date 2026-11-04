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
