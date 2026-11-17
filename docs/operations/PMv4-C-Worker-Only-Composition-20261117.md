# PMv4 C — separate the ticket-only runtime from HTTP/approval/auxiliary processes

**State:** source-only improvement, not an external Ticket Core deployment. No production service, worker, provider credential, owner approval, SQLite schema, or release control is modified by this PR.

## Prior defect and correction

The standalone `jason_runtime.ticket_worker_service` correctly owns its own process and the shared dispatch child `flock`, but it calls `run_autonomy_maintenance_process(..., maintenance_profile="ticket_worker")`. Before this PR, `build_runtime_application` still constructed full HTTP/Teams ingress, callback/replay/continuation stores, approval request transports, and miscellaneous auxiliary runtime objects before selecting the ticket-only maintenance at the end.

The reviewed source now returns `TicketWorkerComponentRuntime(maintenance=...)` **immediately after** the existing governed `CentralOrchestrator` has been constructed for the `ticket_worker` profile. It uses the same existing `build_autonomous_completion_notifier` and `build_autonomy_worker_maintenance` calls, exactly the same registered capabilities and execution ledger, and binds the existing `TicketAttentionRelay`. No second ticket engine or new authority service is introduced. The HTTP/auxiliary profile still follows the original unchanged path. The worker-only branch refuses an erroneously disabled ticket worker.

## Actual durable-state inventory (offline, no provider calls)

A fresh disposable test runtime proved the worker still initializes: authority, Microsoft bindings, client boundaries, orchestration events, governed execution, playbook promotion, reflection, resolution memory, targeted wakes, operational tickets, and ticket split (11 SQLite databases plus some WAL/SHM sidecars). These are not all ticket-owned. **Do not mistake this change for complete isolation.** The new state-budget test fails if more stores are introduced to the worker without source review. The HTTP continuation, replay, security audit, universal-approval, and mobile-release stores are no longer opened by the ticket-only profile.

Before any production Stage C cutover, independently scoped state/credential projection or exact native governed access must preserve the original single authoritative identity/approval/orchestration state while separating only worker-owned files. The provider-only runtime may not mount the entire `/var/lib/jason/openclaw` broad state directory. It must use a committed full SQLite/WAL-consistent migration under host and worker locks, and cannot create a second durable owner or duplicate work. See `PMv4-C-Quiesced-Ledger-Handoff-20261117.md` for the tested source-only SQLite primitive.

## Verification and release boundaries

Existing Ticket Core lifecycle tests and all composition tests pass in nonproduction after the change; new tests prove no HTTP service/ingress, no Teams outbox sender, no auxiliary worker, and a bounded actual file-creation set. The live original embedded worker remains installed and healthy. A separate exact Owner release is necessary for any root data migration, change to HTTP worker mode, independent container credentials/mounts, or activation.

## Concurrent implementation coordination

Integration coordination: #2455 #2405 #2395

- PR #2455's dormant IT Glue foundation adds imports and provider invokers upstream of this PR's branch; the worker-only early return retains the original governed registration path.
- PR #2405 adds company classification registration and invoker upstream of the new branch; no overlapping edited lines.
- PR #2395 changes V5 privileged-release approval policy and browser/Teams decision flows in settings and the later HTTP-only branch. This PR does not grant approval or alter these settings. A future merge must retain its independent authorization gates.

Those PRs remain independent and are not implicitly approved by this source-only change. This review is the required concurrent-change record for source merge, not a production release.
