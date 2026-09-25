# Jason Playbook: Windows POST Error Investigation

## 1. Section Goal

**Goal:** Jason must process Windows Power-On-Self-Test (POST) error alerts from exact asset identification through evidence-based classification, documentation, verification, and escalation. The baseline playbook is diagnostic-first and does not autonomously perform firmware, BIOS, storage, memory, or hardware-changing remediation.

**Success means:**
- exact ticket, client/site, CI, DRMM endpoint, and alert timestamp are proven;
- current endpoint availability and boot state are checked;
- recent related tickets and DRMM activity are reviewed;
- Windows, hardware, storage, WHEA, crash, and boot evidence is gathered where available;
- the alert is classified as stale/isolated, recurring, storage-related, memory/hardware-related, firmware/BIOS-related, power-related, or inconclusive;
- dangerous or ambiguous conditions are escalated rather than “fixed” speculatively;
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

identified -> diagnosing -> classifying -> verifying -> complete

Exception states:
- waiting_endpoint
- recurring_post
- storage_risk
- hardware_risk
- firmware_risk
- power_or_shutdown_correlation
- dependency_blocked
- inconclusive
- escalated

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

Diagnostic/documentation only.

If current evidence proves a stale/isolated alert and the endpoint is healthy:
- no speculative hardware change is performed;
- verify alert state and document resolution.

If evidence indicates a specific hardware/storage/firmware issue:
- classify it;
- preserve evidence;
- escalate with the recommended technician/vendor next step.

Any future automated repair branch must be separately designed, tested, and promoted for the exact capability.

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

Suggested internal note titles:
- Jason - POST Error - Asset Validation
- Jason - POST Error - Diagnostic
- Jason - POST Error - Correlation
- Jason - POST Error - Verification
- Jason - POST Error - Escalation
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

Escalate when:
- POST error recurs;
- WHEA or storage/controller errors are present;
- memory/hardware failure is indicated;
- BIOS/firmware remediation may be needed;
- endpoint fails to boot reliably;
- condition correlates with crashes/BSODs/unexpected shutdowns;
- evidence is contradictory or insufficient;
- protected/server role increases risk.

Escalation should identify the likely subsystem and the next safest technician/vendor diagnostic.

## 17. Verification

For a stale/isolated case:
1. endpoint is currently online/stable;
2. current uptime/boot state is healthy;
3. no new matching POST alert is present;
4. no current WHEA/storage/hardware evidence indicates unresolved risk;
5. related monitoring/ticket state is re-read;
6. final classification is documented.

A component returning success is not sufficient by itself.

## 18. Completion Criteria

Complete only when:
- exact endpoint is verified;
- required diagnostics completed;
- current health is established;
- no recurring/unresolved hardware risk remains;
- alert/ticket state is verified;
- documentation is complete.

Otherwise escalate.

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

**Initial controlled target:** ticket T20260923.0075 / CI 383 / VZ-HYPER-V, a physical HP ProLiant DL380p Gen8 Hyper-V host. Production evidence already shows recurrent POST events in June and September 2026 and host-level interruption correlation across guest VMs, so acceptance must exercise the protected-hypervisor escalation branch rather than auto-remediation.

Prove:
1. trigger recognition;
2. exact ticket/device association;
3. current online/boot state;
4. 30-day recurrence search;
5. DRMM activity correlation;
6. read-only WHEA/storage/crash/boot evidence;
7. hardware/firmware evidence where supported;
8. deterministic classification;
9. no firmware/hardware mutation;
10. current-health verification;
11. internal documentation;
12. complete vs escalate decision.

No unrelated production object may be changed.

## 22. Section Goal Closure

Close after:
- playbook is merged;
- required read-only evidence capabilities are enumerated and proven;
- controlled acceptance on the initial target succeeds;
- any missing hardware/firmware evidence capability becomes an explicit TODO/support item;
- Grafana/Project Jason operational status and remaining limitations are updated.
