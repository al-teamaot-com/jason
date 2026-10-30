# Ticket worker isolation and supervision (P0 #770)

## Objective
Keep Autotask admission/advancement independent of unrelated maintenance tasks. This is a partial resilience repair; it does not change the set of approved playbooks or action permissions.

## Lifecycle
When `JASON_AUTONOMY_WORKER_ENABLED=true`, runtime starts one dedicated spawned ticket-maintenance process and a separate auxiliary maintenance process. The parent supervises ticket-worker liveness using the existing `autonomy_ticket_scan_cycle` ledger. A scan older than the two-interval threshold (minimum two minutes) degrades `/healthz` and requests bounded ticket-worker process recovery; no auxiliary service is restarted as part of ticket-specific recovery. Parent shutdown stops the supervisor and children.

`maintenance_profile=ticket_worker` only ticks operational ticket maintenance; `auxiliary` ticks existing non-ticket maintenance. The HTTP process does not execute the ticket worker. Missing/stale successful scan state is not reported as healthy after startup grace. The restart budget is limited to three attempts per 10-minute window.

## Authority and limitations
No new Autotask, EDR, Datto, Teams, patch, or endpoint permission is granted. Existing per-ticket authorization, exact approval, retry and readback requirements remain authoritative. Tickets lacking promoted matching playbooks remain unclaimed; separate #770 work must deliver bounded diagnostic coverage, human escalation and acceptance that proves ticket advancement.

## Verification
Focused worker/supervisor/HTTP/maintenance tests: 140 PASS. Composition/deployment tests: 29 PASS. A temporary live test or intentionally killing a production worker is prohibited. Production Manager must validate exact candidate scope, source/build, independent protected rollback identity, and governed provider read canaries before promotion. Following promotion, require two consecutive scheduled ticket-scan cycles and documented actual ticket admission/disposition evidence, not merely a healthy HTTP endpoint.

## Integration coordination
Overlapping open integration PRs #2125 and #2128 add routine governed write composition; #2126 adds inert Windows Time shadow maintenance composition. Their additions are outside the patch's existing service list, but must be reconciled against merged protected main before release, preserving every unrelated service and feature flag.
