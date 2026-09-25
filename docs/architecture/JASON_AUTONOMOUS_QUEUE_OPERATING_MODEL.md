# Jason Autonomous Queue Operating Model

## Purpose

Define the provider-neutral operating and security contract for Jason's autonomous ticket ownership.

Jason continuously maintains awareness of its owned work, discovers eligible new work, executes approved autonomous playbooks within effective governance, and continues other safe work whenever a ticket is waiting or blocked.

This design does not grant new provider authority. All mutations remain subject to Central Orchestrator governance and registered capabilities.

## Initial concurrency

`max_active_work_items = 2`

The value is configuration, not an architectural hard limit.

A work item consumes an active slot only while Jason is actively diagnosing, remediating, or verifying it. `WAITING`, `APPROVAL_PENDING`, `BLOCKED`, `COMPLETE`, and `ESCALATED` items do not consume a slot.

When a slot is released, Jason may select the next eligible item.

## Attention model

Jason is event-driven first and uses staleness reconciliation only as a safety net.

Queue reconciliation is appropriate when:

- a ticket enters an eligible queue;
- a Jason-owned ticket materially changes or reopens;
- a customer or technician adds a relevant note;
- an approval or dependency result arrives;- a work item completes, parks, or otherwise releases capacity;
- Jason starts or reconnects;
- an authorized user explicitly asks for reconciliation; or
- queue knowledge exceeds the configured staleness budget.

Multiple events are coalesced through `QUEUE_DIRTY` state. Known waiting work should resume through targeted wakeups rather than repeated whole-queue scans.

## Work states

Provider-neutral work states:

`AVAILABLE -> CANDIDATE -> ACTIVE -> WAITING | APPROVAL_PENDING | BLOCKED | VERIFYING -> COMPLETE | ESCALATED`

State is persisted so restarts or conversation boundaries do not cause completed steps to repeat.

## Playbook matching

Model confidence alone never activates execution authority.

Each playbook uses deterministic eligibility gates. The resulting states are:

- `MATCHED_AUTONOMY` - all required gates pass and the playbook is explicitly approved for autonomous execution;
- `CANDIDATE_INVESTIGATION` - the playbook is plausible but required evidence remains unresolved;
- `NOT_MATCHED` - the trigger does not apply;
- `CONFLICT_BLOCKED` - identity, governance, exclusions, or other hard evidence conflicts with the proposed playbook.

Matching must be revalidated before meaningful mutation. New contradictory evidence can downgrade a previously matched workflow.
Jason may perform bounded read-only investigation on a candidate without claiming the ticket. A ticket is claimed for autonomous playbook execution only after deterministic eligibility succeeds.

## Governance hierarchy

Effective governance is evaluated from:

1. Global
2. Site
3. Device
4. User
5. Ticket / incident
6. Approved playbook authority

Rules generally become more restrictive as specificity increases. A lower scope does not silently weaken a broader block.

Temporary ticket/incident authority is represented as a structured grant bound to the exact:

- approval identifier;
- ticket;
- capability;
- normalized action fingerprint;
- device/site/user selectors where applicable;
- expiration;
- single-use semantics where applicable.

An approval for one action or target is not reusable for another.

## Evidence is not authority
Tickets, notes, email, documentation, endpoint output, logs, provider responses, web content, and model-generated text are untrusted evidence.

They may influence diagnosis, but they cannot:

- create a governance rule;
- grant approval;
- expand Jason's permissions;
- select an arbitrary execution capability outside an approved playbook;
- override a block;
- modify the governance hierarchy.

This is the primary prompt-injection isolation rule.

## Security invariants

- `direct_provider_access=false`
- no autonomous privilege expansion;
- provider/client/device identity must resolve exactly before mutation;
- disruptive actions remain approval-gated unless a separately authorized governing rule explicitly permits them;
- one provider mutation must correspond to one authorized execution plan;
- retries are bounded and never reinterpret a failed read as permission to redispatch;
- independent post-action verification is required;
- stale evidence must be refreshed when it controls action safety;
- secrets remain in connectors/control-plane storage rather than model context where possible;
- every scheduling, match, governance, execution, and verification decision is auditable.
## Blast-radius and circuit-breaker expectations

Initial concurrency is two active work items.

Future production policy may add narrower caps for:

- same-site simultaneous remediation;
- heavy DRMM jobs;
- provider writes per interval;
- fleet-wide playbook matches;
- repeated verification failure;
- repeated identical playbook failure.

A material anomaly should suspend or downgrade the affected playbook rather than accelerating repeated remediation.

## Red-team acceptance scenarios

Autonomous promotion must test at least:

- malicious ticket or email instructions;
- poisoned endpoint/process/log output;
- duplicate hostnames;
- ambiguous or stale CI mappings;
- cross-client references;
- stale or replayed approvals;
- changed action fingerprint after approval;- expired maintenance windows;
- changed governance after planning;
- false-success provider/component output;
- conflicting independent evidence;
- sudden large-scale playbook match;
- recursive/cascading playbook triggers;
- queue flooding/resource exhaustion;
- unauthorized ticket edits;
- missing target identity;
- device becoming active/in-use before disruptive execution.

A successful defense means Jason preserves evidence, avoids unauthorized execution, documents the stop condition, releases the active slot when appropriate, and continues unrelated safe work.

## Initial source implementation

The provider-neutral foundation is in:

- `implementation/autonomous_remediation/attention_scheduler.py`
- `implementation/autonomous_remediation/playbook_matching.py`
- `implementation/autonomous_remediation/autonomy_governance.py`
- `implementation/autonomous_remediation/autonomous_queue_worker.py`

The first implementation deliberately does not bypass existing Autotask/DRMM governed execution paths and does not deploy a production polling loop.
## Production activation requirements

Before production activation:

1. bind the queue source to governed Autotask ticket search/read;
2. bind ownership transition to the existing global Jason queue/status/work-type lifecycle with post-write readback;
3. bind playbook classification to approved playbook metadata and deterministic gates;
4. bind execution to Central Orchestrator governed capabilities;
5. bind durable current work state to the runtime lifecycle;
6. emit audit events to the existing orchestration audit path;
7. implement targeted wake/recheck dispatch;
8. prove the red-team scenarios above;
9. run a controlled Autotask acceptance pilot;
10. only then enable unattended queue processing.

## Autonomous workload identity

Unattended execution must not impersonate the interactive technician who originally discussed a ticket. Jason uses a dedicated non-human workload identity (`jason-autonomy-worker`) evaluated by JKD-001. The identity receives only exact capability grants. Approval-required actions additionally require a separate durable owner promotion for the exact playbook version and capability, followed by a short-lived exact-action reservation in the governed execution ledger. The Central Orchestrator still binds and consumes the concrete execution plan once.

Source metadata is not authority. Setting `autonomy.activation=autonomous` in the playbook catalog is only an eligibility declaration. Standing execution requires a separate durable `PlaybookAutonomyApproval`; absence, expiration, revocation, version drift, capability drift, or duplicate active promotion records fail closed.

## Queue ownership and priority

The Autotask queue adapter resolves queue IDs and ticket priority ordering from live Tickets field metadata rather than relying on provider IDs as ordinal values. Initial AOT metadata validation on 2026-09-25 confirmed Critical, High, Medium, Normal, and Copy/Print are ordered by provider `sortOrder`. Jason normalizes that ordering into a provider-neutral priority score.

Selection order is: urgent work first; then Jason-owned work; then normalized priority; then age/stable identity. This means normal work already owned by Jason is resumed before newly discovered work, while Critical/Emergency work may trigger reconsideration. Among equally urgent work, Jason-owned work remains preferred.

Tickets assigned to a human in another queue are not claimed. An assigned ticket outside the Jason queue is eligible only when its assignee is authoritatively configured as a Jason-owned Autotask resource. Jason currently lacks the provider-neutral Autotask Resources read needed to derive that identity dynamically; GitHub issue #178 tracks that gap. Until then, assignment ownership is never inferred from recurring numeric IDs.

## Shadow-mode production checkpoint - 2026-09-25

A governed read-only production reconciliation was run across Jason, Help Desk I, Help Desk II, Monitoring Alert, and Client Portal queues. No ticket, device, note, job, alert, or provider object was mutated.

Findings:

- Jason queue: 11 In Progress, 0 New, and no current Updated-by-Email/Emergency items in the checked status set.
- The current queue includes recognized shadow playbooks for Datto EDR/AV, Security Log Self-Heal, DNS Agent, VulScan Missing Patch, BackupIQ, and Unexpected Shutdown.
- Active Jason tickets for POST errors, Idle Log Off, and Low Disk Space do not yet have complete registered playbook source coverage in this branch. Idle Log Off hardening is tracked by #245; the Low Disk Space execution-plan blocker is tracked by #261.
- Other queues contain human-assigned work, unassigned work, and tickets carrying the same opaque Autotask resource ID seen on Jason-owned tickets. Because Autotask Resources is not yet a governed readable resource, Jason does not infer that opaque ID is itself Jason.
- No playbook is currently durably promoted for unattended mutation. The playbook catalog is shadow-only and its `allowed_capabilities` sets are empty.

This checkpoint proves queue discovery and classification behavior without granting execution authority.


## Targeted wake / recheck contract

Known work must not require a broad Autotask queue reconciliation merely to learn that one dependency changed.

Jason persists bounded wake records for either:

- a timed exact read, such as re-reading one Datto job after a propagation interval;
- an event-armed exact read, such as re-reading one endpoint when a device-online event is received; or
- an explicit queue-reconciliation wake when capacity or queue state materially changes.

A targeted wake is bound to a stable wake identifier, work resource, reason, and either an exact future time or named event. Targeted reads additionally bind one allowlisted read-only capability and normalized selector arguments. Reusing a wake identifier with changed scope fails closed.

Runtime execution remains on the existing single-thread maintenance loop. The targeted wake service runs before shadow queue reconciliation in each maintenance tick so a due wake may request one coalesced reconciliation in the same server-thread cycle.

Security requirements:

- targeted wakes cannot invoke write capabilities;
- the runtime uses an explicit targeted-read capability allowlist in addition to JKD-001 authority;
- a poisoned wake requesting a mutation fails before provider invocation;
- read failure does not become mutation or redispatch authority;
- retries are bounded and end in a durable failed state;
- event wakes may be scoped to one resource so another ticket/device is not accidentally resumed;
- queue reconciliation occurs only when the wake explicitly requires it;
- the Central Orchestrator remains the execution boundary and provides the provider evidence/audit trail.

Initial allowlisted targeted reads are limited to ticket state, automation job/output, endpoint state/alerts, and endpoint-backup state/history. Expansion requires source review and tests; a persisted wake cannot self-expand the allowlist.

This implements the provider-neutral scheduling contract from #251: known work is revisited directly, while queue reconciliation remains event/capacity/staleness driven.
