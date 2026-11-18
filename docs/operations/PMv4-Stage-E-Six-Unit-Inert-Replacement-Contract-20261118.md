# PMv4 Stage E - six scheduled control replacements, source only

November 18, 2026. NO production install or cutover authority.

The live one-Owner native generic controller canary was accepted and removed.
The independent read-only historic receipt verifier is now in protected main.
The next objective is preserving six engineering/release control schedules
while preventing PMv3 self-heal/reconcile from restarting legacy workers.

The source-only unit bundle in infrastructure/pmv4-e-scheduler/systemd
contains six exact trigger replacements and six matching services:

| Existing scheduled control | Inert proposed PMv4 control |
| --- | --- |
| User support-repair-worker.timer | User pmv4-engineering.timer |
| User release-approval-only.timer | User pmv4-release-approval.timer |
| User release-manager.timer | User pmv4-component-release.timer |
| Root release-control-transition.timer | Root pmv4-component-transition.timer |
| Root release-control-readback.timer | Root pmv4-component-readback.timer |
| Root release-host-reconcile.path | Root pmv4-component-reconcile.path |

Every generated service ExecStart is byte-identical to the existing
approved backend. This avoids a duplicate release engine but is NOT
evidence that all underlying functions have been converted to PMv4.
The release manager still uses the prior routine; the root host
reconciler can reinstall old workers and must be migrated separately.

Each new service includes one ExecCondition calling the reviewed future
root-installed path:
  /opt/jason/pmv4-e-trusted/tools/pmv4_e_unit_admission.py
with a single known role. The guard defaults to legacy mode while no
root-accepted exact cutover marker exists. A malformed, untrusted or
missing marker DENIES new execution. The marker must bind the exact
authenticated Owner action, prior and accepted policy digests, freeze,
all old/new unit names, watchdog retarget, root reconciling that cannot
reactivate old workers, native drift PASS, and exact rollback receipt.

The source bundle validated 12 reviewable unit files. The generated
timer cadences and path activation preserve the existing source.
systemd-analyze verify passed; its sole unrelated warning concerns an
existing cag.service KillMode=none. Live read-only admission without a
root acceptance marker denied with exit 255 and no worker start.

Before final one-Owner root cutover:
1. Rebind and test watchdog timer requirements and engineering target,
   preserving the original shared production transaction lock.
2. Migrate root host reconciler/installer to prevent PMv3 reinstalls.
3. Migrate release-manager production-convergence/readback to PMv4.
4. Prove all six replacement callbacks, 5-minute claims/retries,
   approvals, holds, crash recovery and rollback in a disposable
   provider-free test while old triggers are disabled in that test.
5. Review an exact SHA, prior/new root policy and rollback old/new
   six-unit transaction, obtain a fresh scoped authenticated Owner
   approval, and execute only after preflight PASS.
6. Independently verify two live ticket scans, zero duplicates,
   closed breaker, native drift, freeze and no reactivated PMv3 path.

None of the newly generated units is installed or enabled. Production
Ticket Core, MCP, old units, freeze and original safety controls remain
unchanged. No external provider write authority is granted.
