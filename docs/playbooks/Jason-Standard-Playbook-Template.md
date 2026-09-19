# Jason Standard Playbook Template

This document is the canonical default template for new Project Jason operational playbooks.

## Default-use rule

When a request is to build, create, design, or plan a **Jason playbook**, start from this template unless the requester explicitly specifies another structure. Preserve the sections even when a particular section is marked `Not applicable`, so playbooks remain comparable, auditable, and easy to implement.

Do not treat this template as execution authority. All playbooks remain subject to the Jason Constitution, Central Orchestrator, exact requester grants, provider/client isolation, approval requirements, disruption controls, and `direct_provider_access=false`.

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
4. Resolve the object against the authoritative provider.
5. Confirm there is no ambiguity, duplicate, stale object, or mismatched asset.
6. Record relevant ticket/alert timestamps and external IDs.

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

`identified -> waiting -> diagnosing -> blocked -> remediating -> verifying -> complete`

or:

`escalated`

Add playbook-specific states when required.

State should survive conversation boundaries, scheduled rechecks, technician handoffs, and service restarts where practical. Jason must not repeat completed steps unnecessarily.

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

Every meaningful step must be documented in the original Autotask ticket or authoritative case record when one exists.

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

If a failed/blocked step is caused by a demonstrated tooling gap (missing fact, inadequate component output, repeated component failure, unsafe side effect, duplicate tooling, or missing provider capability), create or strengthen the matching Component Engineering request through the generic engineering workflow. Do not require a technician to request the script improvement, and do not duplicate an already-open problem key.

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
7. final resolution note is present.

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

When a playbook cannot complete, route the blocker through the generic Completion Gap Router rather than inventing playbook-specific backlog behavior. Use the standardized reason classes so the blocker routes to Component Engineering, Communication Template Engineering, provider capability backlog, Documentation Assurance, human decision, or bounded recheck. Unknown blocker reasons must fail closed rather than be guessed. If a specialized durable request already exists, link its request ID to the completion gap instead of creating a parallel duplicate.
