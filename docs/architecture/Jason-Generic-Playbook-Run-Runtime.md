# Jason Generic PlaybookRun Runtime

## Section Goal

Provide one persisted, provider-neutral state engine for recurring Jason operational playbooks so work can survive conversation boundaries, service restarts, approvals, scheduled rechecks, and technician handoffs without repeating completed steps or weakening governance.

## Runtime contract

`implementation/autonomous_remediation/playbook_runtime.py` defines the generic `PlaybookRunRecord` and `FilePlaybookRunStore`.

A run contains the minimum durable orchestration context needed to resume safely:

- stable run ID;
- playbook ID and exact version;
- Autotask ticket ID and company boundary;
- exact device identity when known;
- trigger class;
- current state;
- completed steps and evidence references;
- attempt count;
- approval status and exact approval ID when pending;
- blocked reason class;
- scheduled recheck time;
- verification status; and
- terminal outcome.

The generic runtime performs no provider calls and grants no execution authority. Playbook-specific logic remains subject to the Central Orchestrator, exact requester grants, provider/client isolation, approval policy, disruption controls, bounded attempts, and `direct_provider_access=false`.

## Canonical states

`triggered -> identifying -> diagnosing -> deciding -> awaiting_approval -> remediating -> verifying -> complete`

Supported side states are `waiting`, `recheck_pending`, `blocked`, `escalated`, and `cancelled`.

Transitions are explicit and fail closed. A terminal run cannot accept additional steps or attempts.

## Persistence

The default persistence path is `/var/lib/jason/playbooks/runs`, one JSON file per run. Writes use a temporary file plus atomic `os.replace` so a process interruption cannot intentionally expose a partially written run record as current state.

Duplicate run IDs are rejected. Run IDs are filename-safe and path traversal is rejected.

## Approval binding

A run entering `awaiting_approval` records one exact approval ID. A response can mark the run approved only when the supplied approval ID exactly matches the pending ID. This state primitive does not itself execute the approved action; execution still routes through normal Jason governance.

## Rechecks

A run may persist `recheck_at` and enter `recheck_pending`. Scheduling/execution of the future wake-up remains the responsibility of the governed scheduler/automation layer. The persisted run prevents the resumed workflow from starting over or duplicating already completed work.

## Grafana privacy boundary

`infrastructure/showcase/playbook_exporter.py` reads persisted runs and exports only low-cardinality aggregates:

- total non-terminal active runs;
- runs by playbook/state;
- runs by playbook/approval status;
- blocked runs by playbook/reason class; and
- pending rechecks by playbook.

Run IDs, ticket IDs, company IDs, device IDs, approval IDs, evidence references, notes, and raw provider data are not Prometheus labels.

## Initial acceptance — 2026-09-19

Unit coverage proves persistence/resume, invalid-transition rejection, exact approval binding, scheduled recheck state, terminal-state protection, duplicate-run rejection, safe run IDs, aggregate live-run telemetry, and non-exposure of run/ticket/device/approval identifiers in Prometheus.

A synthetic HOSTS-file-drift run is the initial reference acceptance. It exercises the generic runtime only and performs no provider call or production remediation.

## Synthetic reference acceptance result

On 2026-09-19, a temporary `hosts_file_drift` v0.1.0 run completed the generic path `triggered -> identifying -> diagnosing -> deciding -> awaiting_approval -> remediating -> verifying -> complete`. The test persisted and reloaded state, required the exact pending approval ID, recorded one bounded synthetic attempt, and ended `outcome=resolved`. No provider call, endpoint mutation, ticket mutation, alert mutation, or production run-state file was used. The live-run exporter correctly exposed the intermediate `awaiting_approval` aggregate and later returned zero active runs after completion while withholding the synthetic run, ticket, device, approval, and evidence identifiers.

## Central Orchestrator bridge

`implementation/autonomous_remediation/playbook_coordinator.py` adds a provider-neutral coordinator and `GovernedPlaybookExecutor`. The bridge accepts an already-constructed governed orchestration request, calls the existing Central Orchestrator exactly once, and persists the returned status, correlation reference, reason class, and provider-attempt count into the run. It does not construct provider requests, bypass approvals, or retry failed/denied actions. Approval-required, denied/human-required, and failed results place the run into a blocked state for explicit continuation.

The public MCP governed-action contract is intentionally unchanged; playbook context remains server-side rather than becoming caller-controlled action metadata. The bridge pre-validates the requested post-success state before dispatch so an invalid state transition cannot occur after a provider mutation has already been attempted.

## Production composition status — 2026-09-19

The normal `build_runtime_application()` composition now constructs a `PlaybookRunCoordinator` backed by `RuntimeSettings.playbook_runs_path` (default `/var/lib/jason/playbooks/runs`) and attaches it to the internal `RuntimeHttpApplication` composition object. This is an internal service reference only; no new HTTP/MCP surface is exposed and no playbook is automatically activated by this wiring. Production filesystem ownership/deployment remains an onsite activation step.

## Production observability activation — 2026-09-19

`/var/lib/jason/playbooks/runs` is present and writable by the Jason runtime account (`al`), and the live playbook registry is installed at `/var/lib/jason/playbooks/registry.json`. `jason-playbook-exporter.service` is enabled and active on TCP 9468 using exporter build version 2. Prometheus target `jason-playbooks` is healthy, and Grafana has provisioned the updated `jason-playbook-control-center` with live-run, approval, blocker, and recheck panels. Current active-run count is zero, as expected before a controlled live playbook acceptance. Production runtime activation of the coordinator itself remains separate because the active runtime checkout contains unrelated uncommitted changes that were deliberately not overwritten during observability deployment.
