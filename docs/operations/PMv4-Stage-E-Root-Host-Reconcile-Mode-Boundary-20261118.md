# PMv4 Stage E - root-host reconciliation cannot reinstall PMv3 after cutover

2026-11-18. SOURCE ONLY; NO root installation or Owner authorization.

The existing root host reconciliation script includes direct installers
for the legacy support-repair worker, release manager and release-control
transition timer. Replacing six systemd unit names without changing
these installers would allow PMv3 to reactivate after accepted PMv4
retirement, opening production drift or duplicating work.

The source adds root-only
tools/pmv4_e_root_reconcile_admission.py and a narrow conditional
mode in tools/reconcile_production_host_services.sh.

- Before any host-source or service changes, the script checks for a
  root-accepted Stage E marker. If no marker exists, all legacy unit
  and installer behavior remains as before.
- If a marker is present, a pinned root-only admission module must
  verify the original trusted acceptance via the approved root-owned
  PMv4 unit guard. The release SOURCE_REVISION must match the exact
  accepted release SHA. A bad, outdated, symlinked, writable,
  inaccessible or mismatched marker DENIES; it never falls back to
  the old installer or a caller-selected mode.
- In the accepted replacement path, root reconciliation refuses to
  invoke the old root-policy staging installer, support-repair worker
  installer, root-host reconciler installer, user release manager
  approval installer, or root release-transition timer installer.
  Instead it requires the exact trusted PMv4 guard and active
  replacement engineering, release approval, component release,
  component transition and component reconcile units, and rejects
  reactivated retired PMv3 controls.
- The self-heal watchdog still runs under the existing production
  transaction lock. The exact reviewed self-heal installer is
  preserved but reads the new accepted marker to determine its
  engineering target. No generalized drift, freeze or restart
  override is introduced.
- This is not a second host reconciliation engine. The existing
  canonical root host script retains all other source, authority,
  exporter, security, telemetry and root controls.

The source-only test suite passes the root source/approval contracts
and negative markers with 177 tests. The script parses with bash -n.

UNRESOLVED BEFORE LIVE RETIREMENT:
1. Verify the new root installer and all new scheduled controls are
   source-pinned, root-owned and actually active at the exact cutover.
2. The legacy Release Manager's scheduled_control_alignment and
   install_release_manager_from_current still require PMv3 timer
   names. They need a similarly fail-closed accepted-mode path.
3. Install the reviewed watchdog/root reconciliation path BEFORE
   issuing the accepted marker in one rollback-protected transaction.
   Otherwise an older installed script could re-enable the old units.
4. Prove all six real callback behaviors, durable claims, retries,
   incident holds and rollback while old triggers are disabled in
   an isolated provider-free test. No source-only assertion of full
   parity is allowed.
5. One fresh authenticated Owner approval must bind the final exact
   policy/source old/new-unit delta, rollback and postflight. A failed
   postflight restores prior units and policy; no breaker bypass.

None of these source changes has touched production. The old
production schedule, Ticket Core, MCP, runbook-read, shadow, native
drift watchdog and freeze remain under their existing governance.
