# Jason Playbook: Windows POST Error Investigation

## 1. Section Goal

**Goal:** Jason must process Windows Power-On-Self-Test (POST) error alerts from exact asset identification through evidence-based classification, documentation, verification, autonomous closure of isolated healthy workstation cases, and Human Review for recurring/protected/hardware-risk cases. The playbook does not autonomously perform firmware, BIOS, storage, memory, or hardware-changing remediation.

**Success means:**
- exact ticket, client/site, CI, DRMM endpoint, and alert timestamp are proven;
- current endpoint availability and boot state are checked;
- recent related tickets and DRMM activity are reviewed;
- Windows, hardware, storage, WHEA, crash, and boot evidence is gathered where available;
- the alert is classified as isolated_healthy, recurring_post, storage_risk, memory_hardware_risk, firmware_risk, power_shutdown_correlation, protected_role_review, or evidence_inconclusive;
- dangerous or ambiguous conditions are escalated rather than “fixed” speculatively;
- isolated healthy workstation cases resolve the exact alert and complete the ticket automatically after all evidence gates pass;
- recurring, protected-role, or hardware-risk conditions go to Help Desk I / Human Review with a specific next action;
- closure requires current healthy evidence and no unresolved recurrence/hardware risk.

## 2. Trigger

Primary trigger:
- Autotask/DRMM alert text reports Power-On-Self-Test (POST) errors during the last system startup.

Also applicable when:
- a Jason-owned ticket explicitly reports POST/BIOS startup errors;
- authoritative monitoring records a firmware/hardware startup warning requiring investigation.

Jason must confirm the alert pertains to the current identified endpoint and not a stale/duplicate object.

## 3. Scope and Boundaries

### In Scope
- managed Windows endpoints with a positively identified CI/DRMM device;
- Autotask and DRMM ticket/alert history;
- read-only operating-system, event-log, hardware, storage, firmware-version, uptime, and boot evidence;
- recent job/patch/reboot correlation;
- current health verification;
- internal documentation and escalation.

### Protected server / hypervisor branch

Physical servers, hypervisors, domain controllers, and other protected infrastructure may be investigated read-only, but no autonomous hardware, firmware, storage, reboot, or service-affecting remediation is permitted under this baseline. Recurring POST evidence on a protected host requires escalation unless a separately approved protected-role playbook branch exists.

### Out of Scope
- BIOS/UEFI flashing;
- firmware updates;
- changing boot order/security settings;
- disabling Secure Boot/TPM/BitLocker;
- hardware reset/reseat actions;
- storage repair that writes to disk;
- reboot/shutdown without exact approval;
- generic shell/API bypasses;
- assuming a POST alert proves a specific failed component.

Preserve direct_provider_access=false, Central Orchestrator authority, provider/client isolation, exact identity, disruptive-action approval, and full audit.

## 4. Initial Identification

1. Identify exact Autotask ticket and triggering alert.
2. Identify client/site, CI, hostname, DRMM device, and device role.
3. Validate existing CI or run the global device-association gate.
4. Confirm current endpoint online/last-seen state.
5. Record alert timestamp, current uptime, last boot time, and timezone context.
6. Search recent related tickets for the same device/symptom.
7. Check whether another active hardware/storage/boot incident already covers the condition.
8. Before substantive diagnostics, run the global ticket-work-start lifecycle with post-write readback.
9. If identity is ambiguous, set state identification_blocked and stop.

## 5. Expected State

Healthy state means:
- endpoint is uniquely identified;
- current boot is complete and Windows is stable;
- no recurring POST alert remains unexplained;
- no current WHEA, storage, memory, controller, or file-system evidence indicates hardware risk;
- no conflicting crash/BSOD or power-loss pattern is active;
- the alert is either proven stale/isolated with healthy current evidence or escalated with a specific risk classification.

A successful Windows boot does not by itself prove the POST alert was harmless.

## 6. State Model

identified -> diagnosing -> classifying -> verifying -> resolving_alert -> completing_ticket -> complete

Classification states:
- isolated_healthy
- recurring_post
- storage_risk
- memory_hardware_risk
- firmware_risk
- power_shutdown_correlation
- protected_role_review
- evidence_inconclusive

Exception states:
- waiting_endpoint
- dependency_blocked
- human_review

Persist completed evidence steps so rechecks do not repeat diagnostics unnecessarily.

## 7. Diagnostic Workflow

### Step 1: Validate current availability and boot state

Collect:
- online/offline state;
- last seen;
- current uptime;
- last boot time;
- operating system;
- device role;
- current logged-in-user state where relevant to disruption assessment.

If offline, use the common endpoint-availability workflow rather than assuming hardware failure.

### Step 2: Review recent ticket and alert history

Search a default 30-day window for:
- POST alerts;
- unexpected shutdowns;
- BSOD/crash tickets;
- disk/storage alerts;
- memory/hardware alerts;
- firmware/BIOS-related work.

Repeated POST alerts or correlated hardware evidence should not be closed as isolated.

### Step 3: Review DRMM activity around the incident

Check recent:
- patching;
- reboot actions;
- component jobs;
- firmware/vendor tooling if represented;
- security actions;
- technician activity.

A known planned reboot may explain timing but does not automatically explain a POST hardware error.

### Step 4: Gather Windows hardware/boot evidence

Where governed read capabilities exist, inspect:
- Kernel-Power / Event ID 41;
- Event ID 6008;
- WHEA events;
- disk/controller/NTFS errors;
- bugcheck/crash evidence;
- memory-related hardware events;
- boot/startup failures;
- current Device Manager/problem evidence when available.

### Step 5: Gather firmware/system evidence

Read-only evidence may include:
- system manufacturer/model;
- BIOS/UEFI version/date;
- boot type;
- firmware status exposed by approved provider/tooling;
- hardware health telemetry available from DRMM/vendor integrations.

Do not compare against an internet firmware version unless an authoritative governed vendor/source workflow explicitly supplies that evidence.

### Step 6: Independent device-health check

Check current:
- storage health;
- free space where relevant;
- security/management agent health;
- reboot-required state;
- repeated unexpected shutdowns;
- currently open hardware-related alerts.

## 8. Decision Gates

Before any action beyond read-only diagnostics:
1. exact client/device/CI is proven;
2. evidence identifies a bounded remediation rather than a generic symptom;
3. target role and governance allow the proposed action;
4. action is represented by an approved capability/playbook branch;
5. no conflicting hardware/storage risk makes the action unsafe;
6. disruptive actions have exact ticket/incident approval.

The baseline POST playbook has no standing autonomous hardware/firmware remediation authority.

## 9. Remediation

### Baseline behavior

No speculative hardware change is performed.

If current evidence proves an isolated healthy workstation event:
- classify `isolated_healthy`;
- resolve the exact triggering DRMM alert;
- verify the exact alert is no longer open;
- write the final resolution note;
- complete the Autotask ticket automatically;
- independently read back status=Complete.

No Help Desk review is required for `isolated_healthy`.

If evidence indicates recurrence, protected infrastructure, storage risk, memory/hardware risk, firmware risk, power/shutdown correlation, or inconclusive evidence:
- classify the exact risk state;
- preserve the evidence;
- hand off to Help Desk I with status Human Review;
- state the next safest technician/vendor action clearly.

Any future hardware/firmware repair branch must be separately designed, tested, and promoted for the exact capability.

## 10. Retry Policy

- Provider/read failures: bounded retry of the same read.
- Do not repeat an identical expensive diagnostic when valid recent output already exists.
- No autonomous firmware/hardware remediation retry exists in this baseline.
- Contradictory evidence moves to inconclusive/escalated rather than repeated guessing.

## 11. Periodic Rechecks

Recheck when:
- endpoint is offline;
- a related diagnostic job is pending;
- a technician/vendor action is awaited;
- current health needs confirmation after a separately approved change.

Known-ticket rechecks target the exact endpoint/job/ticket rather than a full queue scan.

## 12. Aging / Stale Condition

If unresolved beyond the normal support window, examine:
- stale/duplicate CI;
- retired/replaced endpoint;
- recurring hardware condition;
- unresolved vendor/warranty dependency;
- monitoring defect;
- ticket duplication.

Do not leave a recurring POST condition parked indefinitely.

## 13. Dependency Handling

Dependencies may include:
- endpoint event-log evidence;
- WHEA/storage reads;
- device hardware inventory;
- BIOS/firmware version evidence;
- DRMM job/activity history;
- vendor diagnostics;
- warranty/support process.

Missing evidence becomes dependency_blocked or inconclusive; it does not justify guessing.

Current controlled-target dependency: #257 tracks a PowerShell 3-compatible/legacy-safe out-of-band/iLO/IML diagnostic path for VZ-HYPER-V. A completed component job with `ScriptRequiresUnmatchedPSVersion` is a diagnostic-tool compatibility failure, not evidence that iLO/OOB is absent.

## 14. Documentation Requirements

Use the standard technician-scannable Jason note layout:

- **STATUS**
- **NEXT STEP** or **ACTION REQUIRED**
- **DEVICE / ALERT**
- **RECURRENCE**
- **KEY HARDWARE EVIDENCE**
- **WHAT JASON CHECKED**
- **CHANGES MADE**
- **JASON STATE**

For isolated healthy closure, lead with:
- STATUS: VERIFIED HEALTHY — ISOLATED POST EVENT
- NEXT STEP: Resolve exact alert and complete ticket automatically
- RECURRENCE: None found in the defined review window

For Human Review, lead with:
- STATUS: HUMAN REVIEW REQUIRED
- ACTION REQUIRED: Review the identified hardware/firmware/recurrence risk
- include the exact subsystem/risk and recommended next diagnostic

Suggested internal note titles:
- Jason - POST Error - Asset Validation
- Jason - POST Error - Diagnostic
- Jason - POST Error - Correlation
- Jason - POST Error - Verification
- Jason - POST Error - Human Review Required
- Jason - POST Error - Resolution

Document:
- ticket/device/CI;
- alert timestamp;
- current boot/uptime state;
- recent related ticket history;
- relevant DRMM activity;
- WHEA/storage/crash/boot findings;
- BIOS/firmware evidence when available;
- classification;
- exact alert-resolution result where applicable;
- ticket-completion readback where applicable;
- next action.

Do not copy secrets or irrelevant raw logs into the ticket.

## 15. Failure Handling

Fail closed and document:
- ambiguous identity;
- endpoint unavailable/inconclusive;
- event evidence unavailable;
- conflicting evidence;
- provider read failure;
- suspected storage/hardware failure;
- firmware action required;
- disruptive action required;
- monitor appears defective/stale but cannot be proven.

## 16. Escalation Criteria

Hand off to Help Desk I / Human Review when:
- POST error recurs;
- WHEA or storage/controller errors are present;
- memory/hardware failure is indicated;
- BIOS/firmware remediation may be needed;
- endpoint fails to boot reliably;
- condition correlates with crashes/BSODs/unexpected shutdowns;
- evidence is contradictory or insufficient;
- device is a protected server/hypervisor/domain controller/physical host;
- exact alert resolution or completion readback fails.

Human Review must identify the likely subsystem and the next safest technician/vendor diagnostic.

## 17. Verification

For an `isolated_healthy` workstation case:
1. endpoint is currently online/stable;
2. current uptime/boot state is healthy;
3. no second matching POST alert exists in the defined recurrence window;
4. no current/recent WHEA evidence indicates hardware risk;
5. no disk/controller/NTFS evidence indicates storage risk;
6. no memory/hardware alert is active;
7. no crash/BSOD pattern is active;
8. no unresolved unexpected-shutdown pattern materially correlates;
9. no other open hardware/boot ticket covers the same condition;
10. device is not a protected server/hypervisor/domain controller/physical host;
11. exact triggering alert is stale/resolved or can be safely resolved;
12. final classification is documented.

A successful Windows boot or component return is not sufficient by itself.

## 18. Completion Criteria

Complete automatically only when:
- exact endpoint is verified;
- classification is `isolated_healthy`;
- all required diagnostics completed;
- current health is established;
- no recurring/unresolved hardware risk remains;
- device is not in a protected role;
- exact triggering alert is resolved and resolution is read back;
- final resolution note exists;
- Autotask completion succeeds and status=Complete is independently read back.

All other classifications go to Help Desk I / Human Review.

## 19. Final Resolution Note

Include:
- original POST condition;
- affected endpoint/CI;
- incident time;
- relevant recent activity;
- hardware/storage/WHEA findings;
- firmware/boot findings;
- recurrence result;
- current health verification;
- final classification/disposition.

## 20. Required Capabilities

- service.ticket.read/search/update
- service.ticket.note.create
- service.configuration.read/search
- endpoint.device.read/search
- management/endpoint alert search
- DRMM activity/job history
- governed Windows event/hardware evidence
- boot/firmware inventory reads where available
- persisted playbook state
- targeted recheck scheduling

No additional write capability is required for the baseline diagnostic branch.

## 21. Acceptance Test

**Protected-role controlled target:** ticket T20260923.0075 / CI 383 / VZ-HYPER-V, a physical HP ProLiant DL380p Gen8 Hyper-V host. Production evidence already shows recurrent POST events in June and September 2026 and host-level interruption correlation across guest VMs, so this target must exercise the protected-hypervisor Human Review branch.

A second controlled target must be an ordinary Windows workstation with a single isolated POST event and no WHEA/storage/memory/crash/shutdown risk, to prove exact-alert resolution and autonomous completion.

Prove:
1. trigger recognition;
2. exact ticket/device association;
3. current online/boot state;
4. 30-day recurrence search;
5. DRMM activity correlation;
6. read-only WHEA/storage/crash/boot evidence;
7. hardware/firmware evidence where supported;
8. deterministic classification into the explicit state set;
9. no firmware/hardware mutation;
10. current-health verification;
11. protected/recurring/hardware-risk case routes to Help Desk I / Human Review;
12. isolated healthy workstation case resolves the exact alert automatically;
13. isolated healthy workstation ticket completes automatically with readback;
14. technician-scannable documentation;
15. no unrelated production object is changed.

No unrelated production object may be changed.

## 22. Section Goal Closure

Close after:
- playbook is merged;
- required read-only evidence capabilities are enumerated and proven;
- controlled acceptance on the initial target succeeds;
- any missing hardware/firmware evidence capability becomes an explicit TODO/support item;
- Grafana/Project Jason operational status and remaining limitations are updated.
