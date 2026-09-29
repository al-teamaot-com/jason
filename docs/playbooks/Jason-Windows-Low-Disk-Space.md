# Jason Playbook: Windows Low Disk Space

```yaml
playbook:
  id: low_disk_space
  name: Jason - Windows Low Disk Space
  version: 1.1.0
  owner: AOT IT Operations
  target_type: ticket
  trigger:
    provider: Autotask/Datto RMM
    match: ticket title contains "Low Disk Space"
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 1
  recheck:
    enabled: true
    cadence: 15 minutes for cleanup/monitor propagation
  verification:
    authoritative_source: Datto RMM current low-disk monitor plus current volume free space
    success_condition: current low-disk alert is clear after current free-space read
  completion:
    terminal_disposition: Complete or Help Desk I / Human Review
  autonomy:
    allowed_branches:
      - recovered_after_existing_autotask_cleanup
      - root_cause_diagnostics
      - one_exact_safe_cleanup
    approval_bound_branches:
      - exact standing-safe cleanup component execution
    disruptive_branches: []
```

## 1. Section Goal

**Goal:** Jason must process Windows low-disk-space alerts from identification through verified resolution or escalation. Jason should determine what is consuming space, preserve user/business data, perform only approved bounded cleanup on supported workstations, verify resulting free space and monitoring state, and route servers or uncertain cases for human review.

**Success means:**
- exact ticket, client, CI, DRMM endpoint, and affected volume are proven;
- Jason gives the existing Autotask-triggered Disk Cleanup a bounded opportunity to finish before doing competing remediation;
- current capacity, free space, free percentage, and current monitor state are established;
- the primary storage consumers are classified, including VSS, Windows/update residue, hibernation/pagefile, large files, MSP/install artifacts, application/user data, and other material consumers;
- physical disk identity, SMART/storage-health evidence, and relevant reliability warnings are considered before recommending cleanup versus replacement;
- known safe cleanup targets are distinguished from user/business/application data;
- no more than one additional playbook-scoped cleanup is attempted;
- if the remaining footprint is legitimate, Jason recommends capacity expansion rather than deleting useful data;
- technician-facing notes contain only facts that explain the cause, change the remediation decision, justify replacement/capacity expansion, or identify technician action;
- workstation remediation is independently verified against current free space and the authoritative monitor;
- server cleanup/remediation remains human-reviewed unless a separately approved server-safe branch exists;
- arbitrary deletion is never used to make the alert disappear.

## 2. Trigger

Primary triggers:
- Autotask/DRMM ticket title contains Low Disk Space;
- DRMM volume monitor reports a configured low-free-space threshold;
- an existing Jason-owned ticket explicitly asks for investigation of a nearly full Windows volume.

Jason confirms the affected volume and current condition rather than assuming the triggering alert is still current.

When the ticket is created, AOT's existing Autotask automation may already dispatch Disk Cleanup and may auto-close the ticket if enough space is recovered. Jason therefore treats the first 15 minutes after first ownership/observation as a cleanup/monitor propagation grace window. During that window Jason does not launch a competing cleanup. If the authoritative low-disk monitor clears, Jason verifies current free space and allows/finishes the normal resolution path. Only a still-current low-disk condition proceeds to deeper root-cause analysis.

## 3. Scope and Boundaries

### In Scope
- managed Windows workstations/laptops;
- read-only disk, folder, file, BitLocker, system, and DRMM activity evidence;
- known AOT-approved cleanup targets when the exact action is approved for autonomous use;
- internal ticket documentation and alert/ticket verification.

### Human Review Required
- Windows servers;
- domain controllers, line-of-business servers, database servers, hypervisors, backup repositories, or other protected roles;
- cleanup involving user profile data, business data, databases, backups, archives, PST/OST data, VHD/VHDX files, or unknown application storage;
- reboot, service interruption, forced logoff, or another user-disruptive action.

### Out of Scope
- deleting arbitrary files because they are large;
- deleting user documents/downloads without explicit approval;
- disabling BitLocker;
- shrinking logs/data without knowing the owning application;
- direct provider access or shell/API bypasses;
- treating provider-reported cleanup success as proof of adequate free space.

Preserve Central Orchestrator authority, provider/client isolation, exact target identity, audit, bounded retries, and direct_provider_access=false.

## 4. Initial Identification

1. Identify exact Autotask ticket and client/site.
2. Run the global CI/device-association gate.
3. Resolve the exact DRMM endpoint and affected drive/volume.
4. Confirm current online state.
5. Before substantive diagnostics, use the global ticket-work-start lifecycle: Jason queue, In Progress, Remote Support, post-write readback.
6. Record current alert timestamp and any prior related ticket.
7. Enter the bounded 15-minute Autotask-cleanup grace state before launching any playbook cleanup.
8. During the grace state, recheck the current DRMM low-disk monitor; do not duplicate the existing Autotask cleanup.
9. Search recent related tickets and DRMM activity history before dispatching a diagnostic that may already have run.
10. If device identity, drive identity, or client scope is ambiguous, set state identification_blocked and stop.

## 5. Expected State

Healthy state means:
- the exact monitored volume is readable and online;
- free space is above the active monitoring condition or documented client/site standard;
- underlying cause is understood or classified;
- no evidence indicates storage failure or file-system corruption;
- BitLocker state is known and not altered;
- any cleanup performed is from an approved target class;
- the alert clears or current evidence proves the condition is healthy.

Do not invent a fixed free-space percentage if the authoritative monitor/policy supplies the threshold.

## 6. State Model

identified -> waiting_autotask_cleanup -> diagnosing -> classified -> candidate_cleanup -> remediating -> verifying -> complete

Waiting/exception states:
- waiting_device_access
- waiting_autotask_cleanup
- waiting_monitor_propagation
- human_review_server
- human_review_capacity
- unknown_large_data
- storage_health_risk
- dependency_blocked
- approval_pending
- escalated

Persist state so a recheck does not repeat completed scans or cleanup.

## 7. Diagnostic Workflow

### Step 1: Capture volume baseline

Record:
- drive letter / volume identity;
- total size;
- free bytes/GB;
- free percentage;
- file system;
- volume label where useful;
- fixed/removable/system role where available;
- current BitLocker protection/encryption state;
- reboot-required state when available.

### Step 2: Check recent automation/activity

Inspect DRMM activity/job history for recent:
- disk/folder size scans;
- cleanup components;
- patching;
- reboot jobs;
- security tooling actions;
- other maintenance that could explain the condition.

If an exact relevant job is still running, track/read that job instead of redispatching it.

### Step 3: Read-only storage analysis

Use governed read-only endpoint evidence to identify:
- largest top-level folders and the dominant retained-data footprint;
- top large files, especially ISO, IMG, WIM, ESD, ZIP/7z/RAR/CAB, MSI/MSP/EXE, DMP, VHD/VHDX, PST/OST, and similar common large-file types;
- VSS/shadow-copy consumption;
- hiberfil.sys, pagefile.sys, MEMORY.DMP, and other material system files;
- Windows Update / SoftwareDistribution residue and old SoftwareDistribution.bak_* folders;
- C:\Sysmon accumulation;
- Autotask/Datto/software-deployment installers, extracted setup media, and stale deployment artifacts when they appear among material consumers;
- user/application/business data that should not be deleted simply because it is large;
- partition/capacity evidence when it materially changes the recommendation.

The large-file scan is diagnostic evidence, not deletion authority. ISO/IMG/install media, archives, PST/OST, VHD/VHDX, Downloads, user data, and unknown application storage are review candidates unless an exact separately approved cleanup class applies.

Do not modify files during analysis.

### Step 4: Check known AOT cleanup candidates

Explicitly check C:\Sysmon when present.

For C:\Sysmon:
- determine whether it exists;
- determine size;
- determine whether active services/processes still depend on it;
- distinguish a current required installation from orphaned/known accumulation;
- only use an approved cleanup action when the playbook and exact target criteria authorize it.

The existence of C:\Sysmon alone is not permission to delete it.

Also check old `C:\Windows\SoftwareDistribution.bak_*` folders. Their aggregate size is useful root-cause evidence, but the current AOT cleanup component is classified by Jason component governance as destructive/review-required and is **not** standing-safe. Jason may recommend that cleanup in Help Desk I / Human Review, but must not dispatch it unattended. Active Windows Update cache is not part of this autonomous cleanup branch.

### Step 5: Check storage-health and replacement evidence

Inspect available evidence for:
- physical disk model, serial where available, media type, bus/interface, and capacity;
- SMART/Storage Spaces health and operational status;
- storage reliability counters, read/write error totals, wear/health indicators when exposed;
- Event ID 7/bad block;
- NTFS/file-system errors;
- controller/disk warnings;
- repeated unexpected shutdowns associated with storage issues.

If storage-health risk is present, prioritize preservation/escalation over cleanup. A drive may warrant replacement even if space can be reclaimed. If both health risk and capacity pressure are present, the technician recommendation should make both facts clear.

### Step 6: Capacity / recurrence interpretation

Where useful evidence exists, distinguish:
- transient accumulation that can be safely removed;
- recurring growth that is likely to return;
- large but legitimate user/application/business data;
- a drive that is simply undersized for the retained data footprint;
- a drive that should be replaced primarily because of health risk.

When prior low-disk tickets exist for the same endpoint, surface the recurrence count only if it changes the recommendation. Do not invent growth rates when historical free-space readings are unavailable.

## 8. Decision Gates

Before cleanup:
1. exact client/device/volume identity is proven;
2. endpoint is online;
3. current low-space condition is confirmed;
4. device role is a supported workstation/laptop for autonomous cleanup;
5. diagnostic evidence identifies the target;
6. target is an explicitly approved safe cleanup class;
7. no user/business/application data is included;
8. no conflicting job/maintenance is active;
9. current governance and playbook promotion authorize the exact action;
10. rollback/escalation behavior is known.

If any gate fails, investigate/document or request human review. Do not improvise deletion.

## 9. Remediation

### A. Known safe workstation cleanup

Version 1.1 permits at most **one** additional playbook-scoped cleanup after the existing Autotask cleanup opportunity. Jason does not rerun generic `Disk Cleanup [WIN]`.

The exact autonomous target is:
- `Sysmon - Clear C:\Sysmon Folder - AOT` (`97ddcdd5-2b74-4a4b-9516-cc872af6a7b6`) only when C:\Sysmon is at least 1 GiB, no active service references that path, and the exact component has active standing-safe approval.

The existing `Delete SoftwareDistribution Backup Folders - AOT Ver 05122026-1` component remains **review-bound** because standing-safe promotion was rejected by Jason component governance as destructive/review-required. Jason may detect and quantify those old backup folders and recommend technician cleanup, but it must not dispatch that component unattended.

User/business/application data, active Windows Update cache, Recycle Bin, browser cache, VSS, hibernation, pagefile, dumps, ISO/IMG/install media, PST/OST, VHD/VHDX, and unknown data are not part of this autonomous cleanup authority.

### B. Server or protected-role cleanup

Set state human_review_server. Jason gathers evidence and proposes the exact cleanup. No autonomous cleanup under this baseline.

### C. Unknown large file/folder

Set state unknown_large_data. Document path, size, owner/application context when available, and recommended technician action. Do not delete.

### D. Storage-health risk

Set state storage_health_risk. Do not focus on space recovery alone. Escalate for hardware/storage investigation and preserve evidence. If replacement is already justified by health evidence, include that conclusion even if cleanup could temporarily recover space.

### E. Legitimate retained data / undersized drive

When the low-space condition remains, no approved waste is material, and the dominant footprint appears to be legitimate retained user/application/business data, do not delete the data. Route to Help Desk I / Human Review with a concise capacity recommendation. Include current capacity/free space, the few material consumers that justify the conclusion, recurrence when relevant, physical-disk health/identity when useful, and a recommendation to replace/upgrade with a larger drive if the data is expected to remain.

## 10. Retry Policy

- Read failures: bounded re-read of the same evidence request; never convert a read failure into cleanup authority.
- Cleanup: maximum one additional autonomous cleanup attempt per incident cycle, regardless of how many eligible safe targets exist. The pre-existing Autotask-triggered cleanup remains the first cleanup opportunity.
- Never rerun while prior job state is active/unknown.
- If verification fails, stop and escalate rather than chaining increasingly aggressive deletion.

## 11. Periodic Rechecks

Recheck when:
- the initial 15-minute Autotask cleanup grace window is active;
- endpoint was offline;
- an approved cleanup job is pending;
- the post-cleanup 15-minute monitor propagation window is active;
- a dependency/approval is awaited.

The grace/recheck windows suppress duplicate cleanup dispatch. If the current low-disk monitor clears at any recheck, Jason verifies current free space and follows the completion path instead of continuing diagnostics.

Known-ticket rechecks target that ticket/job/device rather than scanning the whole queue.

## 12. Aging / Stale Condition

For recurring/old low-space tickets, investigate:
- endpoint replacement/retirement;
- stale CI/DRMM object;
- repeated recurrence after prior cleanup;
- underlying application growth;
- storage sizing problem;
- insufficient system-drive capacity.

Repeated cleanup without root-cause review is not success.

## 13. Dependency Handling

Potential dependencies:
- read-only folder-size component;
- BitLocker status read;
- DRMM activity/job history;
- exact approved cleanup component;
- endpoint/CI association;
- storage-health evidence.

Production validation on GAI-LT2830 proved the #261 execution-plan authorization defect was corrected: both exact approved read-only diagnostics passed governed plan authorization with exactly one provider attempt and readback. The current safety blocker is #265: Datto/Jason job reads can remain `active` with empty output after the endpoint/UI no longer shows a running execution. Treat such state as pending/unknown; never redispatch until current execution state is positively resolved.

## 14. Documentation Requirements

Use concise, technician-scannable internal notes. **Collect broadly, report selectively.** Include only facts that explain the cause, change the remediation decision, justify replacement/capacity expansion, or identify technician action.

Preferred order:
1. **STATUS** — current free space / current monitor state.
2. **NEXT STEP** or **ACTION REQUIRED** — what Jason or the technician should do next.
3. **KEY EVIDENCE** — at most the few material consumers/findings that explain the conclusion.
4. **DISK HEALTH** — only when health/identity information changes the recommendation or confirms replacement/capacity guidance.
5. **WHAT JASON DID** — concise diagnostics/remediation summary.
6. **CHANGES MADE** — explicitly state None when no modification occurred.
7. **JASON STATE** — persisted state for audit/resume.

Relevant evidence may include drive/volume, current free space, major consumers, recurrence, C:\Sysmon or SoftwareDistribution backup size when actionable, large ISO/IMG/install/archive files when material, VSS/system-file consumption when material, storage-health warnings, and exact cleanup job/correlation IDs. Normal/irrelevant SMART attributes, exhaustive folder listings, raw PowerShell output, and low-value details must stay in Jason evidence rather than being pasted into the ticket.

Suggested titles:
- Jason - Low Disk Space - Baseline
- Jason - Low Disk Space - Diagnostic
- Jason - Low Disk Space - Remediation
- Jason - Low Disk Space - Verification
- Jason - Low Disk Space - Escalation

Avoid unnecessary end-user communication for ordinary workstation monitoring remediation unless the action is disruptive, user input is needed, or client policy requires contact.

## 15. Failure Handling

Document and fail closed on:
- ambiguous device/volume;
- diagnostic capability unavailable;
- component execution authorization defect;
- large data whose purpose is unknown;
- storage-health warning;
- cleanup job failure;
- post-cleanup free space not materially improved;
- alert persists despite healthy free-space evidence;
- provider/job state is stale or contradictory.

## 16. Escalation Criteria

Escalate when:
- target is a server/protected role;
- storage-health evidence suggests failure;
- safe cleanup cannot be identified;
- user/business data is the primary consumer;
- issue recurs after bounded cleanup;
- additional disk capacity may be required;
- execution-plan/governance blocks the approved action;
- verification fails.

## 17. Verification

After cleanup:
1. wait for the exact job to reach a trustworthy terminal state;
2. retrieve output;
3. independently re-read volume size/free space/free percentage;
4. confirm expected target no longer consumes the identified space when relevant;
5. confirm monitoring returns healthy/clears;
6. confirm no new storage/file-system errors were introduced;
7. document final state.

Job success alone is not verification.

## 18. Completion Criteria

Complete when:
- identity and volume are correct;
- baseline and root-cause classification are documented;
- required safe remediation completed or no remediation was necessary;
- independent free-space verification is healthy;
- monitoring condition is healthy/cleared;
- no unresolved storage-health risk remains;
- ticket documentation is complete.

## 19. Final Resolution Note

Include:
- original low-space condition;
- volume size/free before;
- primary cause;
- cleanup performed, if any;
- volume size/free after;
- BitLocker status;
- storage-health result;
- alert/monitor result;
- final disposition.

## 20. Required Capabilities

- service.ticket.read/search/update
- service.ticket.note.create
- service.configuration.read/search
- endpoint.device.read/search
- endpoint.audit.read
- endpoint.alert.search/history
- endpoint.powershell.read for classifier-approved read-only storage diagnostics
- service.ticket.search for recurrence context when useful
- automation.component.execute only for exact standing-safe cleanup components
- automation.job.read
- automation.job.output.read
- BitLocker/status evidence
- DRMM activity/history evidence
- persisted playbook state
- orchestration recheck scheduling

Missing/broken capability behavior becomes an explicit blocker, not a shell/API bypass.

## 21. Acceptance Test

**Primary current target:** GAI-LT2830 / ticket T20260924.0078 / CI 280.

Prove:
1. exact ticket/device association;
2. the initial 15-minute Autotask cleanup grace does not dispatch competing cleanup;
3. recovered/cleared monitor state completes through independent free-space and ticket-status readback;
4. current volume baseline and current monitor state;
5. read-only largest-folder and large-file analysis;
6. VSS, hibernation/pagefile/dump, Windows Update residue, C:\Sysmon, SoftwareDistribution backup, and common large-file/install-artifact classification;
7. physical-disk / SMART / reliability evidence and storage-risk override;
8. recurrence context is surfaced only when relevant;
9. protected/server targets route to Help Desk I / Human Review without cleanup;
10. legitimate retained data produces a concise capacity-upgrade recommendation rather than arbitrary deletion;
11. C:\Sysmon is eligible only when >=1 GiB and no active service references it;
12. material SoftwareDistribution.bak_* usage is detected and routed as a review-bound recommendation without autonomous component dispatch;
13. at most one additional standing-safe Sysmon cleanup component is dispatched per incident cycle;
14. successful cleanup still requires current free-space re-read and authoritative monitor clear;
15. failed/uncleared cleanup routes to Help Desk I / Human Review with no second cleanup attempt;
16. technician notes are relevance-filtered and do not paste raw scan/SMART output;
17. #261 remains regression-covered as a fixed authorization path; stale/unknown job state fails closed without duplicate dispatch.

No unrelated production object may be modified.

## 21A. Autonomous Execution Scope

`autonomous_allowed: root_cause_plus_one_bounded_cleanup`

Design/implementation approval owner: person-al.
Design approval date: 2026-09-29.
Source scope: exact `low_disk_space@1.1.0` branch using governed endpoint/device/audit/alert/ticket reads, classifier-approved read-only PowerShell, internal ticket work-start/note/update, and at most one standing-safe Sysmon cleanup when its deterministic preconditions are met. SoftwareDistribution backup cleanup is evidence/recommendation only and remains human-review bound.

The branch may not delete arbitrary/user/business/application data; clear VSS; disable hibernation; resize partitions; empty Recycle Bin; clear active Windows Update cache; delete ISO/IMG/install media, PST/OST, VHD/VHDX, or unknown data; alter BitLocker; stop services/processes; reboot; or perform any other unrelated/disruptive action.

A material version/capability/component-fingerprint change requires a new durable owner promotion before unattended execution. Servers/protected roles and storage-health-risk branches remain Help Desk I / Human Review.

## 22. Section Goal Closure

Close after:
- playbook 1.1 source and runtime are merged;
- deterministic/unit/security validation passes;
- the exact Sysmon cleanup component is standing-safe with a durable fingerprint;
- the SoftwareDistribution cleanup component is explicitly recorded as review-bound and cannot be dispatched unattended;
- exact `low_disk_space@1.1.0` playbook autonomy promotion is active;
- controlled workstation acceptance proves grace, diagnostics, one-cleanup ceiling, verification, and Human Review routing;
- production runtime is deployed and live readback proves 1.1 is executing;
- Grafana/Project Jason status and remaining TODOs are updated.
