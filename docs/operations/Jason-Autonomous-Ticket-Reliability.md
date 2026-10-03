# Jason Autonomous Ticket Reliability

**Status:** Pre-production implementation for issue #770. Production acceptance is intentionally pending.

## Objective

Jason's ticket worker must continuously discover, claim, advance, wait, resume, and complete eligible Autotask work without requiring a technician to notice that the worker has stopped.

A healthy HTTP process is not sufficient evidence that ticket autonomy is healthy. Ticket-worker liveness and workload progress are independent operational requirements.

## Core invariants

1. The operational ticket worker runs independently from support repair, release/deployment, shadow analysis, and other auxiliary maintenance.
2. Every due worker cycle records a durable start and either a durable completion or failure.
3. A worker heartbeat older than two normal worker intervals is degraded health.
4. A dead or stale ticket-worker process is restarted independently with a bounded restart budget.
5. Runtime `/healthz` reports degraded when ticket autonomy remains unhealthy instead of returning a false green state.
6. If active capacity is available and an actionable ticket remains `eligible_now`, the scan must select work or fail the admission invariant.
7. A ticket-specific failure, offline endpoint, governance block, or waiting dependency cannot stop unrelated candidates from being evaluated.
8. Autotask queue/status and Jason's durable worker state must agree. State transitions that change PSA status require provider readback verification.
9. Waiting states preserve the exact ticket, company, configuration item, endpoint, playbook, and resume phase.
10. Waiting work uses durable targeted wakes or explicit recheck deadlines. Full queue scans remain a discovery and reconciliation safety net rather than the only timer.

## Runtime structure

The HTTP-serving process does not execute autonomy maintenance.
When operational ticket autonomy is enabled, the runtime launches:

- a dedicated `jason-ticket-autonomy` child for the operational ticket worker;
- an independent auxiliary-maintenance child for unrelated maintenance services; and
- a lightweight local supervisor for ticket-worker liveness.

The supervisor can restart only the ticket-worker child. It does not grant provider authority and does not perform ticket or endpoint actions.

## Durable heartbeat

The operational work database contains one `autonomy_worker_heartbeat` record with:

- last cycle start;
- last successful completion;
- last failure;
- bounded error detail;
- last duration;
- consecutive failure count; and
- last completed scan cycle ID.

A queue/provider read failure is therefore visible as a failed cycle rather than silently disappearing inside the maintenance loop.

## Waiting and resume behavior

Examples of durable waiting states include:
- `waiting_device_access:<resume_phase>`;
- `waiting_patch_approval`;
- `waiting_patch_window`; and
- `waiting_recheck:<resume_phase>`.

Device-access waits schedule an exact `endpoint.device.read` wake. Timed waits schedule a durable queue-reconcile wake and carry an explicit next-recheck time where applicable.

When a dependency clears and capacity exists, Jason restores the authoritative Autotask active status before resuming the preserved phase.

## State synchronization

Examples:

- active Jason work -> `In Progress`;
- patch not approved -> `Waiting`;
- endpoint unavailable -> `Waiting Device Access`;
- human handoff -> Help Desk I / `Human Review`;
- verified completion -> playbook-appropriate terminal status.

A note describing one state while Autotask remains in another is a defect, not an acceptable transient outcome.

## Admission assurance

Candidate evaluation remains bounded, but exhausted evaluation/admission budgets explicitly classify deferred candidates rather than leaving them silently eligible.

After each scan, Jason checks the admission invariant. Free active capacity plus unselected `eligible_now` work raises an operational failure and is reflected in worker health.
## Production acceptance still required

This implementation is not production-authorized by this document.

Before production promotion, acceptance must prove at minimum:

- continuous scan heartbeat;
- recovery from a dead worker;
- recovery from a stale/hung worker;
- two-slot refill;
- offline candidates do not starve online work;
- waiting-device automatic resume;
- patch-approval wait and resume;
- timed recheck wake behavior;
- ticket-specific provider/identity failure isolation;
- restart recovery with persisted work;
- consistent Autotask and worker state; and
- zero unexplained eligible-but-idle cycles during the observation window.

Production promotion remains subject to Jason's normal governed release process and explicit production authorization.
