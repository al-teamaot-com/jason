# Jason Playbook: Windows Idle Log Off Compliance / Repair

## 1. Section Goal

**Goal:**  
Jason must process Windows Idle Log Off compliance alerts from identification through verified resolution or escalation. When an endpoint is required by AOT/client policy to have Idle Log Off and the control is missing or broken, Jason should repair or install the control using the approved Datto RMM component, verify healthy compliance, document the result, and close the alert/ticket when appropriate.

**Success means:**
- Jason proves the exact endpoint is subject to the Idle Log Off requirement before changing it.
- Jason distinguishes actual noncompliance from a monitor/component execution failure.
- Missing or unhealthy Idle Log Off is repaired using the current approved AOT component rather than ad hoc scripting.
- The final status check returns a valid compliant result and the related DRMM alert is cleared.
- All actions, job IDs, outputs, interpretations, and blockers are documented.
- No unsupported server, kiosk, shared-session, exception, or ambiguous endpoint is modified.

Do not consider the Section Goal complete until the controlled acceptance test succeeds and the production automation scope is explicitly approved.

---

## 2. Trigger

Primary trigger:
- Autotask ticket title contains: [Get Idle Log Off Status AOT Ver 08202024] - Compliant: False
- DRMM policy: AOT - Policy Idle Log Off Monitor/Resolve (Create Ticket)
- DRMM monitor/component: Get Idle Log Off Status AOT Ver 08202024
- Current monitor component UID: 2b5de042-a3ec-4721-ba66-e0ca193a3604

Also applicable when:
- an existing Jason-owned ticket explicitly reports the Idle Log Off control is missing, broken, or noncompliant; or
- authoritative verification after deployment shows the control is absent or unhealthy.

Jason must confirm the trigger and affected endpoint before beginning substantive work.

---

## 3. Scope and Boundaries

### In Scope
- Managed Windows workstations and laptops that are required by AOT/client policy to have Idle Log Off.
- Autotask/DRMM identification and current-state reads.
- Validation of the DRMM alert and component diagnostics.
- Verification that the endpoint is actually subject to the Idle Log Off standard.
- Execution of the current approved AOT Idle Log Off setter after decision gates pass.
- Re-running compliance verification.
- Resolving the exact DRMM alert and completing the ticket when healthy.

### Out of Scope
- Windows Servers unless a documented client policy explicitly requires this control and a server-safe implementation is approved.
- Kiosks, shared-session/RDS devices, lab systems, service consoles, or other documented exceptions.
- Changing the required idle duration outside documented AOT/client policy.
- Generic/ad hoc PowerShell when the approved component can perform the repair.
- Immediate forced sign-out of an active user.
- Reboot/shutdown.
- Disabling the control.
- Guessing missing component variables or borrowing values from another client.
- Direct provider access outside Jason governance.

Preserve:
- direct_provider_access=false
- Central Orchestrator authority
- exact requester grants
- provider/client isolation
- audit trail
- existing approval and disruption rules

---

## 4. Initial Identification

Before troubleshooting:

1. Identify the exact Autotask ticket and DRMM alert.
2. Identify the client/site.
3. Identify the exact endpoint and operating system.
4. Run the global device-association gate:
   - preserve/validate an existing CI when present;
   - if no CI is linked, resolve exactly one same-company active Autotask CI using authoritative DRMM-to-Autotask evidence and associate it before substantive remediation;
   - if identity is ambiguous, set state = identification_blocked and stop.
5. Confirm the endpoint is a supported Windows workstation/laptop unless an explicit documented exception allows another role.
6. Confirm current online state.
7. Record the alert UID, ticket number, component/monitor identity, and alert diagnostics.
8. Before ticket-specific diagnostics/remediation, run the global ticket-work-start lifecycle:
   - queue Jason;
   - status In Progress;
   - Work Type Remote Support;
   - require readback.
9. If the device is offline, do not claim active remediation work. Set state = waiting_endpoint and recheck later.

---

## 5. Expected State

Healthy state for an applicable endpoint:

- Endpoint is online and uniquely identified.
- Client/site policy says Idle Log Off is required.
- The AOT Idle Log Off control is installed/configured.
- The status monitor returns a valid Compliant=True result.
- Monitor execution itself has no PowerShell/runtime/path/variable error.
- No open DRMM Idle Log Off noncompliance alert remains.
- The configured idle duration matches the approved AOT/client standard.
- No active exception exists for this endpoint.

Current setter components discovered in the live Datto catalog:
- Preferred current setter: Set Idle Log Off AOT Ver 02042026-1
  - UID: acc6a240-881d-4655-9470-87f60c8e35e8
  - variables: CheckForIdleEvery_X_Min, MyIdleTimeInMin, MyWarningTimeOut, MyFileDestination
- Legacy setter: Set Idle Log Off AOT Ver 08202024
  - UID: dec3eab8-52a1-4d5b-8c30-f7dab9ff63bf

The current component description states the standard control logs a workstation session off after four hours of idle time. Jason must still use the authoritative AOT/client configuration values rather than inventing values.

---

## 6. State Model

Persist one of the following states:

identified
-> waiting_endpoint
-> diagnosing
-> not_applicable
-> monitor_execution_failure
-> control_missing
-> control_unhealthy
-> remediating
-> verifying
-> waiting_monitor_clear
-> complete

or:

identification_blocked
policy_ambiguous
dependency_blocked
remediation_failed
escalated

A ticket that is In Progress but waiting/parked does not count as one of the owner's two actively-worked tickets.

---

## 7. Diagnostic Workflow

### Step 1: Validate applicability

**Purpose:** Determine whether the endpoint should have Idle Log Off.

**Evidence source:** Autotask CI, DRMM device record, AOT/client policy/documentation.

**Expected result:** Supported Windows workstation/laptop with no documented exception and a policy requiring Idle Log Off.

### Decision

If required:
-> continue to Step 2.

If clearly exempt/not applicable:
-> state = not_applicable; document evidence; resolve the monitoring false positive where appropriate.

If policy cannot be determined:
-> state = policy_ambiguous; document and escalate. Do not install.

### Step 2: Validate the alert itself

**Purpose:** Determine whether Compliant=False reflects endpoint state or a failed monitor/response script.

**Evidence source:** endpoint.alert.search / exact DRMM alert read.

Inspect:
- alert context
- diagnostics
- response actions
- component/runtime errors
- alert age and duplicates

Examples of monitor/plumbing failures:
- Invalid MyFileDestination
- PowerShell/runtime mismatch
- missing variable/configuration
- script exception
- no valid compliance output

### Decision

If a valid monitor result proves noncompliance:
-> continue to Step 3.

If diagnostics show monitor/response execution failure:
-> state = monitor_execution_failure.
Do not infer that the endpoint lacks Idle Log Off solely from Compliant=False.
Continue with independent verification where available and repair the deployment path before final compliance judgment.

### Step 3: Verify current control state

**Purpose:** Determine whether the Idle Log Off control is present and healthy.

**Evidence source:** exact status component and/or approved read-only verification.

Preferred component:
- Get Idle Log Off Status AOT Ver 08202024
- UID: 2b5de042-a3ec-4721-ba66-e0ca193a3604

Expected:
- component executes successfully;
- output is syntactically valid;
- Compliant=True.

If valid Compliant=True:
-> state = verifying / stale-alert path.

If valid Compliant=False:
-> determine whether control is missing vs unhealthy, then remediate.

If status component itself cannot produce reliable output:
-> state = dependency_blocked or monitor_execution_failure; do not blindly install until enough evidence exists to make the repair safe.

### Step 4: Check remediation component readiness

**Purpose:** Ensure the current setter can run deterministically.

**Evidence source:** live component catalog and approved component-control metadata.

Confirm:
- exact component name/UID;
- current component version;
- required variables;
- approved standard values are available;
- MyFileDestination is a valid approved local path;
- no stale metadata/fingerprint mismatch;
- endpoint remains online.

Preferred repair component:
- Set Idle Log Off AOT Ver 02042026-1
- UID: acc6a240-881d-4655-9470-87f60c8e35e8

Do not default to the legacy 08202024 setter when the current approved setter is available.

---

## 8. Decision Gates

All gates must pass before repair/install:

1. Exact endpoint/CI identity is verified.
2. Endpoint is online.
3. Endpoint is an in-scope Windows workstation/laptop or has an explicit documented policy exception allowing the control.
4. Client/site policy requires Idle Log Off.
5. No endpoint-specific exception exists.
6. Current state is validly noncompliant or sufficiently proven missing/broken.
7. Preferred setter component identity is exact.
8. Required variables/configuration are known from approved AOT/client policy.
9. MyFileDestination is a valid approved path; never pass a blank/invalid value.
10. No conflicting maintenance or user-disruptive operation is in progress.
11. Current governance permits the component execution.

If any gate fails, do not improvise.

---

## 9. Remediation

### Remediation A: Missing or broken Idle Log Off control

**Action/component:**  
Set Idle Log Off AOT Ver 02042026-1  
UID: acc6a240-881d-4655-9470-87f60c8e35e8

**Preconditions:** all Section 8 gates pass.

**Approval classification:** modifying, non-rebooting configuration action.

**Authority intent:** Once this playbook and its controlled acceptance are approved for autonomy, Jason may run this exact bounded setter on an in-scope endpoint that has a matching alert and passes all gates. Until then, normal component approval policy applies.

**Required variable handling:**
- use documented AOT/client values;
- standard idle time currently described by the component as four hours;
- do not invent CheckForIdleEvery_X_Min, MyWarningTimeOut, or MyFileDestination;
- never expose secrets;
- validate MyFileDestination before dispatch.

### Remediation B: Stale alert

If independent verification returns valid Compliant=True:
- do not run the setter;
- resolve only the exact stale DRMM alert;
- verify ticket self-heal/completion.

### Remediation C: Monitor/response plumbing failure

If the endpoint cannot be classified because the monitoring/response component failed:
- document the component error;
- use a safe independent verification if available;
- fix/update the approved component/policy assignment through the normal engineering path;
- do not equate script failure with endpoint noncompliance.

---

## 10. Retry Policy

- Maximum setter attempts per ticket: 2.
- Never submit a duplicate while the prior job is active.
- Poll the same job to terminal state.
- Retrieve stdout and stderr.
- Retry only when evidence indicates a transient/component execution condition that has been corrected.
- If the same deterministic failure repeats, state = remediation_failed and escalate.

No endless loops.

---

## 11. Periodic Rechecks

When waiting:

**Endpoint offline:** recheck on the normal Jason queue-review cadence.

**Setter completed but monitor not yet cleared:** recheck compliance after a bounded propagation interval.

**Approval/config dependency:** recheck only after the dependency changes; do not continuously rerun the setter.

Stop rechecks when:
- valid Compliant=True is proven;
- exact alert clears;
- device becomes stale/retired;
- retry limit reached;
- policy ambiguity requires human decision.

---

## 12. Aging / Stale Condition

If the endpoint remains offline or unresolved beyond the normal support window, evaluate:
- retired/replaced endpoint;
- duplicate CI;
- stale DRMM object;
- device rename/reimage;
- intentional exception;
- broken monitor policy assignment.

Do not repeat remediation indefinitely.

---

## 13. Dependency Handling

Dependencies may include:
- client/site policy confirming applicability;
- approved setter variable values;
- valid MyFileDestination;
- live Datto component metadata;
- component-control approval;
- CI-association write path;
- monitoring policy correction.

If missing:
1. confirm the dependency is actually missing;
2. search existing Support/TODO items;
3. do not duplicate;
4. create a Support item if an expected existing capability is broken;
5. state = dependency_blocked.

Today’s AVMAC-1096 evidence is an example:
- ticket T20260924.0043;
- endpoint AVMAC-1096 / CI 1583;
- exact alert UID 9d34f135-8393-4e7f-b2a8-064a1e98eb07;
- diagnostics report Invalid MyFileDestination;
- this is not sufficient evidence by itself that the endpoint is truly noncompliant.

---

## 14. Documentation Requirements

Use one consolidated internal note per logical work session where practical.

Suggested titles:
- Jason - Idle Log Off - Asset Validation
- Jason - Idle Log Off - Diagnostic
- Jason - Idle Log Off - Remediation
- Jason - Idle Log Off - Verification
- Jason - Idle Log Off - Escalation
- Jason - Idle Log Off - Resolution

Document:
- ticket and endpoint
- applicability result
- alert UID
- status component result
- exact setter/component version
- variables by name and non-secret status only
- job UID/correlation ID
- stdout/stderr
- retries
- verification
- final disposition

Never document credentials or secret values.

---

## 15. Failure Handling

Examples:
- endpoint offline
- CI missing/ambiguous
- status component error
- setter variable invalid
- MyFileDestination invalid
- job failure
- component metadata changed
- output unavailable
- alert persists after verified compliant state
- ticket completion blocked by governance

Every failure must be documented. Do not silently proceed.

---

## 16. Escalation Criteria

Escalate when:
- applicability cannot be proven;
- endpoint role is out of scope;
- a documented exception may apply;
- setter fails twice;
- required variable values are unavailable;
- component/policy engineering is required;
- status remains noncompliant after successful setter execution;
- a disruptive action would be required;
- CI association/governance prevents safe work;
- provider evidence conflicts.

Escalation must state symptoms, evidence, attempted actions, job IDs, current state, and recommended next step.

---

## 17. Verification

After repair/install:

1. Wait for the setter job to reach terminal success.
2. Read stdout and stderr.
3. Re-run the exact Idle Log Off status check.
4. Require a valid Compliant=True result.
5. Confirm no monitor/runtime/config error.
6. Confirm the exact DRMM alert clears or resolve it only after healthy state is proven.
7. Re-read the Autotask ticket and confirm expected completion or document a ticket-status governance blocker.

Setter job success alone is not incident resolution.

---

## 18. Completion Criteria

Complete only when:
1. exact endpoint/CI is proven;
2. applicability is proven;
3. diagnostics distinguish real noncompliance from monitor failure;
4. required repair/install succeeded, or no repair was needed;
5. valid Compliant=True verification exists;
6. exact alert is cleared;
7. ticket documentation is complete;
8. no unresolved playbook-specific blocker remains.

---

## 19. Final Resolution Note

Include:
- original Compliant=False condition;
- whether it was true noncompliance or monitor/plumbing failure;
- endpoint applicability;
- setter version/action if used;
- job/correlation IDs;
- verification result;
- alert status;
- final disposition.

---

## 20. Required Capabilities

Minimum required capabilities:
- service.ticket.read/search/update
- service.ticket.note.create
- service.configuration.read/search
- endpoint.device.read/search
- endpoint.alert.search/resolve
- automation.component.search
- automation.component.execute
- automation.job.read
- automation.job.output.read
- durable component-control approval/readback
- persisted playbook state
- scheduled/recheck support

Potential implementation improvement:
- a dedicated standing-safe Idle Log Off diagnostic component that independently verifies the installed mechanism and configuration without depending solely on the monitoring script.

---

## 21. Acceptance Test

**Primary controlled test target:**  
AVMAC-1096 / Autotask CI 1583 / ticket T20260924.0043.

Known baseline:
- Windows 11 Pro workstation/laptop endpoint is online.
- Alert UID 9d34f135-8393-4e7f-b2a8-064a1e98eb07.
- Alert context reports Compliant=False.
- Alert diagnostics currently report Invalid MyFileDestination.
- Current setter catalog contains both the legacy 08202024 version and preferred 02042026-1 version.

Acceptance must prove:
1. trigger detection;
2. exact CI/device association;
3. applicability to the endpoint;
4. monitor-error classification instead of blindly trusting Compliant=False;
5. current preferred setter selection;
6. deterministic approved variable handling, including valid MyFileDestination;
7. exactly one bounded setter execution if the endpoint is truly noncompliant;
8. terminal job/output readback;
9. valid Compliant=True verification;
10. exact alert resolution;
11. Autotask documentation/completion behavior;
12. retry/failure handling;
13. no reboot or unrelated endpoint changes;
14. persisted state and cleanup.

A successful test should also verify the older setter is not accidentally selected when the current approved version is available.

---

## 22. Section Goal Closure

The Section Goal closes only after:
- this playbook is merged into Project Jason;
- the preferred setter and required variables are production-validated;
- AVMAC-1096 acceptance proves the monitor-error and repair branches;
- the approved component-control state is documented;
- any invalid MyFileDestination policy/component defect is corrected;
- Grafana/Project Jason operational status is updated;
- known limitations and follow-up engineering items are recorded.

Any unresolved component/policy defect becomes an explicit Support item rather than a hidden exception.
