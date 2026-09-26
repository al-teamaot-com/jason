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
- DRMM monitor/component: Get Idle Log Off Status AOT Ver 08202024
- Current monitor component UID: 2b5de042-a3ec-4721-ba66-e0ca193a3604
- Historical ticket/alert text may include a DRMM policy name. Treat that as historical evidence only; do not assume the named policy still exists or is the current source of the monitor without a live provider read.

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

Authoritative monitor:
- Get Idle Log Off Status AOT Ver 08202024
- UID: 2b5de042-a3ec-4721-ba66-e0ca193a3604
- Datto type: monitor. It is evaluated by DRMM policy/monitoring and cannot be run as an on-demand script or quick job.

Expected normal-cycle result:
- monitor evaluates through DRMM;
- output is syntactically valid;
- Compliant=True.

For immediate post-remediation verification, use approved read-only endpoint evidence instead of trying to execute the monitor on demand. Verify the expected mechanism directly:
- scheduled task AOT_IdleLogOff exists;
- task state is Ready;
- principal is SYSTEM / Highest;
- executable is C:\Temp\MyIdleLogOff\MyIdleLogOff.exe;
- approved baseline arguments are 240 60 (four-hour idle threshold / 60-second warning).

If the normal monitor cycle later reports Compliant=True:
-> state = verifying / healthy.

If the existing alert still carries only historical legacy-setter failure evidence while independent mechanism verification is healthy:
-> classify the alert as stale evidence and resolve only that exact alert through governed alert resolution.

If the normal monitor cycle produces a fresh Compliant=False after verified repair:
-> state = monitor_execution_failure or remediation_failed and investigate the monitor/policy path. Do not blindly rerun the setter.

### Step 4: Check remediation component readiness

**Purpose:** Ensure the current setter can run deterministically.

**Evidence source:** live component catalog and approved component-control metadata.

Confirm:
- exact component name/UID;
- current component version;
- endpoint remains online;
- the approved production baseline is the 02042026-1 setter invoked with its built-in defaults and no legacy variable overrides;
- if any variable override is proposed, every value comes from an authoritative AOT/client source and is validated before dispatch;
- never carry forward the legacy policy's invalid MyFileDestination payload;
- no stale metadata/fingerprint mismatch.

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
8. Use the production-validated built-in defaults unless an authoritative AOT/client requirement explicitly calls for overrides.
9. Never pass the legacy MyFileDestination value/payload. If any override is required, validate it before dispatch.
10. No conflicting maintenance or user-disruptive operation is in progress.
11. Current governance permits the component execution and exact per-run technician approval is present.

If any gate fails, do not improvise.

---

## 9. Remediation

### Remediation A: Missing or broken Idle Log Off control

**Action/component:**  
Set Idle Log Off AOT Ver 02042026-1  
UID: acc6a240-881d-4655-9470-87f60c8e35e8

**Preconditions:** all Section 8 gates pass.

**Approval classification:** modifying configuration action with future user-session impact. It does not immediately force a logoff during installation, but it intentionally enforces idle-session logoff after the configured threshold.

**Authority intent:** Keep this setter per-run approved. Production Component Control review on 2026-09-25 rejected standing-safe promotion with DATTO_COMPONENT_DISRUPTIVE_OR_DESTRUCTIVE_REVIEW_REQUIRED. Do not weaken that guard. Jason may execute this exact setter only when the playbook gates pass and an authorized technician explicitly approves that specific remediation.

**Required variable handling:**
- production acceptance validated the 02042026-1 setter with its built-in defaults and no overrides;
- resulting task arguments were 240 60 (four-hour idle threshold / 60-second warning);
- do not invent CheckForIdleEvery_X_Min, MyIdleTimeInMin, MyWarningTimeOut, or MyFileDestination;
- do not pass the legacy policy's invalid MyFileDestination payload;
- if future client-specific overrides are required, source and validate them authoritatively before execution;
- never expose secrets.

### Remediation B: Stale alert

If independent verification proves the approved Idle Log Off mechanism is healthy and the existing alert contains only historical legacy-setter failure evidence:
- do not run the setter again;
- resolve only the exact stale DRMM alert;
- require alert-resolution readback;
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

1. Wait for the setter job to reach terminal success or classify provider lifecycle evidence safely if Datto leaves a stale job state.
2. Read stdout and stderr.
3. Perform approved read-only endpoint verification of the installed Idle Log Off mechanism; do not attempt to run the monitor as an on-demand component.
4. Require the verified task/mechanism to match the approved baseline: AOT_IdleLogOff, SYSTEM/Highest, expected executable, and arguments 240 60 unless an authoritative override applies.
5. Observe the monitor's next normal DRMM evaluation when available. A fresh Compliant=False after successful mechanism verification is a monitor/policy investigation, not permission to blindly rerun the setter.
6. If the existing alert contains only stale legacy-setter failure evidence and independent healthy-state verification is complete, resolve only that exact alert through governed alert resolution and require readback.
7. Re-read the Autotask ticket and confirm expected completion or document a ticket-status governance blocker.

Setter job success alone is not incident resolution; endpoint-state verification and alert/ticket disposition are required.

---

## 18. Completion Criteria

Complete the individual incident only when:
1. exact endpoint/CI is proven;
2. applicability is proven;
3. diagnostics distinguish real noncompliance from monitor/plumbing failure;
4. required repair/install succeeded, or no repair was needed;
5. authoritative healthy-state evidence exists from the normal monitor cycle or approved independent mechanism verification;
6. exact alert is cleared/resolved with readback;
7. ticket documentation is complete;
8. any remaining policy/governance engineering item is explicitly tracked rather than hidden.

The playbook's autonomy Section Goal is separate from incident completion and remains open while the setter requires per-run approval or the DRMM policy still points to the legacy setter.

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

Potential implementation improvements:
- a dedicated standing-safe Idle Log Off diagnostic component that independently verifies the installed mechanism and configuration without depending solely on the monitoring script;
- a governed DRMM policy-response read/update capability so Jason can verify and replace legacy response-component assignments without direct provider access.

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
6. production-validated built-in-default handling with no legacy MyFileDestination override;
7. exactly one bounded setter execution if the endpoint is truly noncompliant;
8. terminal job/output readback or safe stale-job classification;
9. approved independent mechanism verification, plus normal-cycle monitor observation when available;
10. exact alert resolution with readback;
11. Autotask documentation/completion behavior;
12. retry/failure handling;
13. no reboot, immediate forced logoff, or unrelated endpoint changes;
14. persisted state and cleanup.

A successful test should also verify the older setter is not accidentally selected when the current approved version is available and that the monitor is never dispatched as a quick job.

### 2026-09-25 controlled production acceptance result

AVMAC-1096 / ticket T20260924.0043 established:
- exact endpoint/CI association remained AVMAC-1096 / CI 1583;
- the legacy 08202024 response component failed with Invalid MyFileDestination;
- the preferred Set Idle Log Off AOT Ver 02042026-1 setter was dispatched exactly once under owner approval using built-in defaults;
- setter stdout reported successful staging and scheduled-task creation; stderr was empty;
- independent read-only verification proved AOT_IdleLogOff was Ready, SYSTEM, Highest, executing C:\Temp\MyIdleLogOff\MyIdleLogOff.exe with arguments 240 60 and exit code 0;
- no immediate forced logoff or reboot occurred;
- Get Idle Log Off Status AOT Ver 08202024 was confirmed to be a DRMM monitor that cannot be executed on demand; the attempted quick-job invocation returned HTTP 500 before job creation and is classified as an invalid execution path, not an endpoint failure;
- exact stale alert 9d34f135-8393-4e7f-b2a8-064a1e98eb07 was resolved through governed alert resolution with one provider attempt and verified readback, correlation corr_mcp_action_8b29c0e4cc124ad0be8e0a5e98b0b6cf;
- Autotask then completed T20260924.0043 automatically and the final internal resolution note was written;
- Component Control standing-safe promotion of the setter was rejected by the disruptive/destructive review guard. This is the intended fail-closed result; the setter remains per-run approved;
- the Autotask ticket description historically named DRMM policy AOT - Policy Idle Log Off Monitor/Resolve (Create Ticket), but on 2026-09-25 the operator verified no current DRMM policy exists under that name. The historical ticket text therefore must not be treated as proof of a current provider object or as a required manual change.
- a fresh governed alert read confirmed no current Idle Log Off alert remained on AVMAC-1096 after resolution.

The AVMAC-1096 incident is resolved and has no remaining policy-change dependency. The broader playbook remains per-run governed because the setter has future user-session impact; no additional provider change is required for this incident.

---

## 22. Section Goal Closure

The Section Goal closes when:
- this playbook is merged into Project Jason;
- the preferred setter and built-in-default behavior are production-validated;
- AVMAC-1096 acceptance proves the monitor-error, repair, independent-verification, stale-alert, and Autotask closeout branches;
- the approved component-control state is documented;
- historical provider-object names are not treated as current without live verification;
- Grafana/Project Jason operational status is updated where applicable;
- known limitations and follow-up engineering items are recorded.

Do not create or preserve a provider-policy remediation task solely from historical ticket text. Create a new Support/TODO item only when a current provider object and an actual unresolved defect are proven.


---

## 23. Autonomous Execution Eligibility

`autonomous_allowed: diagnostic_only`

Approval owner: person-al.  
Approval date: 2026-09-26.  
Approved scope: exact `idle_log_off@1.0.0` diagnostic branch using governed endpoint and alert-history reads plus internal ticket work-start/note updates.

The autonomous branch may identify exact ticket/CI/device identity, classify protected/exception roles, distinguish known monitor/plumbing failures such as Invalid MyFileDestination from a genuine noncompliance signal, and document the result. It may not run the setter, independently alter Idle Log Off policy, resolve the alert, force a logoff, run generic PowerShell, reboot, or automatically complete the ticket.

`Set Idle Log Off AOT Ver 02042026-1` remains per-run approved because it intentionally affects future user sessions and Component Control rejected standing-safe promotion. Material changes invalidate this diagnostic approval until re-reviewed.
