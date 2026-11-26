# PMv4 Stage E - legacy control-plane reactivation blockers

November 18, 2026. Verified source-only negative gate, NOT a release.

The first three Stage E core transitions are accepted in production:
Stage C independent external Ticket Core with two actual provider scans;
Stage D independent read-only Runbook Management; and A1 v5 isolated
preproduction shadow. The source-only PMv4 E canary/durable scheduling
regressions were merged to main as d85faad76881439953527d391c314df0f5d2967a.
An immutable, unprivileged canary release packet was built, with distinct
OCI image-source SHA and new candidate SHA. The generic canary has NOT
been root-installed or Owner-authorized.

Retiring the six old engineering/release timers and paths alone is
insufficient: three installed control-plane scripts still depend on
old units.

1. User self-heal watchdog, tools/jason_self_heal_watchdog.py,
   hardcodes jason-release-manager.timer and
   jason-support-repair-worker.timer in its required timer list.
   It starts jason-support-repair-worker.service directly on some
   support-repair incidents, independently of its scheduling timer.
2. Legacy release-manager host runner,
   tools/release_manager_host_runner.py, requires old release-manager
   and support-repair user timers, and actively rechecks and installs
   the legacy release manager timer.
3. Root host reconciliation,
   tools/reconcile_production_host_services.sh, explicitly calls
   install_support_repair_host_worker.py --activate and
   install_self_heal_watchdog.py --activate, and verifies original
   worker source and runtime revision. Without replacement, it may
   reinstall PMv3 worker units after a nominal Stage E cutover.

The read-only helper tools/pmv4_e_controlplane_dependencies.py adds
five NO-GO reasons to the Stage E assessment:
- WATCHDOG_REQUIRES_LEGACY_TIMERS
- WATCHDOG_RESTARTS_LEGACY_WORKER
- RELEASE_MANAGER_REQUIRES_LEGACY_TIMERS
- ROOT_HOST_RECONCILER_REINSTALLS_LEGACY_WORKER
- REPLACEMENT_CONTROLPLANE_ROOT_ACCEPTANCE_MISSING

Missing legacy source strings are not sufficient proof of a working
replacement or its actual acceptance. The helper emits only source
hashes and blocker names; it never starts/stops services, publishes
desired-state policy, invokes providers or issues Owner authority.

To retire PMv3 correctly, keep old units active until a reviewed
independent PMv4 replacement proves durable five-minute engineering
claims/retries, authenticated Owner approval offers, component release,
root-host reconciliation/readback, recovery/rollback and self-heal
activation of ONLY the new worker. Preserve boot, drift, authority
and provider monitoring. The final exact Owner transaction must
update replacement scheduling AND watchdog/reconciler dependencies
as one rollback-protected cutover. If it fails, restore old units and
watchdog target exactly; verify zero duplicate work and drift PASS.

Source-only CI creates no production authority. Generic component
live acceptance, protected C/D/A1 receipts, protected desired state,
and fresh authenticated exact retirement approval remain required.
