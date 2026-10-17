# Bounded nonblocking systemd exporter activation

## Incident

The approved QuickBooks Production read-only release at source
`f0338832747f56080ac54202f9fa866be1eb9103` entered production
on 2026-10-15. The root host reconciliation record
`release-f0338832747f-ef07b8423efc.json` reports that all ten
exporter ports were independently checked free and the first seven
recreated exporters passed exact owned listener checks, but the
synchronous `systemctl enable --now jason-status-exporter.service`
exceeded its 25-second timeout. The protected reconciler rejected the
release (`HOST_RECONCILE_FAILURE`, `rc=124`). This is a systemd
activation-job timeout, **not** an acceptable monitored endpoint.
The controller's existing bounded recovery only handled the later
`port has no listener, MainPID=0` probe; it could not run when
`enable --now` timed out before that probe.

## Scope and contract

Exporter unit enablement and service start are separated into
`systemctl enable` and `systemctl start --no-block` commands,
each with an explicit 15-second timeout. The second command queues
systemd activation without synchronously waiting for the start job,
but **does not count as successful activation**. The canonical existing
`release_exporter_port_guard.py` must independently prove the
listening port is owned solely by the allowlisted service's MainPID.
If the port is completely free and systemd MainPID is 0, the existing
bounded recovery now queues up to two `restart --no-block` attempts,
rechecking the owner after each. An unrecognized/foreign port owner,
persistent no listener, any systemd communication error, enabled-unit
failure, or unexpected runtime condition still fails host reconciliation
and triggers the Release Manager's verified rollback. All services are
again checked active after exporter activation; CCC must separately
show all targets up and certify all other controls.

No control unit is manually modified on the live host, no unmanaged
process is terminated, no release evidence is rewritten, no monitoring
thresholds are relaxed, no accounting writes are allowed. This is
protected core source and requires new PR CI, exact SHA owner review,
independently verified preproduction, and root-governed promotion.

## Validation

The existing shell-helper behavioral tests execute the actual helper
in isolation with fake `systemctl`, `timeout` and independent port
guard, covering transient startup, persistent absence, and foreign
listener failures. An additional source contract verifies separate
bounded enable and nonblocking start, use of strict owned-port evidence
and terminal active-unit certification. Run full host-reconcile,
release-manager, CCC, rollback, drift and exporter guard regressions.

Integration coordination: #1112, #1436, #1453.

## 2026-10-17 incident: status exporter must not wait on authority-health job

In the failed `de5b94ca9dd9` release transaction, source preproduction and
post-deploy CCC passed, but the downstream documentation-publisher request
failed, initiating automatic rollback. The root-owned rollback host
reconciler stopped all ten allowlisted exporters and later failed at
`jason-status-exporter.service`: the strict MainPID/listener guard saw
`MainPID=0` and no owned listener on port 9464 until its finite retry
budget was exhausted. Later-listed usage exporters (ports 9465/9466)
remained stopped, and the drift watchdog correctly opened the breaker.

The status exporter's canonical unit ordered its start **After**
`jason-openclaw-authority-health.service`. That separate full-integrity
job takes over two minutes and may already be active during rollback.
An exporter start queued behind it can therefore outlast the bounded
ownership probes without actually having failed. This creates a timing
dependency that the metrics exporter does not technically require.

The source fix removes **only that ordering dependency**, retaining
`Requires=docker.service`, its immutable working directory, restricted
service user, read-only paths, restart rules and the existing independent
socket/MainPID ownership gate. The exporter continues to derive
`jason_openclaw_authority_operational_health` from the actual snapshot:
a missing snapshot reports **0** (unhealthy), with age **-1**.
Starting metrics exposure early cannot promote a stale/missing authority
snapshot into a green result.

The exact observed rollback defect and its successor fix are tracked in
Project Jason issue #1440. This configuration is **production control
infrastructure**; the change requires protected CI, separately reviewed
preproduction and exact owner authorization before production restart.
No live unit, runtime source, root control file or circuit breaker is
changed by committing the fix.

Integration coordination for the 2026-10-17 follow-up: #1331, #1453,
#692. PR #1331 adds bounded exporter-reconciliation contract assertions
in the same test module. Preserve both its existing ownership/cadence
regressions and this independent service-ordering contract on merge; do
not replace the newer main-based tests with an old branch snapshot.
