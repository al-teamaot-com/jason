# Bounded Host Exporter Reconciliation

**Incident:** [GitHub #1437](https://github.com/al-teamaot-com/jason/issues/1437). On October 14, 2026, QuickBooks Stage 1 was preproduction-approved, but host reconciliation failed after switching both containers. The system journal showed repeated `EADDRINUSE` failures for two systemd-managed exporters. The subsequent host rollback reconciliation failed at the same activation step. The existing production runtime and MCP containers were subsequently restored to original SHA `2087dd3898b17638659c8f975006290e4f2951c2`; the root-managed circuit breaker was independently revalidated closed. The historical release record still correctly reports `failed` and `rollback_verified=false`.

## Bounded repair contract

The host reconciler always operates with root-governed exact-SHA approval. It must:

1. Stop **only** the ten declared Jason system exporter units, with an explicit maximum duration per unit. Do not terminate processes based solely on script names or broad user matching.
2. Wait for the exact declared TCP listener of each exporter to disappear. A listener belonging to an unknown process, an uninspectable socket, or a surviving prior exporter remains a **blocker**, not something to kill.
3. Start each managed unit and verify its TCP socket PID exactly matches systemd's nonzero `MainPID`. A successful HTTP request, enabled state, or transient `systemctl start` return is insufficient.
4. Fail closed if the port is occupied by another process, cannot be inspected, or fails to come up within the bound. Include exact host-reconciliation step, unit, result, and systemd exit status in root worker evidence. Never clear release circuit breakers or release records in this checker.
5. Retain all existing immutable release, CCC, monitoring, owner review, rollback, host reconciliation, and provider-mutation boundaries.

The checker is `tools/release_exporter_port_guard.py`. It is part of the immutable candidate source, invoked only from the already-authorized root host reconciliation path; it cannot start, stop, or kill anything on its own.

## Acceptance and safe progression

- Unit tests exercise real local TCP socket enumeration, transient listening and port drain, unexpected PID, invisible owner, unknown unit, command failure, and static activation ordering.
- An isolated operator read-only check against existing live exporters verifies expected systemd MainPID/socket ownership without modifying services.
- Run the required protected GitHub CI and new exact-SHA preproduction and rollback-readiness tests.
- **No direct host changes:** only the canonical Release Manager may deploy. For the next attempt use a **new** reviewed source SHA, not a retry of the failed `release-3ab8d7dda8c507c8` record.
- The owner must record the new exact SHA material review, and production pre/post CCC must validate the new revision. The first release preserves `quickbooks-sandbox-read-v1`. Only after its verified closeout may the separately prepared Production read-only profile be considered.
- Failures in the activation path must produce diagnosable unit evidence and leave the protected rollback process active. Do not claim the previous failure record had a successful rollback.

**Note:** Three historical `tools/tests/test_release_manager_atomic_surfaces.py` failures reproduce against the unmodified Stage 1 baseline. These are tracked separately from this repair and are not newly introduced.


## Subsequent root-cause evidence: authority snapshot timeout

In the next governed Stage 1 promotion, all ten exporter port-free and
post-start ownership checks passed. The root worker then failed at
`system_service_activation` on `jason-openclaw-authority-health.service`,
`rc=124`. This is `timeout`'s expiration, not a failed health check.
Systemd historical executions completed successfully after about 134-136
seconds (e.g., 18:11:59 to 18:14:15 ET), exceeding the host installer's
hard-coded 120-second `systemctl start` bound.

For the named authority-health check only, the host installer permits a
bounded 180-second `systemctl start`, still requiring the service to
actually complete and pass; the other maintenance services retain 120
seconds. The root reconciler retains its 360-second overall cap. No check is
skipped, run asynchronously, or marked successful because it merely started.
Retain failed release records from prior exact SHA attempts.
