# Jason Standard Playbook Template

This document is the canonical default template for new Project Jason operational playbooks.

This template is paired with `Jason-Playbook-Runtime-Automation-Contract.md`. New playbooks inherit the shared runtime mechanics defined there rather than reimplementing them.

## Default-use rule

When a request is to build, create, design, or plan a **Jason playbook**, start from this template unless the requester explicitly specifies another structure. Preserve the sections even when a particular section is marked `Not applicable`, so playbooks remain comparable, auditable, and easy to implement.

Do not treat this template as execution authority. All playbooks remain subject to the Jason Constitution, Central Orchestrator, exact requester grants, provider/client isolation, approval requirements, disruption controls, and `direct_provider_access=false`.

## Runtime inheritance rule

Before adding logic to an individual playbook, ask whether the behavior is domain-specific or should be common to all playbooks.

Common behavior belongs in the shared runtime/contract, including:
- queue ownership and work-start lifecycle;
- active-work-slot handling;
- object/CI association;
- persisted state;
- waiting/recheck scheduling;
- retry counting;
- duplicate suppression;
- note layout;
- governance/authority gates;
- human handoff;
- terminal-state readback;
- common observability.

A new playbook should mostly declare trigger, expected state, evidence questions, classifications, domain-specific gates/remediation, and authoritative verification.

## Standard manifest

Every playbook should provide these fields near the top, initially in Markdown or YAML and later in a machine-readable registry when implemented:

```yaml
playbook:
  id: <stable_id>
  name: <human_name>
  version: <semantic_version>
  owner: <operational_owner>
  target_type: <ticket|endpoint|user|site|service|provider_object>
  trigger:
    provider: <source>
    match: <exact rule>
  ownership:
    while_open: <Jason|source_queue|conditional>
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: <n>
  recheck:
    enabled: true|false
    cadence: <duration>
    stale_after: <duration>
  verification:
    authoritative_source: <source>
    success_condition: <condition>
  completion:
    terminal_disposition: <Complete|Human Review|other>
  autonomy:
    allowed_branches: []
    approval_bound_branches: []
    disruptive_branches: []
```

---

# Jason Playbook: [Playbook Name]

## 1. Section Goal

Define exactly what Jason should be able to accomplish.

**Goal:**  
[Example: Process a specific monitoring alert from initial investigation through verified resolution or escalation.]

**Success means:**
- [criterion]
- [criterion]
- [criterion]

Do not consider the Section Goal complete until all acceptance criteria have been demonstrated and documented.

---

## 2. Trigger

Define exactly when this playbook applies.

Examples:
- Autotask ticket title contains: `[exact text/pattern]`
- DRMM alert type: `[alert]`
- Queue: `[queue]`
- Device/site condition: `[condition]`

Jason must confirm the trigger matches before starting the playbook.

---

## 3. Scope and Boundaries

### In Scope
- [systems/providers]
- [ticket/device types]
- [authorized diagnostics]
- [authorized remediation]

### Out of Scope
- [excluded systems/actions]
- disruptive actions unless separately approved
- unrelated tickets/devices
- direct provider access outside Jason governance

Preserve:
- `direct_provider_access=false`
- Central Orchestrator authority
- exact requester grants
- provider/client isolation
- audit trail
- existing approval rules

---

## 4. Initial Identification

Before troubleshooting:
1. Identify the exact Autotask ticket or triggering object.
2. Identify the client.
3. Identify the affected asset/device/user.
4. Run the **global device-association gate**:
   - preserve and validate an existing configuration item when present;
   - if a device is applicable but no configuration item is linked, resolve exactly one same-company active Autotask configuration through authoritative DRMM-to-Autotask evidence and associate it before substantive diagnostics;
   - if multiple candidates exist or identity is uncertain, set `state = identification_blocked`, document the evidence/candidates, and stop rather than guessing;
   - if no device is genuinely applicable, explicitly document `No applicable device association`.
5. Resolve the object against the authoritative provider.
6. Confirm there is no ambiguity, duplicate, stale object, or mismatched asset.
7. Record relevant ticket/alert timestamps and external IDs.
8. Immediately before the first ticket-specific diagnostic, remediation, or verification action, run the **global ticket-work-start lifecycle**:
   - move the ticket to queue **Jason**;
   - set status **In Progress**;
   - set Work Type **Remote Support**;
   - require post-mutation readback;
   - if the ownership transition fails, do not continue substantive work as though ownership succeeded.
9. Do not conflate queue ownership with endpoint availability. A matching playbook may claim/own an offline ticket when its ownership policy requires that. Apply endpoint-online or continuous-online requirements as diagnostic/remediation gates, not as a universal prerequisite for queue ownership.
10. Before substantive ticket-specific diagnostics, require the global work-start transition/readback defined by the shared runtime contract.

If the affected object cannot be identified confidently:

`state = identification_blocked`

Document and escalate rather than guessing.

---

## 5. Expected State

Define what healthy should look like.

Examples:
- required software installed
- required service running
- device online
- expected policy assigned
- expected backup occurring
- expected security agent version
- expected configuration present

Jason should know what condition it is trying to restore before taking remediation actions.

---

## 6. State Model

Every playbook should have explicit persisted states.

Suggested base states:

`detected -> owned -> identified -> diagnosing -> classified -> waiting | blocked | remediating | verifying | human_review | escalated | complete`

Add playbook-specific states when required.

State should survive conversation boundaries, scheduled rechecks, technician handoffs, and service restarts where practical. Jason must not repeat completed steps unnecessarily.

Persist at minimum:
- current playbook state;
- last meaningful observed-state fingerprint;
- active job/correlation identifiers;
- next recheck condition/time;
- last ticket-documentation fingerprint.

A recheck that produces no meaningful state/evidence change updates persisted state only; it does **not** create another ticket note. The persisted recheck record remains the audit evidence that the check occurred.

Waiting is a first-class state. Where safe, waiting tickets should release their active-work slot while retaining the queue ownership declared by the playbook. Resume from persisted state rather than restarting completed work.

---

## 7. Diagnostic Workflow

For each diagnostic step define:

### Step [#]: [Name]

**Purpose:**  
[What question does this answer?]

**Evidence source:**  
[Autotask / DRMM / IT Glue / Entra / provider / etc.]

**Command/read/component:**  
[Exact capability or component where known]

**Expected result:**  
[Healthy condition]

### Decision

If `[condition A]`:  
-> [next state/action]

If `[condition B]`:  
-> [next state/action]

If evidence is inconclusive:  
-> gather additional evidence or escalate.

Do not infer a failure solely from an alert if authoritative evidence can verify it.

A successful authoritative read that returns no matching object is valid negative evidence, not automatically a connector failure. Playbooks must distinguish an authoritative empty result from a failed/unauthorized/unavailable read.

---

## 8. Decision Gates

Define conditions that must be satisfied before remediation.

Examples:
- device online
- continuously online for required time
- correct endpoint confirmed
- software actually missing/unhealthy
- required site variable exists
- no active conflicting maintenance
- requester has required authority

If a gate fails, Jason must not skip it simply to reach remediation.

---

## 9. Remediation

Define the exact authorized remediation.

For each remediation:

**Action/component:**  
`[exact action]`

**Preconditions:**
- [condition]
- [condition]

**Approval classification:**
- read-only
- non-destructive
- modifying
- disruptive

**Verification required:**  
[how success is proven]

Submission of a job is not proof of success. Jason must verify terminal completion and retrieve actual output where available.

---

## 10. Retry Policy

Define bounded retry behavior.

Example:
- Maximum full remediation attempts: `2`
- Do not retry blindly.
- Document the result of each attempt.
- A second attempt should only occur when evidence indicates retrying is reasonable.

After the limit is reached:

`state = escalated`

No endless remediation loops.

---

## 11. Periodic Rechecks

If the playbook requires waiting:

**Recheck interval:**  
[example: hourly]

**Recheck condition:**  
[what Jason checks]

**Stop conditions:**
- issue resolves
- ticket closes
- escalation threshold reached
- asset becomes stale/retired
- maximum waiting period reached

Prevent duplicate scheduled jobs for the same ticket/playbook instance.

Unless the playbook explicitly requires otherwise, entering a normal waiting state should release the active-work slot without changing the playbook's declared queue ownership.

Periodic polling is not itself a documentable event. Write a new ticket note only when the recheck changes evidence, classification, action, dependency, authority state, escalation state, or terminal disposition.

---

## 12. Aging / Stale Condition

Define when a normal waiting condition becomes abnormal.

Example:

If a device remains offline for more than `[X days]`, investigate:
- retired device
- replaced device
- duplicate CI
- stale DRMM object
- renamed/reimaged endpoint
- broader connectivity problem

Do not continue periodic retries indefinitely.

---

## 13. Dependency Handling

If remediation depends on missing configuration, credentials, variables, licensing, documentation, or another team:
1. Confirm the dependency is actually missing.
2. Search for an existing open dependency ticket.
3. Do not create duplicates.
4. If none exists and Jason is authorized, create one.
5. Cross-reference the dependency ticket.
6. Put the original playbook into `state = blocked`.

Never fabricate missing configuration or borrow values from another client.

---

## 14. Documentation Requirements

Every meaningful **state transition** must be documented in the original Autotask ticket or authoritative case record when one exists.

Do not document unchanged polling/recheck results repeatedly. Before creating a Jason-authored note, compare a durable normalized fingerprint for the same ticket/playbook/note class. If the normalized content is unchanged, suppress the duplicate note and retain the recheck only in persisted operational state.

Document:
- what Jason checked
- why
- exact command/read/component
- target
- timestamp
- result
- Job ID / correlation ID where available
- relevant StdOut/StdErr
- interpretation
- resulting decision
- next step

### Technician-scannable note layout

Where practical, Jason-authored operational notes should put the technician's decision context before diagnostic detail.

Preferred field order:
1. **STATUS** — current state in plain language.
2. **NEXT STEP** or **ACTION REQUIRED** — what happens now and who must act.
3. **WHEN / ESCALATION** — next recheck, deadline, or aging threshold when applicable.
4. **KEY EVIDENCE** — only the facts necessary to understand the decision.
5. **WHAT JASON DID** — concise summary of diagnostics/remediation.
6. **CHANGES MADE** — explicitly say **None** when no modifying action occurred.
7. **JASON STATE** — persisted machine state for audit/resume.

Rules:
- Do not bury an actionable technician decision inside a diagnostic paragraph.
- If no technician action is required, say that explicitly near the top.
- If human action is required, use **ACTION REQUIRED** and state the exact decision/action.
- Keep detailed diagnostics below the action summary.
- Use note titles that expose the state, such as `Jason - [Playbook] - Waiting Approval`, `Human Review Required`, `Verification`, or `Resolution`.

Suggested note titles:
- `Jason - [Playbook] - Asset Validation`
- `Jason - [Playbook] - Diagnostic`
- `Jason - [Playbook] - Recheck`
- `Jason - [Playbook] - Remediation`
- `Jason - [Playbook] - Verification`
- `Jason - [Playbook] - Escalation`
- `Jason - [Playbook] - Resolution`

### Secret Handling

Never document:
- passwords
- API keys
- tokens
- private keys
- secret variable values

Document only presence/status where appropriate.

---

## 15. Failure Handling

Failed steps must be documented just as thoroughly as successful ones.

Examples:
- provider read failed
- endpoint could not be matched
- component failed
- StdOut unavailable
- job timed out
- required variable missing
- evidence contradictory
- authority denied

Do not silently skip failed steps.

---

## 16. Escalation Criteria

Define exactly when Jason stops automatic processing.

Examples:
- retry limit reached
- disruptive action required
- identity/asset cannot be resolved
- required dependency cannot be created
- unexpected provider result
- repeated service failure
- conflicting evidence
- issue falls outside playbook scope

Escalation note should summarize:
- symptoms
- evidence
- diagnostics
- actions attempted
- results
- current state
- recommended technician next step

---

## 17. Verification

Remediation success and incident resolution are not necessarily the same thing.

Define authoritative resolution evidence.

Examples:
- successful backup
- alert cleared
- service healthy
- EDR reporting correctly
- user confirmed functionality
- event no longer occurring
- monitoring condition returned to healthy

Do not close solely because a command/component returned success.

---

## 18. Completion Criteria

The ticket/case may only complete when:
1. the correct object was identified;
2. required diagnostics completed;
3. root cause or reasonable resolution classification established;
4. remediation succeeded where required;
5. authoritative healthy-state evidence exists;
6. all actions/results are documented;
7. final resolution note is present;
8. the requested terminal ticket disposition has been independently/readback verified against the authoritative PSA/provider state.

A resolution statement in prose is never proof that the ticket actually reached its intended terminal state. If the terminal write or readback fails, do not mark the playbook complete; persist a blocked/escalated state with the failed terminal transition as the next required action.

---

## 19. Final Resolution Note

Summarize:
- original condition
- root cause
- relevant device/client state
- diagnostics performed
- remediation performed
- number of attempts
- final verification
- verification timestamp
- final disposition

---

## 20. Required Capabilities

List the narrowest Jason capabilities required.

Examples:
- Autotask ticket search/read
- Autotask internal note create
- Autotask ticket update
- Autotask ticket create
- DRMM endpoint search/read
- DRMM software/service read
- DRMM component discovery
- DRMM component execution
- job status
- StdOut/StdErr
- IT Glue reads
- scheduled recheck support
- persisted playbook state

Do not broaden capabilities solely for convenience.

---

## 21. Acceptance Test

Define a controlled real-world test.

**Test target:**  
[device/ticket]

Prove:
1. trigger detection
2. object association
3. documentation
4. diagnostics
5. decision gates
6. waiting/recheck behavior where applicable
7. remediation
8. retry limits
9. failure handling
10. verification
11. completion/escalation
12. scheduled-job cleanup
13. persisted state
14. duplicate-note suppression on unchanged rechecks
15. terminal ticket-state readback verification
16. queue ownership independent of active-work capacity
17. active-slot release/resume while waiting
18. authoritative negative-evidence handling
19. client-boundary rejection
20. persisted restart/resume behavior

Do not modify unrelated production objects during testing.

---

## 22. Section Goal Closure

When the acceptance test succeeds:
- document implementation
- document capability additions
- document test results
- record known limitations
- update Grafana / Project Jason Section Goal
- mark the Section Goal complete

Any unresolved capability gaps should become explicit follow-up TODO items rather than hidden exceptions.

---

## 23. Autonomous Execution Eligibility and Owner Review

Playbook authors/technicians may define and test the proposed autonomous safe branch, but they do not grant standing autonomy.

Document:

- branch-level autonomy: exact allowed branches, approval-bound branches, and disruptive branches;
- exact playbook version;
- exact allowed capabilities;
- explicit actions that remain approval-bound;
- standing-safe component requirements, if any;
- acceptance-test result and known limitations;
- review status describing the promoted branch boundary.

When the source-controlled production entry is ready for autonomy review, it may nominate `autonomy.activation=autonomous`. That nomination causes no unattended authority by itself. Jason requires a separate durable owner promotion.

The preferred production approval path is a Teams Adaptive Card sent to a configured owner identity. The card is bound to the exact playbook/version/policy/capabilities and source-entry fingerprint. Owner **Approve** creates the matching durable promotion mechanically; **Deny** and **Request Changes** create no promotion.

Any material playbook/version/capability/fingerprint change requires a new owner review before the changed branch can execute autonomously.
