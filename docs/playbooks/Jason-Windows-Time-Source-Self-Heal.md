# Jason Playbook: Windows Time Source Self-Heal

```yaml
playbook:
  id: windows_time_source
  name: Jason - Windows Time Source Self-Heal
  version: 0.1.0
  owner: AOT IT Operations
  target_type: provider_object
  trigger:
    provider: Datto RMM
    match: open comp_script_ctx alert whose diagnostics contain "Time source mismatch." and "not in approved list:"
  ownership:
    while_open: conditional
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 2
  recheck:
    enabled: true
    cadence: 15 minutes
    stale_after: 24 hours
  verification:
    authoritative_source: dedicated Windows Time diagnostic plus exact DRMM monitor state
    success_condition: endpoint reports approved time source and exact triggering alert is no longer open
  completion:
    terminal_disposition: Complete or Human Review
  autonomy:
    allowed_branches:
      - detect
      - identify
      - classify
      - recurrence_detection
      - read_only_diagnostics
      - recovered_verification
    approval_bound_branches:
      - rediscover_resync
      - restore_domain_hierarchy
      - restart_w32time
      - exact_alert_resolution
    disruptive_branches:
      - reboot
      - domain_rejoin
      - secure_channel_reset
      - domain_controller_time_configuration
```

## 1. Section Goal

**Goal:** Detect a Windows endpoint whose current time source is outside the approved source set, establish why the endpoint is not using its expected time hierarchy, perform only bounded approved repair, independently verify healthy synchronization, and resolve only the exact triggering DRMM alert.

**Success means:**
- exact alert, client/site, endpoint UID, and hostname are proven;
- the alert is treated as a symptom rather than proof of root cause;
- recurrence is detected from authoritative DRMM history;
- ordinary domain-member failures can be safely classified for bounded repair;
- domain-controller, trust, DNS/DC-discovery, GPO, and disruptive branches fail closed to Human Review;
- remediation success is independently verified by a dedicated Windows Time diagnostic and current DRMM monitor state;
- no reboot, domain rejoin, DNS change, secure-channel reset, or domain-controller NTP change is performed without separate authority.

## 2. Trigger

Primary trigger:
- Datto RMM open alert;
- `alertContext.@class = comp_script_ctx`;
- diagnostics contain `Time source mismatch.`;
- diagnostics contain `not in approved list:`.

Known source monitor:
- `Get time source AOT Ver 05222026-1`
- component UID `07c49a16-1ee4-4be8-9f80-e2bb6c312adc`.

A matching alert may exist without an Autotask ticket. This playbook is therefore provider-object driven and must not depend on DRMM ticket creation being enabled.

## 3. Scope and Boundaries

### In Scope
- managed Windows endpoints;
- current DRMM alert and endpoint identity;
- current/previous time-source alert evidence;
- Windows Time service/configuration/source diagnostics;
- ordinary domain-member rediscovery/resynchronization;
- restoration of domain-hierarchy synchronization only when authoritative evidence proves the endpoint is a normal domain member and configuration is wrong;
- exact alert resolution after healthy verification.

### Out of Scope
- domain-controller/PDC external NTP configuration;
- DNS client changes;
- secure-channel repair;
- domain leave/rejoin;
- GPO modification;
- VM host time-policy changes;
- reboot or forced user interruption;
- unrelated alerts/devices.

Preserve Central Orchestrator authority, exact requester grants, provider/client isolation, audit, bounded retries, disruption protections, and `direct_provider_access=false`.

## 4. Initial Identification

1. Identify exact alert UID.
2. Identify exact DRMM device UID, hostname, and site/client from alert source evidence.
3. Read the managed endpoint by exact UID and confirm hostname/site identity.
4. If an Autotask ticket is linked, use the global CI/device-association and work-start lifecycle.
5. If no ticket exists, retain a provider-object playbook instance keyed by alert UID and device UID.
6. Search resolved alert history for prior matching Windows Time source failures on the same endpoint.
7. If identity is ambiguous, set `state = identification_blocked` and stop.

## 5. Expected State

For an ordinary Active Directory domain member:
- endpoint is online;
- Windows Time service is available and functional;
- synchronization mode is appropriate for domain hierarchy;
- current time source is in the site/client approved source set;
- synchronization status is healthy;
- a rediscovery/resync does not return an unresolved provider/system error;
- the exact triggering DRMM monitor condition clears.

For a non-domain endpoint, healthy state must come from an explicitly approved site/client NTP policy. Do not invent one.

## 6. State Model

`detected -> identified -> diagnosing -> classified -> waiting | approval_pending | remediating -> verifying -> complete`

Exception states:
- `identification_blocked`
- `waiting_device_access`
- `domain_controller_review`
- `trust_or_dc_discovery_review`
- `policy_conflict_review`
- `recurring_failure_review`
- `human_review`
- `escalated`

Persist alert UID, device UID, source, approved source set, recurrence count/window, classification, job IDs, attempt count, verification evidence, and last meaningful evidence fingerprint.

## 7. Diagnostic Workflow

### Step 1: Alert evidence

**Purpose:** Establish the exact observed mismatch.

**Evidence source:** DRMM open alert.

Record current source, approved source list, alert timestamp, autoresolve setting, response-action references, and exact alert UID.

### Step 2: Endpoint identity and availability

**Purpose:** Prove the alert belongs to the exact current endpoint and determine whether diagnostics can run.

**Evidence source:** `endpoint.device.read`.

If offline, enter `waiting_device_access`. Do not dispatch repair.

### Step 3: Recurrence

**Purpose:** Distinguish transient drift from repeated failure.

**Evidence source:** `endpoint.alert.history.search`.

Count same-device time-source mismatch alerts inside the previous 30 days. Three or more occurrences, including the current incident, classify as `RECURRING_FAILURE`.

### Step 4: Dedicated Windows Time diagnostic

**Required component:** `Windows Time Diagnostic [WIN] AOT Ver 10012026-1` or later accepted equivalent.

The diagnostic must return structured evidence for:
- domain joined;
- domain name;
- machine role / domain-controller status;
- W32Time service status/start type;
- current source;
- synchronization mode/type;
- configured peers;
- last successful synchronization;
- last synchronization error;
- stratum/offset where available;
- DC discovery result;
- authenticating DC;
- relevant recent Windows Time events;
- health classification.

Diagnostic component is read-only and is the intended standing-safe evidence source.

### Step 5: Classification

Bounded classifications:
- `HEALTHY_TRANSIENT`
- `W32TIME_STOPPED`
- `WRONG_SYNC_MODE`
- `RESYNC_REQUIRED`
- `LOCAL_CLOCK_FALLBACK`
- `NO_DOMAIN_SOURCE`
- `DOMAIN_TRUST_OR_DC_FAILURE`
- `DOMAIN_CONTROLLER`
- `NON_DOMAIN_DEVICE`
- `POLICY_CONFLICT`
- `RECURRING_FAILURE`
- `INCONCLUSIVE`

## 8. Decision Gates

Before remediation require:
1. exact alert and endpoint identity;
2. endpoint online in DRMM;
3. diagnostic evidence fresh;
4. endpoint proven to be a supported ordinary Windows domain member for domain-hierarchy repair;
5. endpoint is not a domain controller;
6. no evidence of domain trust, DNS/DC discovery, GPO, or broader site/domain failure requiring separate handling;
7. exact remediation component identity and arguments are source controlled;
8. exact authority exists for the target/action;
9. no equivalent action is already in flight;
10. retry limit is not exhausted.

## 9. Remediation

### Branch A: Rediscover and resync

Use for `RESYNC_REQUIRED` or eligible `LOCAL_CLOCK_FALLBACK`.

Expected behavior:
- rediscover time source;
- request resynchronization;
- return before/after source and command result;
- no reboot.

Classification: modifying, non-disruptive.

### Branch B: Restore domain hierarchy

Use only for `WRONG_SYNC_MODE` on a proven ordinary domain member.

Expected behavior:
- restore domain-hierarchy synchronization configuration;
- update Windows Time configuration;
- restart W32Time only when required by the accepted remediation component;
- rediscover/resync;
- return before/after configuration and source.

Classification: modifying. Service restart is permitted only if the accepted playbook-scoped component has been specifically reviewed for this branch.

### Explicitly not autonomous
- domain-controller time configuration;
- secure-channel reset;
- DNS changes;
- domain rejoin;
- GPO changes;
- reboot.

## 10. Retry Policy

Maximum autonomous remediation attempts per unchanged incident: **2**.

Attempt 1 should normally be rediscovery/resync.

Attempt 2 is allowed only when fresh diagnostic evidence specifically proves a configuration correction is appropriate.

Never repeat the same failed action blindly. After the bounded limit, enter Human Review.

## 11. Periodic Rechecks

Provider-object scan cadence: 15 minutes.

Waiting/recheck conditions:
- endpoint becomes online;
- remediation job reaches terminal state;
- normal DRMM monitor cycle updates;
- current source/health diagnostic changes.

Suppress duplicate work and duplicate notes for unchanged evidence.

## 12. Aging / Stale Condition

If a matching alert remains unresolved for 24 hours, or if three or more episodes occur within 30 days, investigate:
- recurrent DC reachability;
- DNS/DC-locator problems;
- roaming/offsite/VPN behavior;
- GPO/configuration drift;
- VM guest-time-provider interaction;
- Windows Time service instability;
- secure-channel/trust problems;
- broader domain time hierarchy health.

Repeated successful resync is not a substitute for root-cause investigation.

## 13. Dependency Handling

Current implementation dependencies:
- dedicated read-only Windows Time diagnostic component;
- accepted bounded remediation component;
- governed job status/output reads;
- exact alert resolution capability;
- durable provider-object playbook state;
- optional Autotask ticket creation for recurrence/failure escalation.

Missing dependencies become explicit implementation gaps. Do not substitute generic shell/provider access.

## 14. Documentation Requirements

When a linked or recurrence ticket exists, use:
1. **STATUS**
2. **NEXT STEP / ACTION REQUIRED**
3. **WHEN / ESCALATION**
4. **KEY EVIDENCE**
5. **WHAT JASON DID**
6. **CHANGES MADE**
7. **JASON STATE**

Suggested titles:
- `Jason - Windows Time - Diagnostic`
- `Jason - Windows Time - Recurring Failure`
- `Jason - Windows Time - Remediation`
- `Jason - Windows Time - Verification`
- `Jason - Windows Time - Resolution`
- `Jason - Windows Time - Human Review Required`

Do not write unchanged polling results repeatedly.

## 15. Failure Handling

Fail closed on:
- missing/ambiguous device identity;
- endpoint read failure;
- diagnostic component failure or unreadable output;
- unknown machine role;
- domain-controller target;
- conflicting policy evidence;
- job output unavailable;
- alert-resolution readback failure;
- unsupported provider result.

## 16. Escalation Criteria

Human Review when:
- domain controller is affected;
- trust/DC discovery remains broken;
- DNS/GPO/site/domain issue is suspected;
- two bounded repair attempts fail;
- recurrence threshold is reached;
- disruptive action is required;
- approved source policy is missing or contradictory;
- current state cannot be independently verified.

## 17. Verification

Required after remediation:
1. rerun the dedicated Windows Time diagnostic;
2. prove current source is in the approved source set;
3. prove synchronization health;
4. verify the exact DRMM time-source monitor condition is no longer open;
5. resolve the exact triggering alert only when provider state has not already auto-resolved it;
6. independently read back alert resolution/history.

Component exit code alone is not resolution evidence.

## 18. Completion Criteria

Complete only when:
- exact alert/device identity is proven;
- required diagnostics are complete;
- classification is established;
- any authorized remediation succeeded;
- authoritative healthy-state evidence exists;
- exact alert is no longer open;
- documentation is complete when a ticket/case exists;
- terminal provider/PSA state is independently read back.

## 19. Final Resolution Note

Summarize:
- original source mismatch;
- approved source expectation;
- recurrence count;
- root-cause classification;
- remediation performed;
- attempt count;
- final source and synchronization health;
- alert disposition;
- verification timestamp.

## 20. Required Capabilities

Read:
- `management.alert.search`
- `endpoint.device.read`
- `endpoint.alert.history.search`
- `automation.component.search`
- `automation.job.read`
- `automation.job.output.read`
- `service.ticket.search/read` when a ticket exists.

Actions for future promoted branches:
- `automation.component.execute`
- `endpoint.alert.resolve`
- `service.ticket.create`
- `service.ticket.note.create`
- `service.ticket.update`.

## 21. Acceptance Test

**Initial controlled target:** Riggins Company / CR412LT / DRMM device UID `ea3b591e-15a4-8e4f-a2a6-59a7793ea2c9` / alert UID `136898e4-f961-4b34-bd54-fd610bda5163`.

Acceptance matrix:
1. current alert is detected by exact diagnostic signature;
2. exact endpoint identity resolves;
3. source `Free-running System Clock` is extracted;
4. approved source `ADSRV.Rigginsco.local` is extracted;
5. prior same-device `Free-running System Clock` and `Local CMOS Clock` episodes count toward recurrence;
6. recurrence threshold classifies CR412LT as recurring;
7. wrong/unrelated `comp_script_ctx` alerts are rejected;
8. offline endpoint waits without mutation;
9. missing/failed evidence is inconclusive rather than healthy;
10. shadow mode performs zero mutations;
11. future remediation job is single/idempotent and bounded;
12. future verification requires monitor clear and diagnostic healthy state;
13. exact alert resolution is read back;
14. ambiguous/cross-client identity fails closed;
15. restart/resume preserves state.

## 22. Section Goal Closure

Section Goal is complete only after:
- shadow trigger/identity/recurrence acceptance passes on CR412LT;
- dedicated diagnostic component is reviewed and accepted;
- bounded remediation component is reviewed and accepted;
- remediation and verification acceptance cases pass;
- source-controlled registry is promoted from pilot/shadow to production/autonomous;
- exact owner promotion exists;
- Grafana/Project Jason control center shows the playbook and its state.

## 23. Autonomous Execution Eligibility and Owner Review

Initial version `0.1.0` is **pilot/shadow only**. It has no unattended mutation authority.

The proposed future autonomous safe boundary is:
- detect/identify/classify;
- read-only diagnostic;
- ordinary domain-member rediscover/resync;
- restore domain hierarchy only when diagnostic gates prove it is required;
- bounded W32Time restart only as part of the reviewed component;
- authoritative verification;
- resolve exact alert;
- create/update a recurrence or failure ticket when policy requires.

Explicit approval-bound/disruptive branches remain domain-controller changes, DNS/GPO/trust repair, domain rejoin, and reboot.

Any production/autonomous version change requires acceptance evidence and a new exact owner promotion.
