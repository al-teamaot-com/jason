# Stage E isolated root reconciliation release

Status: source preparation, November 20, 2026. Production cutover remains pending.

## Verified baseline

The Owner restored the exact approved shared root worker. Its SHA256 is
dca0c480265426c3c73f9cf8f7b8a9a4c5ab555640bd6953eb127cf3963a1896.
The existing catalog recovery subsequently returned idle_no_scoped_transaction.
The existing bounded breaker manager collected three distinct clean root
observations and the original root revalidation closed the breaker at
2026-11-20T15:07:21Z. Subsequent root drift readback passed.

The earlier dispatcher replacement conflicted with the catalog controller's
independent worker pin. Changing that catalog trust pin or relaxing the
production gate was rejected. This release preserves those controls and uses
the restored baseline as a prerequisite.

## Concrete behavior

The replacement component-reconcile service executes the reviewed worker from
/opt/jason/pmv4-e-trusted/tools/release_host_reconcile_worker.py. Native Stage E
code switching modifies only the watchdog, Release Manager runner and exact
six-unit root policy. The catalog-pinned shared root worker is excluded from
that transaction. The isolated worker uses the existing root-owned policy
migration helper at its canonical installed path.

The watchdog verifies the Stage E control revision separately from the
protected runtime baseline. Runtime source links and inherited helper hashes
come from the existing runtime release. Stage E watchdog, runner, replacement
timer and isolated worker hashes come from the accepted control revision.
The engineering repository must be clean and contain the accepted revision.

## Exact local root decision

The local launcher pins the installer bytes, candidate, archive, manifest and
existing trust tree. Its isolated-cutover mode first verifies fresh root
health, the original accepted install receipt, the restored shared worker,
catalog policy, protected source scope, required CI and independent live
Stage E prerequisites. Failures deny before requesting an Owner decision.

The existing Entra verifier authenticates the Owner and displays
COMPLETE-EXACT-ISOLATED-PMV4-E with the complete installation scope.
One exact decision covers source preparation and the original native Stage E
transaction and rollback. Root records retain the exact scope and actor.

After approval, existing locks protect the sealed source/policy update.
Failed source preparation restores both prior images. The installer refreshes
the original root CI evidence, obtains the original exact service signature
under the verified Owner decision and passes that same proof to the existing
root bootstrap and native ledger. Each original gate remains independently
enforced. The native controller alone owns unit switching and rollback.

A bootstrap failure attempts the original signed inert cleanup. Native STARTED
receipts prohibit inert cleanup and retain their original ledger recovery
authority. A native rollback is recorded as rollback and cannot satisfy
acceptance. Consumed approvals cannot be reused.

## Verification and remaining gates

Local focused tests cover exact unit inventory, scope binding, source rollback,
catalog drift denial, signed recovery and acceptance versus rollback.
UID0 filesystem tests run only on the disposable privileged CI runner.

Before a release is executable, protected CI and an immutable merged candidate
must pass, the exact source-only package must be rebuilt from that candidate,
and all archive bytes must match its reviewed Git objects. The connected
UID1000 tool session cannot supply local root execution. The prepared launcher
requires the Owner's sudo terminal and exact current-scope decision.

After native acceptance, independently verify all six replacement triggers,
all six legacy retirements, component ownership, protected runtime containers,
freeze/hold hashes and fresh root drift. Existing Owner pause and production
hold remain part of the governed operational state. MCP issuer publication
and full PMv4 operational completion require their own verified evidence.
