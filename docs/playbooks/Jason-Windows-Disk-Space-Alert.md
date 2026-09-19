# Jason Playbook: Windows Disk Space Alert

Status: Pilot v0.1.0. Manual controlled acceptance only; not enabled for automatic production execution.

## 1. Section Goal
Process a Windows disk-space monitoring ticket from exact ticket/company/device/alert identification through current-space diagnosis, bounded decision, authoritative verification, and documented completion or escalation. First acceptance is diagnostic-only.

## 2. Trigger
Autotask/DRMM monitoring ticket reporting a Windows fixed volume at or above its configured used-space threshold.

## 3. Scope and Boundaries
Same-client Autotask ticket/CI and DRMM endpoint/alert only. No cross-client evidence. No direct provider bypass. Cleanup, deletion, service interruption, reboot, or other modifying/disruptive action is outside the first acceptance and remains separately governed.

## 4. Initial Identification
Resolve exact ticket, company, active Autotask CI, DRMM endpoint UID/hostname/site, and originating alert UID. Ambiguity blocks the run.

## 5. Expected State
The monitored volume is below the alert threshold with sufficient headroom for normal operations. A historical ticket threshold breach is not proof the condition still exists.

## 6. State Model
Uses generic persisted `PlaybookRun`: `triggered -> identifying -> diagnosing -> deciding -> verifying -> complete`, with `awaiting_approval`, `recheck_pending`, `blocked`, and `escalated` as needed.

## 7. Diagnostic Workflow
First run `Get free hard drive (disk) space AOT Ver 09182025-1` (UID `68aed44a-af02-4ecb-9d57-e11296531356`) to establish current free/used space. If current evidence still shows material pressure and more diagnosis is warranted, `Comprehensive Disk & Storage Diagnostic [WIN] AOT Ver 07232026` (UID `c97df7f4-ae3d-4b8c-aae3-68accc68144f`) is the preferred broader read-only follow-up. Do not run cleanup as part of first acceptance.

## 8. Decision Gates
Require exact object identity, endpoint online/available, current disk evidence, and correct volume before any next step. If healthy now, verify alert state before closure. If still full, determine whether further read-only diagnostics or a separately authorized remediation proposal is appropriate.

## 9. Remediation
Not part of first live acceptance. Any deletion/cleanup/storage modification is modifying and requires the applicable existing governance/approval. Reboot remains disruptive and instance-specific approval-required.

## 10. Retry Policy
Maximum two diagnostic attempts when evidence indicates a retry is reasonable. No blind repeats.

## 11. Periodic Rechecks
Offline/unavailable endpoints may enter `recheck_pending`; rechecks must be bounded and de-duplicated.

## 12. Aging / Stale Condition
Repeated or persistent disk pressure should trigger investigation for growth source, retention/log issues, backup/cache accumulation, stale data, or capacity planning instead of indefinite cleanup.

## 13. Dependency Handling
Missing device mapping, unavailable component output, or unavailable alert evidence blocks the run and is documented rather than guessed.

## 14. Documentation Requirements
Record ticket/device/alert identity, diagnostic component/job/correlation references, result, interpretation, decision, verification, and final disposition. Never record secrets.

## 15. Failure Handling
Failed or missing diagnostic output does not count as healthy verification and does not advance to completion.

## 16. Escalation Criteria
Escalate ambiguous identity, repeatedly failed diagnostics, critically low free space with no safe standing remediation, evidence of storage/filesystem health issues, or repeated threshold recurrence.

## 17. Verification
Resolution requires current authoritative disk-space evidence plus healthy/cleared monitoring state where available. Component success alone is insufficient.

## 18. Completion Criteria
Complete only after exact identity, current disk evidence, healthy-state verification, and final documentation. First acceptance may intentionally stop in `deciding` or `blocked` without modifying the endpoint.

## 19. Final Resolution Note
Summarize original threshold condition, current free/used state, diagnostic evidence, any root cause/remediation, verification timestamp, and final alert/ticket disposition.

## 20. Required Capabilities
Autotask ticket/configuration reads; DRMM endpoint/alert reads; governed component discovery/execution; persisted generic PlaybookRun; Grafana live-run telemetry; later alert/ticket closure capabilities only after verification.

## 21. Acceptance Test
Use real ticket `T20260919.0012` for Hitt Electric Corp. / `WIN-PF34UO3QMOL`. Prove exact ticket-company-CI-endpoint-alert binding, persisted run creation/resume, Grafana visibility, read-only disk diagnostic, evidence capture, and safe stop before modifying remediation.

## 22. Section Goal Closure
Close the first-live-run milestone after the run persists, Grafana reports it, current disk evidence is captured or a governed blocker is recorded, no unrelated object is changed, and remaining production workflow gaps are documented.
