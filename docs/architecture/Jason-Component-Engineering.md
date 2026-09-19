# Jason Component Engineering

## Section Goal

Jason should improve its own operational tooling without waiting for a technician to request a script. When a real ticket/playbook exposes a missing, weak, ambiguous, repetitive, unsafe, or poorly machine-readable component capability, Jason creates or strengthens one durable Component Engineering request, evaluates existing/native options first, designs a bounded solution, tests according to risk, and routes promotion through existing governance.

## Core rule

Technicians do not need to request the improvement. The operational workflow that encounters the gap is the trigger.

The preference order is:

1. use an existing native Kaseya/Datto/Autotask capability when it already provides the needed evidence/action;
2. reuse an existing AOT DRMM component when sufficient;
3. improve an existing AOT component when that is safer and simpler than adding another component;
4. create a new component only when there is a real capability gap.

This is engineering workflow, not execution authority.

## Durable object

`implementation/autonomous_remediation/component_engineering.py` defines `ComponentEngineeringRequest` and `ComponentEngineeringService`.

A request records a stable problem key, request kind, lifecycle, risk, existing component when relevant, desired capability, gap summary, proposed change, acceptance criteria, dependent playbooks, originating runs/tickets/evidence references, recurrence count, and timestamps.

The same active `problem_key` is strengthened rather than duplicated. A repeated occurrence increments `occurrence_count` and attaches the new run/ticket/evidence. Multiple active requests with the same problem key fail closed.

Default store: `/var/lib/jason/component-engineering/requests`.

## Lifecycle

`open -> designing -> testing -> pilot -> awaiting_promotion -> production`

Side/terminal states: `deferred`, `resolved`, `retired`.

Production/promotion is not implied by design completion.

## Risk classes

- `read_only`
- `non_destructive`
- `modifying`
- `disruptive`

Existing Jason disruption policy remains absolute: a component design cannot make reboot, shutdown, forced logoff, user-impacting service restart, or similar disruption autonomous.

## Automatic playbook hook

`PlaybookRunCoordinator.report_component_gap(...)` binds the engineering request to the active PlaybookRun, originating ticket, playbook, and evidence. It persists the engineering request ID back into the run metadata and records whether the request was newly created or strengthened.

Use this hook when the playbook concludes that its tooling is the blocker, for example:

- component output lacks a fact needed for a decision gate;
- a component repeatedly fails or returns ambiguous output;
- a diagnostic component unexpectedly modifies state;
- technicians repeatedly need the same manual follow-up command;
- several components duplicate the same purpose;
- a native provider capability would be safer than script automation;
- a missing read-only diagnostic prevents authoritative verification.

Do not create an engineering request merely because an incident remains unresolved; first establish that the tooling gap is real.

## AI design review

Prompt `PROMPT-ENG-001` v1.0.0 and `ComponentEngineeringDesigner` provide bounded AI design support.

The designer receives only the durable request, supplied existing-component metadata, supplied native-capability metadata, and supplied evidence summaries. It has no provider tools. It returns exactly one recommendation:

- `use_existing`
- `improve_existing`
- `new_component`
- `prefer_native_capability`

It also returns a proposed name, purpose, inputs, machine-readable result fields, safety class, implementation requirements, test plan, acceptance criteria, and promotion-approval requirement.

Modifying/disruptive designs are rejected by deterministic validation if they claim human promotion approval is unnecessary.

## Testing policy

Read-only/non-destructive designs may be eligible for autonomous bounded testing on Owner-approved test devices when the execution component itself is allowed by Component Control and the test cannot create user disruption.

Modifying component tests require the applicable approval and rollback/verification plan.

Disruptive component execution always requires instance-specific technician approval.

No test result is inferred from code review. Jason must record actual job/correlation IDs and authoritative output.

## Component output standard

New/improved components should produce a concise deterministic result block plus normal technician-readable evidence when practical. Recommended form:

```text
JASON_RESULT_BEGIN
status=pass|warning|fail
<bounded key=value facts>
recommended_next_step=<bounded value>
JASON_RESULT_END
```

The exact schema is component-specific. Never emit passwords, tokens, private keys, or secret variable values.

## Grafana

Dashboard UID: `jason-component-engineering`.

The dashboard is observational and shows:

- active request count;
- total request count;
- risk mix;
- durable request inventory;
- recurrence/occurrence counts;
- active request kinds.

Prometheus deliberately excludes ticket IDs, run IDs, device IDs, evidence refs, gap narratives, proposed code, and secret-bearing content.

## Provider write gap

Jason currently has governed Datto component discovery and execution, but no governed capability to create/update DRMM component definitions. Therefore Jason can detect, persist, design, review, and prepare/test against existing components now, but automated publication of a new/improved component remains a separate provider capability gap. This must not be bypassed with undocumented/private Datto web endpoints.

## First operational acceptance candidate

The disk-space PlaybookRun for `T20260919.0012` revealed a concrete tooling-quality issue: `Get free hard drive (disk) space AOT Ver 09182025-1`, used as a diagnostic, created `HKLM:\SOFTWARE\AOT` and recorded an alert timestamp while collecting current disk state. Jason should treat this as evidence for a read-only diagnostic improvement request rather than waiting for a technician to request a new script.
