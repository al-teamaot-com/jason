# P0 rollback of candidate-only Jason systemd units

Parent issue: #1078. Related unresolved rollback-integrity issue: #1101.

## Existing behavior and risk

Production host reconciliation installs the target release's canonical host units,
removes a fixed list of obsolete units, and runs the production desired-state
drift guard. Its fixed cleanup list does not cover a future candidate release
that *adds* a new service, timer, or path unit and is then rolled back to a
previous release which did not declare it. A leftover installed unit is
correctly classified by the guard as undeclared installed system/user unit.

This is a source-reviewed potential rollback defect, NOT a demonstrated live
failure of the currently deployed release.

## Bounded source-only remediation

The root-owned, serialized host reconciliation obtains the prior immutable
release symlink and intended target release before updating the symlink.
When both are distinct, it runs a new read-only unit-delta planner.

The planner:
- pins both releases to exact immutable SHA-named directories under
  /opt/jason/releases;
- reads the target and candidate production-desired-state manifests;
- selects at most eight candidate-declared, target-absent units per scope;
- permits only syntactically safe Jason service/timer/path names;
- requires exact candidate release source bytes for each installed unit, and
  rejects symlinked, missing-definition, duplicate-definition, or
  wrong-ownership files;
- lists the reviewed unit names, without executing actions or deleting data.

Reconciliation validates BOTH scope plans before any removal. It backs up each
owned installed unit, disables and stops triggering timers/path units before
services, removes only the validated fixed system/user unit path, reloads
systemd when required, and then proceeds with normal target source installation
and the existing drift guard. Plan or removal errors fail closed. No source,
tenant, provider, or endpoint permission is broadened.

The release policy and change-risk classifier explicitly treat both the root
host-reconciliation script and this new planner as PROTECTED CORE, requiring
exact-source Owner approval even when general autonomous repair releases are
permitted. The prior release policy omitted the root script from its explicit
protected list; this gap must be repaired before allowing this PR to merge.

This is limited to source-installed units proven to match the previous
release. Manually modified/third-party units are NOT removed automatically and
must remain an explicit blocker for examination. The fixed obsolete-unit
cleanup already present in the reconciler is not broadened.

## Acceptance limits

This source patch does NOT retroactively repair rollbacks into LKG versions
predating this helper. It must first be integrated and verified in a governed
production release before that release can be a safe future rollback target.

Isolated unit planning, structural host reconciliation, safe failure, and
regular release manager tests are necessary but NOT sufficient. A representative
candidate adding a harmless Jason test timer must be deployed through the
governed Release Manager and rolled back in an authorized controlled acceptance
test. Prove the new timer/service is removed, old unit set restored, no failed
required host/user units, active aligned runtime/MCP/host/controller revision,
fresh clean drift evidence, CCC requirements honored, breaker state verified,
functional smoke successful, and rollback record correct.

DO NOT merge or deploy based solely on this engineering exercise. The reviewed
exact release SHA and owner-controlled protected-core/CCC approval are required.
Stop if rollback/health/manifest verification cannot be demonstrated.
