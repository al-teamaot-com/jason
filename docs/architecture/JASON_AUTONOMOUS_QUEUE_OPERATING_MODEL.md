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

The implementation does not bypass existing Autotask/DRMM governed execution paths. A bounded production worker is now deployed for separately promoted operational playbooks.
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

As of 2026-09-26, items 1-10 have been completed for the current production autonomous operating model. All ten production playbooks presently registered have a separately promoted safe branch. Each version remains independently gated, and autonomy is branch-specific rather than blanket playbook authority. A promoted diagnostic branch does not authorize a remediation, disruptive, cleanup, closure, or client-facing branch that is not explicitly included in that playbook's production scope.

## Autonomous workload identity

Unattended execution must not impersonate the interactive technician who originally discussed a ticket. Jason uses a dedicated non-human workload identity (`jason-autonomy-worker`) evaluated by JKD-001. The identity receives only exact capability grants. Approval-required actions additionally require a separate durable owner promotion for the exact playbook version and capability, followed by a short-lived exact-action reservation in the governed execution ledger. The Central Orchestrator still binds and consumes the concrete execution plan once.

Source metadata is not authority. Setting `autonomy.activation=autonomous` in the playbook catalog is only an eligibility declaration. Standing execution requires a separate durable `PlaybookAutonomyApproval`; absence, expiration, revocation, version drift, capability drift, or duplicate active promotion records fail closed.

## Queue ownership and priority

The Autotask queue adapter resolves queue IDs and ticket priority ordering from live Tickets field metadata rather than relying on provider IDs as ordinal values. Initial AOT metadata validation on 2026-09-25 confirmed Critical, High, Medium, Normal, and Copy/Print are ordered by provider `sortOrder`. Jason normalizes that ordering into a provider-neutral priority score.

Selection order is: urgent work first; then Jason-owned work; then normalized priority; then age/stable identity. This means normal work already owned by Jason is resumed before newly discovered work, while Critical/Emergency work may trigger reconsideration. Among equally urgent work, Jason-owned work remains preferred.

Tickets assigned to a human in another queue are not claimed. An assigned ticket outside the Jason queue is eligible only when its assignee is authoritatively configured as a Jason-owned Autotask resource. Canonical `service.resource.search` / `service.resource.read` are now production-active, and the 2026-09-25 production identity proof established `29682930` as **Jason ReadWrite** and `29682926` as **Jason Read Only**; `29682899` is **Lindsey Collins**. Production autonomous queue ownership is bound to Resource `29682930`. Assignment ownership must continue to be resolved authoritatively and must never be inferred from recurring numeric IDs.

## Shadow-mode production checkpoint - 2026-09-25

A governed read-only production reconciliation was run across Jason, Help Desk I, Help Desk II, Monitoring Alert, and Client Portal queues. No ticket, device, note, job, alert, or provider object was mutated.

Findings:

- Jason queue: 11 In Progress, 0 New, and no current Updated-by-Email/Emergency items in the checked status set.
- The current queue includes recognized shadow playbooks for Datto EDR/AV, Security Log Self-Heal, DNS Agent, VulScan Missing Patch, BackupIQ, and Unexpected Shutdown.
- Active Jason tickets for POST errors, Idle Log Off, and Low Disk Space do not yet have complete registered playbook source coverage in this branch. Idle Log Off hardening is tracked by #245; the Low Disk Space execution-plan blocker is tracked by #261.
- Other queues contain human-assigned work, unassigned work, and tickets carrying the same opaque Autotask resource ID seen on Jason-owned tickets. Because Autotask Resources is not yet a governed readable resource, Jason does not infer that opaque ID is itself Jason.
- The shadow checkpoint originally had no operational playbook promotion. The EDR/AV health-only branch was separately promoted on 2026-09-25. On 2026-09-26, the remaining production playbooks received bounded safe-branch implementations, validation, durable promotions, and production deployment. The current registry therefore has no shadow-only playbooks among this ten-playbook production set, while unsafe/remediation sub-branches remain separately gated.

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


## Production autonomous execution acceptance - 2026-09-25

The autonomous execution substrate is production-proven. This is a platform/governance acceptance, not blanket playbook authority.

### Controlled target

- Client: XYZ Test Company
- Company ID: `1158`
- Ticket: `T20260925.0051`
- Ticket ID: `141233`
- Capability: `service.ticket.note.create`
- Workload principal: `jason-autonomy-worker`
- Autotask API Resource: `29682930` / Jason ReadWrite

### Successful governed execution

- Execution ID: `exec_autonomy_559d20ebdeaa40f2bb5ccafc4a1cce61`
- Correlation ID: `corr_autonomy_4b0af623d006492b87e2f3d4ca4ed133`
- Approval ID: `approval_mcp_aebd2009640046d782f932ff8d80debd`
- Idempotency key: `idem_mcp_action_2e536a88873d4e0ea70f84737c21d4fc`
- Intent/action fingerprint: `31fe3a9edada5dae203c08c264d8fd766ebf6ece86c71a12b6ef5c0bf301e555`
- Execution-plan fingerprint: `42c98ab374d904f7f5cf46dea9e8c02bb873eeb56549aa435d5dc3630369ae7d`
- Provider: `autotask_internal_note`
- Provider attempts: exactly 1
- Governed execution state: `succeeded`
- Failure reason: none

The normalized provider execution plan targeted only:

`POST /V1.0/Tickets/141233/Notes`

with the exact internal-note payload approved for the acceptance run.

### Provider/readback proof

Autotask created note `30509332`.

Readback proved:

- `creatorResourceID=29682930`;
- `impersonatorCreatorResourceID=null`;
- `readbackVerified=true`;
- verified `ticketNoteId=30509332`;
- verified `creatorResourceId=29682930`;
- verified `impersonatorRecorded=false`.

Independent governed `service.ticket.notes.search` observed the same durable note.

The direct API-user attribution is intentional for the autonomous workload. Human-originated internal-note writes continue to use requester impersonation; autonomous Jason uses the dedicated API Resource directly and must not self-impersonate.

### Duplicate suppression and cleanup

A second acceptance run recognized the exact existing marker and returned the already-verified path with duplicate suppression. No second provider write occurred.

At the conclusion of that acceptance checkpoint:

- every temporary acceptance `PlaybookAutonomyApproval` was revoked;
- all temporary acceptance JKD-001 grants were revoked;
- no broad autonomous mutation grant remained;
- operational queue processing remained shadow-only until the later EDR/AV operational promotion documented below.

### Production code boundary

The accepted production MCP line includes:

- #325 — exact autonomy acceptance information-release boundary;
- #328 — direct API-user attribution for autonomous internal notes;
- #329 — provider-envelope verification extraction.

Production MCP source at the accepted checkpoint: `d3bdf0ced712e6602a46b14ddbaa6e83a139ebc6`.

### Admission rule going forward

This proof establishes that Jason can execute a governed autonomous provider write safely. It does **not** authorize arbitrary writes or automatically promote existing playbooks.

Each operational playbook must still provide, for its exact version and capability set:

1. deterministic playbook match;
2. current governance pass;
3. exact JKD-001 authority;
4. durable owner promotion;
5. bounded execution-plan authorization;
6. provider-specific safety/preflight;
7. independent verification;
8. duplicate/idempotency protection;
9. red-team acceptance;
10. explicit suspension/revocation behavior.

The production model is therefore **per-playbook-version and per-safe-branch testing and promotion**, not generic autonomy enablement. The current ten production playbooks all have a promoted safe branch, but each retains explicit non-autonomous boundaries where remediation, disruptive action, automatic closure, or another higher-risk capability has not been accepted.

## Production worker activation - 2026-09-25

The bounded production worker is active for the separately promoted EDR/AV health-only branch. It scans Help Desk I, Help Desk II, Monitoring Alert, and Jason-owned work, with a default maximum of two active work items. Source defaults remain fail-closed; production explicitly enables `JASON_AUTONOMY_WORKER_ENABLED=true` and `JASON_DATTO_COMPONENT_EXECUTION_AUTONOMY_ENABLED=true`.

The first real reconciliation found a normalization mismatch between canonical endpoint evidence (`resource_id`) and provider-native Datto evidence (`uid`). PR #349 corrected the normalization to accept `resource_id`, `uid`, or `deviceUid` while preserving exact CI UID and hostname equality requirements. The corrected worker was deployed at revision `aaa536cef3e10edac8a1cc41595caee19be570c6` and verified healthy.

Full production operating details, recovery rules, current authority, and the procedure for promoting additional playbooks are documented in `docs/operations/JASON_AUTONOMOUS_TICKET_WORKER.md`.


## Production safe-branch coverage - 2026-09-26

The current production registry has autonomous activation for the following exact playbook versions:

- `datto_edr_av@1.3.0`
- `dns_agent_diagnostic@1.0.0`
- `security_log_self_heal@1.0.0`
- `post_error_investigation@1.0.0`
- `unexpected_shutdown@1.0.0`
- `backupiq_endpoint_backup@1.0.0`
- `low_disk_space@1.0.0`
- `vulscan_missing_patch@1.0.0`
- `disk_bad_block_event_7@1.0.0`
- `idle_log_off@1.0.0`

This list means each playbook has at least one unattended branch that has passed source review, runtime tests, durable owner promotion, and production deployment. It does **not** mean the whole playbook is autonomous.

Examples of intentionally retained hard boundaries:

- EDR/AV threat response and disruptive remediation remain gated.
- DNS repair/install remains gated.
- Security Log alert/SOC side-effect cleanup remains gated.
- POST firmware/hardware changes and automatic closure remain gated.
- Unexpected Shutdown automatic closure remains gated.
- BackupIQ reinstall/policy/retention/restore/delete operations remain gated.
- Low Disk cleanup/file deletion remains gated, and servers remain human-reviewed.
- VulScan patch approval/install/Windows Update repair/reboot remain gated.
- Disk Event ID 7 physical-disk mapping/repair/alert resolution remain gated.
- Idle Log Off setter execution remains per-run approved because of future user-session impact.

The architectural invariant is: **autonomy stops at the branch boundary, not at the ticket boundary**. A matching ticket may be claimed and worked automatically through its exact approved branch, then transition to an escalated/waiting/approval state when the next step requires authority that is not part of that branch.
