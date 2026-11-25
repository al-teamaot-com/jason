# PMv4 Stage E - watchdog cannot reactivate retired PMv3 engineering

November 18, 2026. Source-only; not installed in production.

The existing self-heal watchdog requires old user timers and directly
starts jason-support-repair-worker.service after an incident. Disabling
only the PMv3 timers would not retire that worker. The watchdog also
checks old release manager artifacts, old manager timer and old root
host reconcile path, which would be false failures after cutover.

The reviewed source now reads the independently root-owned marker
/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json.

- If missing, all existing timer requirements and worker activation
  remain unchanged. No new PMv4 action is allowed by the watchdog.
- If present but wrong owner, symlinked, writable, unreadable, or not
  accepted by the pinned root-owned PMv4 unit-admission script, the
  watchdog DENIES engineering activation. It does not fall back to
  the PMv3 service, even if ordinary production health probes pass.
- If present with exact root acceptance, worker remediation switches
  to jason-pmv4-engineering.service using the SAME shared production
  transaction mutex and no-block systemd call.
- In the accepted mode, release manager timer/source convergence,
  required user timers and root reconcile path are checked against
  reviewed PMv4 names. Missing source/active units still FAIL; a
  relabeled service is not assumed to provide actual parity.

The new source preserves the old watchdog architecture, incident
fingerprints, bounded retries and case handling. It does not replace
a recovery engine, change Ticket Core/MCP, bypass drift, unfreeze,
reboot or grant provider/Owner authority.

47 focused tests cover original watchdog behavior, invalid marker
fail-closed handling, no PMv3 restart under a valid marker, strict
new target output verification, production-lock preservation and
replacement source convergence. The installed watchdog remains
unchanged until a separate root-accepted old/new six-unit transaction.

Still required: migrate the root host reconciliation backend so it
cannot reinstall old PMv3 workers, adapt release manager host source
and real release scheduling, run isolated old-disabled parity and
bounded rollback, then obtain the one exact Owner release approval
for the entire Stage E retirement transaction. NO production switch
has happened as a result of this source-only change.
