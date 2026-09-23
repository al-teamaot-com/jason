# Jason Playbook: Windows Disk Space Alert

Status: Pilot v0.3.0. Manual controlled acceptance only; not enabled for automatic production execution.

## 1. Section Goal
Process a Windows disk-space monitoring ticket from exact ticket/company/device/alert identification through current-space diagnosis, bounded decision, authoritative verification, and documented completion or escalation. First acceptance is diagnostic-only.

## 2. Trigger
Autotask/DRMM monitoring ticket reporting a Windows fixed volume at or above its configured used-space threshold.

## 3. Scope and Boundaries
Same-client Autotask ticket/CI and DRMM endpoint/alert only. No cross-client evidence. No direct provider bypass.

Workstations may proceed through bounded diagnostic and separately governed low-risk cleanup when the evidence supports it. Servers require human review before cleanup, deletion, storage expansion, service interruption, reboot, or other modifying/disruptive action. An active user session is a decision input: do not clear browser caches, Recycle Bin content, user data, or take any disruptive action merely to gain space while a user is active unless separately approved.

## 4. Initial Identification
Resolve exact ticket, company, active Autotask CI, DRMM endpoint UID/hostname/site, and originating alert UID. Ambiguity blocks the run.

## 5. Expected State
The monitored volume is below the alert threshold with sufficient headroom for normal operations. A historical ticket threshold breach is not proof the condition still exists.

## 6. State Model
Uses generic persisted `PlaybookRun`: `triggered -> identifying -> diagnosing -> deciding -> verifying -> complete`, with `awaiting_approval`, `recheck_pending`, `blocked`, and `escalated` as needed.

## 7. Diagnostic Workflow
### Step 1: Confirm current pressure
Use authoritative current evidence first. Prefer DRMM `endpoint.audit.read` logical-disk data when it is current enough; otherwise use a governed disk-space diagnostic. `Get free hard drive (disk) space AOT Ver 09182025-1` (UID `68aed44a-af02-4ecb-9d57-e11296531356`) is known to write AOT disk-alert cooldown state while collecting evidence and therefore must not be treated as purely read-only. Prefer the replacement `JASON | Disk Space | Diagnose [WIN] v1.0` when published. `Comprehensive Disk & Storage Diagnostic [WIN] AOT Ver 07232026` (UID `c97df7f4-ae3d-4b8c-aae3-68accc68144f`) is the preferred broader diagnostic follow-up.

### Step 1A: Post internal drive-baseline note
After current disk evidence is established and before remediation, add an internal Autotask note titled `Jason - Disk Space - Drive Baseline`. This note is mandatory when an Autotask ticket exists.

Record, when available:
- endpoint hostname and affected drive/volume;
- drive role (system/data) and volume label;
- filesystem;
- total capacity;
- used space in GB/GiB and percent;
- free space in GB/GiB and percent;
- configured monitor threshold;
- minimum additional free space required to return below the threshold;
- physical disk model/media type and health/SMART summary when available;
- filesystem/volume health and dirty-bit/CHKDSK status when available;
- whether the device is a workstation or server;
- current online/offline state and evidence freshness/last-audit timestamp when available;
- active-session evidence when available; distinguish a proven active session from DRMM `last_logged_in_user` history and never treat the latter alone as proof that a user is currently active;
- current alert UID/timestamp and whether the reading is current or historical;
- reboot-required state when available.

Do not invent unavailable fields. Prefer current authoritative DRMM/provider evidence over values copied from an older alert. If later remediation changes capacity usage, add a verification note with the before/after values rather than overwriting the baseline.

### Step 2: Check prior remediation history before repeating cleanup
Search DRMM alert/activity evidence and related Autotask ticket notes for prior disk-cleanup component runs on the same endpoint. Record the most recent cleanup timestamps and before/after free-space results when available. A prior cleanup that produced only trivial improvement is evidence that repeating the same cleanup is unlikely to resolve the condition.

Decision: if cleanup has already run recently or repeatedly with little durable gain, do not blindly rerun it. Advance to root-cause/storage-consumer analysis.

### Step 3: Determine whether the problem is recurring
Compare current free space with prior disk alerts/tickets. Distinguish a one-time transient condition from repeated pressure over days/weeks/months. Recurrence after successful cleanup suggests persistent growth, retained business data, application/cache/log accumulation, backup data, update artifacts, profiles, or undersized storage rather than a simple temp-file problem.

### Step 4: Identify the storage consumers
Before deleting data, identify the largest directories/files and relevant age/growth pattern. Prefer `Drive or Folder Size Report - AOT Ver 11142024` (UID `8b7f7b3d-6462-40ca-9415-71232aecdb1f`) with `RootFolder=C:\\` for recursive folder-size evidence; it reports folders over 1 GB and overall drive utilization. If file-level ranking is needed, use `Get Largest Files and Folders on Disk (DattoSize) [WIN]` (UID `e48c6d3d-bd12-4ce5-b0a0-0e44bc3ac25a`) with the target drive and an appropriate bounded result depth. The comprehensive disk/storage diagnostic remains appropriate for filesystem, SMART, VSS, controller, and storage-health evidence, but should not substitute for consumer-size analysis when the question is what is using the space. Inspect at minimum: Windows temp/update/cache locations, user profiles and Downloads/Desktop/Documents, application data/logs, crash dumps, installer/package caches, backup/staging directories, recycle bin, virtualization/container data where applicable, and unusually large individual files. Do not infer that the largest item is safe to delete.

### Step 4A: Sysmon archive branch
If a dominant storage consumer is `C:\\Sysmon` or another configured Sysmon `ArchiveDirectory`, treat it as a security-evidence archive rather than ordinary temporary data. Microsoft documents that Sysmon Event ID 23 archives deleted files into `ArchiveDirectory` (default `C:\\Sysmon`) and that the directory may grow to an unreasonable size.

Before deletion:
- confirm the exact archive path and its total bytes/GiB plus file count;
- capture oldest/newest file timestamps when practical to establish retained-history range;
- read the Sysmon service state and `PathName`; verify the live Sysmon executable is not located inside the candidate archive directory;
- confirm the candidate directory has the expected hidden/system and SYSTEM-protected characteristics when present;
- determine whether file-delete archiving is currently configured/enabled when authoritative configuration evidence is available;
- check for an active security incident, EDR/AV investigation, legal/evidence hold, or ticket requiring preservation of deleted-file artifacts. Any such condition blocks deletion and escalates to security review.

A stopped Sysmon service or an executable path outside the archive directory is supporting evidence only; neither alone authorizes deletion. Do not delete an arbitrary folder merely because it is named `Sysmon`.

If the exact archive is validated, no preservation hold exists, and the device is a workstation, removal of the archived copies is a modifying/security-sensitive action and requires explicit governed approval. Servers always require human review under the server gate. Do not autonomously disable Sysmon, change its configuration, or convert Event ID 23 behavior to Event ID 26; configuration/retention changes require separate security-policy review.

Deletion procedure:
1. Attempt deletion only against the exact validated archive path.
2. If recursive removal fails with access denied, stop and inspect stderr plus parent/child ACL ownership. Do not blindly retry.
3. When the job is executing as SYSTEM and evidence confirms the protected tree is the validated Sysmon archive, a governed ACL-reset cleanup may reset ACLs only within that exact archive tree, clear blocking read-only attributes where required, and retry deletion.
4. Never broaden ACL reset, ownership, or deletion to the volume root, Windows directory, user profiles, or any sibling path.
5. For a large archive, maintain one authoritative cleanup job. Poll the same job/output until terminal; do not dispatch concurrent duplicate deletes.
6. After completion, re-read disk space and re-check the archive path. If archiving remains enabled, the directory may be recreated; record that fact and evaluate retention/configuration policy separately so the condition does not silently recur.

### Step 5: Check operational context
Determine endpoint role (workstation/server), current logged-on user/session, reboot requirement, related disk/filesystem alerts, pending patches, and whether a recent cleanup or update is already in progress. On a workstation with an active user, favor diagnostics and system-safe cleanup only. On a server, stop for human review before modifying storage.

Do not run cleanup merely because an alert exists; remediation must be justified by current evidence and history.

## 8. Decision Gates
Require exact object identity, endpoint online/available, current disk evidence, correct volume, endpoint role, active-user context, and remediation history before any next step.

- If healthy now: verify alert state before closure.
- If still full and no cleanup has been attempted recently: identify likely safe reclaimable categories before proposing cleanup.
- If cleanup has already run with minimal gain: do not repeat the same cleanup; identify largest consumers/root cause first.
- If the dominant consumer is a Sysmon archive: validate archive identity, security-preservation status, service/configuration context, and exact size before proposing deletion; any active investigation/evidence-hold condition blocks cleanup.
- If the same endpoint repeatedly returns below threshold after prior cleanup: treat as recurring capacity/growth and investigate source or capacity planning.
- If filesystem/disk-health evidence is abnormal: stop cleanup and escalate for storage-health investigation.
- If server: require human review before modifying storage.
- If workstation with active user: prohibit browser-cache, Recycle Bin, user-file deletion, reboot, or other user-disruptive cleanup without separate approval.

## 9. Remediation
Remediation is evidence-driven and separately governed.

For a workstation, `Disk Cleanup [WIN]` (UID `6b00547c-94ae-44cb-8ecb-d5f804c147ec`) may be proposed only after Steps 1-5. A conservative active-user pass should favor system/user Temp, Windows Error Reporting, crash dumps/minidumps, and stale RMM component cache where appropriate. Do not include browser caches, Prefetch, font cache, Windows Update cache, Recycle Bin, or user files unless the evidence specifically supports them and the required approval/user-impact gate is satisfied.

If a validated Sysmon archive is the dominant consumer, do not treat it as ordinary temp cleanup. Record archive size/file count and service/configuration evidence, check preservation requirements, then request explicit governed approval for archive removal on a workstation. If deletion encounters SYSTEM ACL protection, use the bounded ACL-aware procedure in Step 4A and keep all ACL changes scoped to the exact validated archive tree. Do not change Sysmon retention/configuration as part of disk cleanup.

Before repeating the same cleanup component, compare prior before/after results. If prior executions yielded only marginal improvement, skip repetition and investigate the largest storage consumers instead.

Deletion of business/user data, uninstalling software, changing retention, expanding/shrinking partitions, storage migration, or server cleanup is modifying/high-impact work and requires explicit human review/approval. Reboot remains disruptive and instance-specific approval-required.

## 10. Retry Policy
Maximum two attempts for the same diagnostic when evidence indicates a retry is reasonable. No blind repeats. A cleanup component is not a generic retry: do not run the same cleanup again solely because free space remains low. Require new evidence showing that additional reclaimable data has accumulated or a different cleanup category is justified. For a large Sysmon archive deletion, an active cleanup job is authoritative: poll that same job and its stdout/stderr until terminal instead of launching a second deletion. An access-denied result requires ACL/path evidence review before any governed retry.

## 11. Periodic Rechecks
Offline/unavailable endpoints may enter `recheck_pending`; rechecks must be bounded and de-duplicated.

## 12. Aging / Stale Condition
Repeated or persistent disk pressure must trigger root-cause/capacity investigation instead of indefinite cleanup. Compare prior ticket/alert dates, before/after cleanup gains, and current free space. Escalate recurring cases where cleanup provides only temporary or negligible relief, where free space repeatedly falls below threshold, or where the same large consumer continues to grow.

## 13. Dependency Handling
Missing device mapping, unavailable component output, or unavailable alert evidence blocks the run and is documented rather than guessed.

## 14. Documentation Requirements
A `Jason - Disk Space - Drive Baseline` internal note is required before remediation whenever an Autotask ticket exists. It must capture the current drive specification/baseline defined in Step 1A. Record ticket/device/alert identity, current free/used space, endpoint role, active-user context, prior disk alerts/tickets, prior cleanup timestamps and before/after results, diagnostic component/job/correlation references, largest storage consumers identified, remediation rationale, exact cleanup options used, result, interpretation, decision, verification, and final disposition. Never record secrets.

For a Sysmon archive case, also document the exact archive path, measured bytes/GiB, file count, service state/path, available archiving/configuration evidence, preservation/security-ticket check, deletion job/correlation IDs, ACL failure/fallback details if encountered, and whether the archive was absent or recreated after cleanup.

After remediation or other material change, add `Jason - Disk Space - Verification` with post-action total/used/free values, percentage change, reclaimed space, monitor-threshold status, and alert state. Preserve the original baseline note for comparison.

## 15. Failure Handling
Failed or missing diagnostic output does not count as healthy verification and does not advance to completion.

## 16. Escalation Criteria
Escalate ambiguous identity, repeatedly failed diagnostics, critically low free space with no safe standing remediation, evidence of storage/filesystem health issues, server remediation needs, suspected business/user-data deletion, or repeated threshold recurrence. Also escalate when prior cleanup executions repeatedly gain little space, when a dominant storage consumer cannot be safely classified, or when capacity is fundamentally undersized for the observed workload. For Sysmon archives, escalate any active security investigation/evidence hold, inability to prove the archive path, unexpected service executable placement, unknown retention intent, repeated rapid archive regrowth, or need to alter Sysmon configuration/retention.

## 17. Verification
Resolution requires current authoritative disk-space evidence plus healthy/cleared monitoring state where available. Component/job success alone is insufficient. Record post-remediation free bytes/GB and percentage, compare against the pre-remediation baseline, and verify the gain is durable enough to satisfy the configured monitor threshold. For a Sysmon archive cleanup, also verify the exact archive path is absent or has only a newly recreated bounded footprint, and record whether Sysmon archiving remains enabled so recurrence risk is explicit. If the alert remains open only because of stale monitor state, verify the current disk condition independently before resolving the stale alert.

## 18. Completion Criteria
Complete only after exact identity, current disk evidence, remediation-history review, healthy-state verification, and final documentation. If cleanup produced insufficient durable headroom, do not close merely because the component completed; document the root-cause/capacity finding and escalate or continue with an approved corrective plan. First acceptance may intentionally stop in `deciding` or `blocked` without modifying the endpoint.

## 19. Final Resolution Note
Summarize original threshold condition, baseline total/used/free values, final total/used/free values, net space reclaimed, diagnostic evidence, root cause/remediation, verification timestamp, monitor/alert state, and final ticket disposition.

## 20. Required Capabilities
Autotask ticket/configuration reads; DRMM endpoint/alert reads; governed component discovery/execution; persisted generic PlaybookRun; Grafana live-run telemetry; later alert/ticket closure capabilities only after verification.

## 21. Acceptance Test
Retain `T20260919.0012` for Hitt Electric Corp. / `WIN-PF34UO3QMOL` as the original diagnostic-only acceptance case. Use `T20260923.0003` / `HITT-WS-06` as the remediation-history/root-cause/Sysmon-archive acceptance case. The HITT-WS-06 evidence set includes a `C:\\Sysmon` archive measured at 426.39 GiB across approximately 316,000 files, a stopped `sysmon64` service whose executable path was `C:\\WINDOWS\\sysmon64.exe`, and an initial recursive deletion failure caused by access-denied protection within the SYSTEM-owned archive tree. Acceptance must prove that Jason posts the required internal drive-baseline note, discovers prior cleanup history (including before/after free-space evidence), refuses to blindly repeat an ineffective cleanup, identifies the dominant archive, validates that the archive is not the live Sysmon executable location, checks evidence-preservation/security state, requires governed approval before deleting archived security artifacts, handles protected-child ACL failure without broadening scope, polls one authoritative long-running cleanup job rather than redispatching, verifies post-cleanup free space and archive state, preserves active-user/server safeguards, and documents the decision before and after modifying action.

## 22. Section Goal Closure
Close the first-live-run milestone after the run persists, Grafana reports it, current disk evidence is captured or a governed blocker is recorded, no unrelated object is changed, and remaining production workflow gaps are documented.
