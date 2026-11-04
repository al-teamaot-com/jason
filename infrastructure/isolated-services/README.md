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
