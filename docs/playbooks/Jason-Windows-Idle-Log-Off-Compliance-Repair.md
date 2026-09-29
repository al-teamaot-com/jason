# Jason Playbook: Windows Idle Log Off Compliance / Repair

## Playbook Manifest

```yaml
playbook:
  id: idle_log_off
  name: Windows Idle Log Off Compliance / Repair
  version: 1.1.0
  owner: AOT
  target_type: endpoint
  trigger:
    provider: Autotask / Datto RMM
    match: Idle Log Off compliance alert or exact Jason-owned noncompliance ticket
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 1
  recheck:
    enabled: true
    cadence: normal Jason queue-review cadence
    stale_after: normal support aging threshold
  verification:
    authoritative_source: Datto job/output plus normal DRMM current-alert state
    success_condition: exact setter job succeeds with no stderr and the current Idle Log Off alert clears
  completion:
    terminal_disposition: Complete
  autonomy:
    allowed_branches:
      - identify
      - classify
      - wait
      - recheck
      - resume_on_online
      - remediate_exact_current_noncompliance
      - verify_monitor_clear
      - complete_verified_ticket
    approval_bound_branches:
      - client_specific_override
      - stale_alert_resolution_without_normal_clear
    disruptive_branches:
      - forced_logoff
      - reboot
```

This playbook inherits common work-start, identity, waiting/recheck, active-slot, retry, documentation, verification, human-handoff, terminal-readback, and observability behavior from `Jason-Playbook-Runtime-Automation-Contract.md`.

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

A waiting Idle Log Off ticket remains owned by Jason but releases its active-work slot. Offline cases use the shared `waiting_device_access:idle_log_off_investigate` state and resume from preserved work when the exact DRMM endpoint returns online.

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
11. Exact `idle_log_off@1.1.0` playbook autonomy promotion is active and includes `automation.component.execute`.
12. The current endpoint has exactly one open Idle Log Off alert.
13. The exact setter is source-bound to UID `acc6a240-881d-4655-9470-87f60c8e35e8`, with built-in defaults only.
14. No client-specific variable override, generic PowerShell, reboot, forced logoff, or other component is requested.

If any gate fails, do not improvise.

---

## 9. Remediation

### Remediation A: Missing or broken Idle Log Off control

**Action/component:**  
Set Idle Log Off AOT Ver 02042026-1  
UID: acc6a240-881d-4655-9470-87f60c8e35e8

**Preconditions:** all Section 8 gates pass.

**Approval classification:** playbook-scoped autonomous modifying action with future user-session impact. Installation itself does not immediately force a logoff; the installed control enforces the approved idle-session policy later.

**Authority intent:** Keep this component globally classified `per_run` in Datto Component Control. Do **not** promote it to globally standing-safe.

Autonomous execution is permitted only through the exact owner-promoted `idle_log_off@1.1.0` playbook scope, whose allowed capabilities include `automation.component.execute`. The autonomous worker converts that durable playbook promotion into a short-lived, exact execution approval through the Central Orchestrator.

The autonomous remediation branch is hard-bound to:
- one exact ticket/client/CI/device identity;
- supported Windows workstation/laptop role;
- exactly one current open Idle Log Off alert on that endpoint;
- no monitor/plumbing failure evidence;
- component name `Set Idle Log Off AOT Ver 02042026-1`;
- component UID `acc6a240-881d-4655-9470-87f60c8e35e8`;
- built-in defaults with `variables={}`;
- one automatic setter attempt;
- normal DRMM monitor-clear verification before ticket completion.

The playbook promotion does not authorize this component for any other playbook, target, arguments, or ad-hoc use.

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

- Maximum automatic setter attempts per ticket: 1.
- Never submit a duplicate while the prior job is active.
- Poll the same job to terminal state.
- Retrieve stdout and stderr.
- A provider/job failure does not authorize automatic redispatch.
- A second attempt requires new evidence and a separately reviewed path; the baseline autonomous branch escalates.

No endless loops.

---

## 11. Periodic Rechecks

When waiting:

**Endpoint offline:** move to Waiting Device Access, retain Jason queue ownership, release the active-work slot, and recheck on the normal Jason queue-review cadence. When the exact endpoint becomes online, return to In Progress and resume `idle_log_off_investigate`.

**Setter completed but monitor not yet cleared:** enter the shared `waiting_recheck:idle_log_off_verify_monitor` state, release the active-work slot, and recheck the exact current alert during a bounded 15-minute propagation window.

**Configuration dependency:** any client-specific override or policy ambiguity exits the autonomous remediation branch. Jason does not invent values or broaden the playbook-scoped component authority.

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

After autonomous repair/install:

1. Wait for the exact setter job to reach a terminal provider state.
2. Read both stdout and stderr for that exact job/component/device binding.
3. Require terminal provider success and empty stderr. This proves action execution only; it does not prove incident resolution.
4. Enter `waiting_recheck:idle_log_off_verify_monitor`, release the active-work slot, and observe the exact endpoint's normal DRMM current-alert state.
5. If the Idle Log Off alert clears during the bounded 15-minute propagation window, treat that normal monitor-clear as the authoritative healthy-state evidence for the autonomous branch.
6. If a current Idle Log Off alert remains after the propagation window, do not rerun the setter. Route to monitor/policy investigation.
7. Complete the Autotask ticket only after the alert-clear evidence is present and terminal ticket-status readback succeeds.

The 2026-09-25 controlled acceptance separately proved the underlying scheduled-task mechanism and 240/60 baseline. Jason currently has no dedicated native scheduled-task-detail read capability, so the autonomous v1.1 branch does not claim to perform that direct mechanism inspection on every incident. A future dedicated read capability or standing-safe diagnostic may strengthen verification without changing this completion rule.

Setter job success alone is never incident resolution.

---

## 18. Completion Criteria

Complete the individual incident only when:
1. exact endpoint/CI is proven;
2. applicability is proven;
3. diagnostics distinguish real noncompliance from monitor/plumbing failure;
4. required repair/install succeeded, or no repair was needed;
5. authoritative healthy-state evidence exists from the normal DRMM current-alert state;
6. the exact Idle Log Off alert is no longer open;
7. ticket documentation is complete;
8. any remaining policy/governance engineering item is explicitly tracked rather than hidden.

The playbook's autonomy Section Goal is separate from incident completion and remains open until v1.1.0 source tests, provider-boundary controls, Owner promotion, and controlled production acceptance are complete.

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
9. job stdout/stderr capture followed by normal current-alert monitor-clear verification;
10. ticket completion only after monitor-clear evidence and terminal Autotask readback;
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

The AVMAC-1096 incident is resolved and has no remaining policy-change dependency. At the time of that 2026-09-25 acceptance, the broader playbook remained per-run governed because the setter has future user-session impact. The v1.1.0 design intentionally preserves the component's global per-run classification while proposing a narrower playbook-scoped autonomous authority.

---

## 22. Section Goal Closure

The Section Goal closes when:
- this playbook is merged into Project Jason;
- the preferred setter and built-in-default behavior are production-validated;
- AVMAC-1096 historical acceptance proves the monitor-error, repair, independent-verification, stale-alert, and Autotask closeout mechanics;
- v1.1.0 source acceptance proves exact playbook-scoped setter execution, provider-boundary binding, waiting/recheck behavior, and monitor-clear completion;
- the globally per-run component-control state and the narrower playbook-scoped authority are both documented;
- historical provider-object names are not treated as current without live verification;
- Grafana/Project Jason operational status is updated where applicable;
- known limitations and follow-up engineering items are recorded.

Do not create or preserve a provider-policy remediation task solely from historical ticket text. Create a new Support/TODO item only when a current provider object and an actual unresolved defect are proven.


---

## 23. Autonomous Execution Eligibility

### Current production authority

The previously approved `idle_log_off@1.0.0` scope remains diagnostic-only in production until v1.1.0 completes controlled acceptance and receives exact Owner promotion.

### v1.1.0 proposed playbook-scoped autonomous authority

`idle_log_off@1.1.0` is designed for autonomous execution of the bounded normal-workstation remediation branch.

Required action capabilities:
- `automation.component.execute`
- `service.ticket.note.create`
- `service.ticket.update`

Autonomous branches:
- exact ticket/client/CI/device identification;
- supported Windows workstation/laptop classification;
- current exact Idle Log Off alert confirmation;
- monitor/plumbing-error rejection;
- offline Waiting Device Access and online resume;
- exact `Set Idle Log Off AOT Ver 02042026-1` execution with built-in defaults only;
- Datto job/status/stdout/stderr readback;
- bounded monitor-clear waiting/recheck;
- ticket completion only after the current Idle Log Off alert is no longer open and Autotask status readback succeeds.

The Datto component itself remains globally `per_run` and is **not** standing-safe. The authority comes from the exact Owner-approved playbook/version/capability scope and is converted to an exact short-lived execution approval by the autonomous governance path.

Hard stops / exclusions:
- server, domain controller, RDS/terminal server, kiosk, or unsupported/ambiguous role;
- endpoint offline until it returns online;
- zero or multiple current Idle Log Off alerts;
- monitor/plumbing failure such as Invalid MyFileDestination;
- client-specific variable override;
- component UID/name mismatch;
- non-empty stderr or non-success provider job state;
- current Idle Log Off alert still open after the 15-minute propagation window;
- generic PowerShell;
- reboot;
- immediate/forced logoff;
- policy mutation;
- unrelated component execution.

Any hard stop routes to waiting, blocking, or Human Review as appropriate; it never broadens execution authority.

### Promotion requirement

This document and its tests do not grant production authority by themselves. Promote `idle_log_off@1.1.0` only after the controlled acceptance matrix is green and Owner approval is durably recorded for the exact registry fingerprint and capability set. Any material source/version/capability change requires re-review.
