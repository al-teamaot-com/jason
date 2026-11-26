# Native engineering closed-loop recovery

## Objective

P0 #1196: use the existing engineering supervisor, controller, self-heal
watchdog and resolution engine to detect and route exact stalled support work,
without requiring repeated Owner prompts or introducing a competing manager.
Source PR #2756 is the bounded engineering-control correction. Root-managed
installation is a distinct authorization boundary.

## Exact installation contract

The native engineering manager successor is anchored to accepted manager
revision 9b69aa8e2cdc7c9a037d044a5ac9d00cfcc2870f. The existing protected
runtime rollback revision remains d1b8c196dadd4b672ec8ba47075f27bb61c98d63.

The existing installer adds the fixed closed-loop successor mode. It replaces
only the supervisor, engineering controller, watchdog and resolution engine
under the native manager receipt, with the updated root guard and immutable
release evidence. It pins the resolver (previously a legacy runtime artifact)
and exposes already verified pipeline artifact hashes to the watchdog to
avoid false drift alarms. No new scheduler, root execution capability,
provider write, runtime/MCP restart, freeze change or source rollback is
authorized.

The candidate must be exact current protected main with native CI attestation.
The installer verifies the single squash-integrated bounded source change,
inventories every intervening excluded source path, and denies any intervening
change to the scoped files, installed manager dependencies, native controls,
or protected configuration. Only the fixed installation target set is applied.
The excluded paths are part of the signed scope; they are not installed.
Previously accepted independent integration, retry behavior, TODO quarantine,
the production mutex, peer identity, native drift and breaker remain mandatory.

## Preflight and decision

From a verified clean detached checkout of the exact protected-main candidate,
the existing installer supports `--closed-loop-successor --candidate <sha>`
for the native read-only scope preflight. Review its exact scope and rollback
before using the existing authenticated exact-action approval and apply route.
Do not run an unmerged or unverified checkout as root. No new human authority
is issued by preflight.

## Acceptance and recovery

Reuse the native immutable predecessor/receipt transaction, rollback and
pause restoration. Require two distinct normal scheduled cycles, every
engineering stage successful, independent-source integration intact,
fresh completed watchdog engineering-progress readback, existing quarantines,
unchanged runtime and MCP identities, native drift pass, and closed breaker.

Installation acceptance is not closure of #1196: additionally verify actual
advancement of a previously stalled support or development item, or a
specific independently verified external dependency. Maintain the original
P0 work item, support issue identities, and historical retry evidence until
the outcome is proven. Roll back through the existing exact transaction if
the governed install or acceptance fails.
