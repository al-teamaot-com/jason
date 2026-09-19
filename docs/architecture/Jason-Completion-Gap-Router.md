# Jason Completion Gap Router

## Section Goal

Give every PlaybookRun one generic, governed way to answer **why Jason could not complete the work** and route that reason to the right follow-up system without duplicating work or granting new execution authority.

## Gap classes and routes

| Gap class | Route |
| --- | --- |
| `component_tooling` | Component Engineering |
| `communication_template` | Communication Template Engineering |
| `provider_capability` | Capability backlog / provider development |
| `documentation` | Continuous Documentation Assurance |
| `human_decision` | Approval / escalation |
| `temporary_condition` | Bounded recheck |

Unknown reason classes fail closed rather than being guessed.

## Deterministic reason mapping

Standard blocker reason classes map deterministically, including:

- `component_output_inadequate`, `component_missing`, `component_repeated_failure` → Component Engineering;
- `approved_template_missing`, `communication_template_missing` → Communication Template Engineering;
- `capability_unavailable`, `provider_capability_missing`, `provider_write_unavailable` → capability backlog;
- `documentation_missing`, `documentation_stale`, `documentation_conflict` → Documentation Assurance;
- `human_decision_required`, `approval_required`, `authority_or_human_required` → human decision;
- `endpoint_offline`, `provider_temporarily_unavailable`, `temporary_evidence_unavailable` → bounded recheck.

## Durable record

`CompletionGapRecord` is stored under `/var/lib/jason/openclaw/completion-gaps`. It records a stable problem key, class, route, lifecycle, recurrence count, affected playbooks/runs/tickets, evidence refs, linked request IDs, timestamps, and recheck time where applicable.

The same active `problem_key` is strengthened instead of duplicated. Multiple active records with the same key fail closed.

## Playbook integration

`PlaybookRunCoordinator.route_completion_gap(...)` is the generic playbook entry point. The router persists the gap ID and route into PlaybookRun metadata and records a `completion_gap_routed` step.

Specialized systems remain authoritative for their own work items. For example, Component Engineering still owns component design requests and Communication Template Engineering still owns proposed client-template requests. The completion gap links to those request IDs rather than replacing them.

## State behavior

- Component/tooling, communication, provider capability, and documentation gaps place the run in `blocked` with the gap class as the blocked reason.
- Human decisions place the run in `blocked` / waiting for human action; routing does not approve anything.
- Temporary conditions require a concrete bounded recheck timestamp and place the run in `recheck_pending`.

## Governance

The router performs no provider reads or writes and cannot authorize remediation. Central Orchestrator, client/provider isolation, Component Control, approval policy, and disruptive-action protections remain authoritative.

## Observability

Dashboard UID: `jason-completion-gaps`.

Exporter port: 9474.

Prometheus exposes aggregate/secret-safe gap metadata and recurrence counts. Ticket IDs, run IDs, device IDs, evidence refs, and detailed summaries are intentionally withheld from metrics.

## Acceptance

Source acceptance must prove deterministic classification, de-duplication, temporary-condition recheck enforcement, human-decision waiting behavior, PlaybookRun linkage, secret-safe exporter output, and Grafana JSON validity.
