# Jason Playbook: Windows Low Disk Space

## 1. Section Goal

**Goal:** Jason must process Windows low-disk-space alerts from identification through verified resolution or escalation. Jason should determine what is consuming space, preserve user/business data, perform only approved bounded cleanup on supported workstations, verify resulting free space and monitoring state, and route servers or uncertain cases for human review.

**Success means:**
- exact ticket, client, CI, DRMM endpoint, and affected volume are proven;
- current capacity, free space, free percentage, volume details, and BitLocker state are documented;
- recent DRMM activity/job history is checked before rerunning diagnostics or cleanup;
- large folders/files are identified without modifying data;
- known safe cleanup targets are distinguished from user/business/application data;
- workstation remediation is bounded and independently verified;
- server cleanup/remediation remains human-reviewed unless a separately approved server-safe branch exists;
- arbitrary deletion is never used to make the alert disappear.

## 2. Trigger

Primary triggers:
- Autotask/DRMM ticket title contains Low Disk Space;
- DRMM volume monitor reports a configured low-free-space threshold;
- an existing Jason-owned ticket explicitly asks for investigation of a nearly full Windows volume.

Jason confirms the affected volume and current condition rather than assuming the triggering alert is still current.

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
7. Search recent related tickets and DRMM activity history before dispatching a diagnostic that may already have run.
8. If device identity, drive identity, or client scope is ambiguous, set state identification_blocked and stop.

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

identified -> diagnosing -> candidate_cleanup -> remediating -> verifying -> complete

Waiting/exception states:
- waiting_endpoint
- human_review_server
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

Use an approved read-only diagnostic to identify:
- largest top-level folders;
- largest relevant subfolders;
- top large files;
- obvious temporary/cache/log accumulation;
- Windows update/component-store context where supported.

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

### Step 5: Check storage-health evidence

Inspect available evidence for:
- Event ID 7/bad block;
- NTFS/file-system errors;
- controller/disk warnings;
- SMART/storage-health warnings where governed evidence exists;
- repeated unexpected shutdowns associated with storage issues.

If storage-health risk is present, prioritize preservation/escalation over cleanup.

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

Permitted only after separate autonomy promotion for the exact capability/target class.

Examples may include:
- an approved AOT cleanup component;
- an independently proven orphaned C:\Sysmon accumulation when the approved cleanup contract explicitly covers it;
- another explicitly cataloged temporary/cache target.

### B. Server or protected-role cleanup

Set state human_review_server. Jason gathers evidence and proposes the exact cleanup. No autonomous cleanup under this baseline.

### C. Unknown large file/folder

Set state unknown_large_data. Document path, size, owner/application context when available, and recommended technician action. Do not delete.

### D. Storage-health risk

Set state storage_health_risk. Do not focus on space recovery alone. Escalate for hardware/storage investigation and preserve evidence.

## 10. Retry Policy

- Read failures: bounded re-read of the same evidence request; never convert a read failure into cleanup authority.
- Cleanup: maximum one autonomous attempt per exact target unless an action-specific policy explicitly permits a second bounded attempt.
- Never rerun while prior job state is active/unknown.
- If verification fails, stop and escalate rather than chaining increasingly aggressive deletion.

## 11. Periodic Rechecks

Recheck when:
- endpoint was offline;
- an approved cleanup job is pending;
- monitoring needs propagation time;
- a dependency/approval is awaited.

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

Use concise internal notes. For each meaningful session include:
- drive/volume;
- total size, free space, free percentage;
- file system / relevant drive details;
- BitLocker enabled/protection state;
- major space consumers;
- DRMM activity-history result;
- C:\Sysmon existence/size/status when relevant;
- storage-health indicators;
- exact diagnostic/cleanup capability and job/correlation IDs;
- interpretation and next step.

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
- alert read
- automation.component.search
- automation.component.execute for approved diagnostics/remediation
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
2. current volume baseline;
3. BitLocker status;
4. recent DRMM activity check;
5. read-only largest-folder/file analysis;
6. C:\Sysmon check;
7. server/workstation gate;
8. no arbitrary deletion;
9. bounded approved cleanup only if a safe target is positively identified and authority exists;
10. terminal job readback;
11. independent free-space verification;
12. alert/ticket documentation;
13. #261 remains regression-covered as a fixed authorization path; #265 stale/unknown job state fails closed without duplicate dispatch.

No unrelated production object may be modified.

## 22. Section Goal Closure

Close after:
- playbook is merged;
- required diagnostic/read capabilities are reliable;
- #261 remains fixed under regression coverage and #265 stale-job handling is resolved or safely classified;
- controlled workstation acceptance succeeds;
- server human-review behavior is proven;
- safe cleanup capability scopes are separately approved for autonomy;
- Grafana/Project Jason status and remaining TODOs are updated.
