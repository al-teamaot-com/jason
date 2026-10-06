# Jason Playbook: GPT Insights - Help Desk Tech Assist

**Version:** 0.2.0  
**Status:** Production scope; exact durable owner promotion required  
**Mode:** Advisory, internal-note only

## 1. Section Goal

**Goal:** Give an AOT technician useful, evidence-grounded help on eligible Help Desk I New tickets that Jason cannot autonomously resolve, without claiming the ticket, changing ticket state, performing remediation, or asking a human for facts Jason can obtain itself.

**Success means:**
- every eligible non-recurring Help Desk I ticket in status `New` receives one internal `GPT Insights` note;
- material evidence changes refresh that same Jason-owned note rather than creating update-note clutter;
- recurring tickets never reach this playbook;
- no client notification, ticket update, or disruptive action is performed.

## 2. Trigger

- Queue: **Help Desk I**
- Status: **New**
- Autotask ticket source is not **Recurring**
- No applicable promoted remediation playbook matches the ticket.

## 3. Scope and Boundaries

### In Scope
- read-only ticket, configuration, endpoint, and bounded same-client evidence;
- one internal `GPT Insights` note;
- governed update of that same Jason-owned internal note when material evidence changes.

### Out of Scope
- Help Desk II;
- any status other than New;
- Autotask source **Recurring**;
- ticket queue/status/assignment mutation;
- client-facing communication;
- component execution or remediation;
- disruptive actions.

Preserve Central Orchestrator authority, `direct_provider_access=false`, exact requester grants, provider/client isolation, and auditability.

## 4. Initial Identification

1. Identify the exact Autotask ticket.
2. Confirm queue = Help Desk I and status = New.
3. Confirm the queue source already excluded source label Recurring.
4. Resolve the associated configuration item only when an exact same-company active association is available.
5. If identity is uncertain, record the limitation in the insight rather than guessing.
6. Do not claim or move the ticket.

## 5. Expected State

The ticket has exactly one current `GPT Insights` internal note containing the best available evidence and recommendations. If evidence has not materially changed, no note mutation occurs.

## 6. State Model

`eligible -> evidence_collected -> insight_created | insight_current | insight_updated | blocked`

Persist the material-evidence fingerprint in the operational augmentation store. A restart or local-state loss must not create a duplicate base note when Autotask already contains `GPT Insights`.

## 7. Diagnostic Workflow

### Step 1: Ticket classification
Classify as network, printing, performance, login, application, or unknown from ticket evidence without inventing a cause.

### Step 2: Device evidence
When an exact associated device exists, collect authoritative online state, last-seen evidence, OS, and category-specific read-only facts.

### Step 3: Correlation
Use bounded same-company ticket evidence where it materially reduces technician effort.

### Decision
- material evidence available -> render/update insight;
- evidence unchanged -> no write;
- evidence unavailable -> state the limitation and avoid unsupported claims.

## 8. Decision Gates

Before note creation/update:
- exact Help Desk I queue;
- exact New status;
- recurring source exclusion already applied;
- no promoted remediation playbook applies;
- exact durable v0.2 owner promotion exists;
- update target, if present, is uniquely identified as the Jason-owned `GPT Insights` internal note.

## 9. Remediation

Not applicable. This playbook is advisory only.

Allowed mutations:
- `service.ticket.note.create`
- `service.ticket.note.update`

The update capability may touch only an existing Jason-owned internal note after exact creator, visibility, title, and note-ID verification.

## 10. Retry Policy

No provider mutation retries. One governed attempt per execution plan. Failed note writes fail closed and are retried only by a later normal worker cycle after state is re-read.

## 11. Periodic Rechecks

The normal worker cadence may reassess eligible New tickets. A recheck with the same material fingerprint performs no note mutation.

## 12. Aging / Stale Condition

When the ticket leaves New status, GPT Insights stops. The playbook does not continue refreshing tickets already being actively handled.

## 13. Dependency Handling

Missing device association or unavailable read-only evidence is recorded as a limitation; Jason does not fabricate identity or configuration.

## 14. Documentation Requirements

Maintain one internal note titled **GPT Insights**. The living note contains current evidence, assessment, limitations, and recommended next steps.

Every successful note revision is also recorded in Jason's mutation audit with:
- ticket ID;
- note ID;
- prior and revised body;
- prior and revised SHA-256;
- provider readback result.

## 15. Failure Handling

Fail closed if:
- note identity is ambiguous;
- target note is not internal;
- creator identity is not Jason's exact execution identity;
- provider update permission is unavailable;
- post-mutation readback does not match.

## 16. Escalation Criteria

GPT Insights itself does not escalate operational tickets. Failures are surfaced to Jason support/audit while leaving the ticket untouched.

## 17. Verification

Success requires authoritative Autotask readback showing:
- the intended note ID;
- title `GPT Insights`;
- noteType=3;
- publish=2;
- exact intended description;
- exact Jason creator attribution.

## 18. Completion Criteria

For each eligible scan, the playbook is complete when the current material fingerprint is represented by the one verified internal note or no write is needed because the note is already current.

## 19. Final Resolution Note

Not applicable. GPT Insights is an advisory augmentation, not the incident-resolution playbook.

## 20. Required Capabilities

- `service.ticket.notes.search`
- `service.ticket.search`
- `service.configuration.read`
- `endpoint.device.read`
- approved read-only diagnostic capabilities where category-specific evidence warrants them
- `service.ticket.note.create`
- `service.ticket.note.update`

## 21. Acceptance Test

Prove:
1. eligible Help Desk I New non-recurring ticket receives one base note;
2. same evidence creates no duplicate or update;
3. material evidence change updates that same note ID;
4. technician/client/workflow notes cannot be updated;
5. Help Desk II does not receive GPT Insights;
6. non-New status does not receive GPT Insights;
7. source Recurring is excluded upstream;
8. update audit preserves before/after bodies and hashes;
9. post-write readback verifies internal visibility and Jason ownership;
10. no ticket-field/client/disruptive mutation occurs.

## 22. Section Goal Closure

Close only after source tests, protected CI, exact durable owner promotion, production deployment, and controlled live Help Desk I verification are complete.

## 23. Autonomous Execution Eligibility and Owner Review

Production nomination: `autonomy.activation=autonomous`.

Exact promoted scope:
- playbook: `gpt_insights_tech_assist@0.2.0`
- policy: `playbook-autonomy:gpt_insights_tech_assist`
- capabilities: `service.ticket.note.create`, `service.ticket.note.update`

Any material version, capability, trigger, ownership rule, or notification-boundary change requires new owner review.
