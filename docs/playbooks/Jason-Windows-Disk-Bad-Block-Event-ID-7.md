# Jason Playbook — Windows Disk Bad Block / Event ID 7

## 1. Section Goal

Jason must investigate Windows disk Event ID 7 / bad-block alerts, positively identify the physical disk that generated the event, and distinguish removable/external media from an internal disk.

Success:
- If the affected disk is conclusively removable/external: document the evidence, resolve the DRMM alert, and complete the associated Autotask ticket when otherwise healthy.
- If the affected disk is conclusively internal: document the evidence, move the associated Autotask ticket to Help Desk I, and notify the affected user once an approved notification template is available.
- If disk identity is ambiguous or evidence conflicts: fail closed and escalate for technician review.

## 2. Trigger

Apply when DRMM reports a Windows System event matching:
- Provider/source: `disk`
- Event ID: `7`
- Typical message: `The device, \\Device\\HarddiskX\\DRX, has a bad block.`

Also apply to an associated Autotask monitoring ticket when present.

## 3. Scope and Boundaries

In scope:
- Windows workstations and laptops.
- DRMM alert/device/audit/history reads.
- Read-only physical-disk, SMART, reliability, controller, filesystem, and storage-event diagnostics.
- Autotask documentation, alert resolution, ticket completion, or Help Desk I escalation.
- Approved user notification templates when available.

Out of scope:
- Disk replacement.
- Formatting or partition modification.
- Destructive testing.
- CHKDSK repair/offline repair.
- Firmware or driver modification.
- Reboot/shutdown or other user-disruptive actions.

Preserve Central Orchestrator authority, requester grants, provider/client isolation, approval rules, audit trail, and `direct_provider_access=false`.

## 4. Initial Identification

Record:
- Client/site.
- Endpoint hostname and DRMM UID.
- Associated Autotask ticket and configuration item when available.
- DRMM alert UID.
- Alert timestamp.
- Exact Event ID 7 text.
- Reported `HarddiskX/DRX`.
- Endpoint online/offline state.
- Logged-on user when available.

If endpoint, ticket, or disk identity cannot be established, set `state = identification_blocked`, document the reason, and escalate rather than guessing.

## 5. Expected State

Healthy expected state:
- Internal storage reports healthy.
- No authoritative evidence shows recurring Event ID 7 or related storage faults on an internal disk.
- Removable-media errors are clearly attributable to removable/external media.
- No stale unresolved DRMM alert remains after successful classification and documentation.

## 6. State Model

Primary:
`identified -> diagnosing -> disk_classified -> verifying -> complete`

Removable path:
`disk_classified_removable -> resolving -> complete`

Internal path:
`disk_classified_internal -> escalating -> escalated`

Exception paths:
`identification_blocked`
`diagnostic_blocked`
`evidence_conflict`

Persist the state so Jason can resume without repeating completed work.

## 7. Diagnostic Workflow

### A. Confirm the alert
Purpose: establish the exact storage object reported by Windows.

Evidence:
- DRMM open alert.
- Exact Event ID 7 message.
- Alert timestamp and device UID.

Do not infer a drive letter from `HarddiskX`.

### B. Review DRMM endpoint/audit
Purpose: determine current fixed/removable logical disks and attached storage.

Collect:
- Fixed logical disks.
- Removable logical disks.
- Attached USB/portable-storage devices.
- Current disk free space and basic endpoint health.

This is supporting evidence, not final classification.

### C. Run the approved read-only storage diagnostic
Preferred component:
`Comprehensive Disk & Storage Diagnostic [WIN] AOT Ver 07232026`

Capture:
- Datto job UID.
- Terminal job status.
- StdOut/StdErr.
- Physical disk number.
- Model and serial when available.
- Bus/media type.
- Operational status.
- SMART/reliability information.
- Partition/volume association.
- USB/removable device information.
- Related storage-event history.

The component must remain read-only.

### D. Map HarddiskX to the physical disk
Examples of removable evidence:
- `Disk 1 — Generic Mass-Storage`
- USB or SD bus/media.
- `No Media` on a removable storage reader/device.

Examples of internal evidence:
- NVMe/SATA/fixed disk permanently installed in the endpoint.
- Physical disk associated with the Windows system volume or another internal fixed volume.

Do not classify solely from disk number.

### E. Check recurrence
Review relevant storage events, especially:
- 7
- 9
- 11
- 51
- 55
- 57
- 98
- 129
- 140
- 153
- 154
- 157

Correlate timestamps with USB insertion/removal, sleep/resume, docking, backup jobs, power events, and other storage activity where evidence is available.

## 8. Decision Gates

### Gate 1 — Is the affected disk positively identified?
- No: document and escalate for technician review.
- Yes: continue.

### Gate 2 — Is it removable/external?
- Yes: removable resolution path.
- No: continue.

### Gate 3 — Is it internal?
- Yes: internal escalation path.
- No/uncertain: evidence-conflict path.

### Gate 4 — Does evidence conflict?
If SMART, Windows event data, DRMM inventory, and disk mapping disagree, do not auto-close. Set `state = evidence_conflict` and escalate.

## 9. Remediation

### Removable/external disk
Authority: non-destructive/modifying ticket and alert state only.

Preconditions:
- Physical disk mapping is authoritative.
- Internal storage is not implicated.
- No critical internal-storage finding remains unresolved.

Actions:
1. Write diagnostic evidence to the ticket.
2. Resolve the DRMM Event ID 7 alert.
3. Complete the associated Autotask ticket if no other unresolved condition exists.
4. Add final resolution note.

### Internal disk
Authority: ticket routing/documentation only.

Actions:
1. Do not classify the condition as harmless.
2. Document physical disk identity, model/serial, health evidence, and recurrence.
3. Move the ticket to Help Desk I.
4. Keep the incident open for technician/hardware review.
5. Send the approved user notification template once that capability is available.

Do not automatically run repairs or disruptive actions.

## 10. Retry Policy

- Maximum one normal execution of the comprehensive diagnostic per incident.
- If the Datto job remains active longer than expected, poll the same job; do not redispatch.
- If the job reaches a failed/terminal state without useful evidence, use an approved narrower read-only diagnostic once or escalate.
- Never loop indefinitely.

## 11. Periodic Rechecks

Normally not required after positive disk classification.

If waiting on a Datto diagnostic job:
- Recheck the same job.
- Do not submit a duplicate job.
- Stop after terminal completion, failure, ticket closure, or escalation.

## 12. Aging / Stale Condition

Old Event ID 7 alerts still require classification before closure.

If the device has been replaced, storage configuration changed, removable media is no longer present, or the event is too old to map reliably:
- Document the limitation.
- Do not claim the internal disk is healthy solely because the event is old.
- Escalate when positive classification is not possible.

## 13. Dependency Handling

Dependencies:
- DRMM endpoint and alert reads.
- DRMM audit/history reads.
- Approved read-only storage diagnostic.
- Datto job/output reads.
- Autotask ticket association and internal notes.
- Autotask queue/status/complete mutations.
- DRMM alert resolution.
- Future approved notification-template selection/delivery.

If the notification-template capability is unavailable, internal-drive escalation proceeds and the ticket note records:
`User notification pending approved notification-template capability.`

Suppress duplicate dependency tickets.

## 14. Documentation Requirements

Suggested note titles:
- `Jason - Disk Event ID 7 - Asset Validation`
- `Jason - Disk Event ID 7 - Diagnostic`
- `Jason - Disk Event ID 7 - Recheck`
- `Jason - Disk Event ID 7 - Escalation`
- `Jason - Disk Event ID 7 - Resolution`

Include:
- What was checked and why.
- Target/device and timestamp.
- Alert UID and exact Event ID.
- Diagnostic component and Datto job UID.
- Physical disk mapping.
- SMART/reliability/storage-event summary.
- Interpretation.
- Resulting decision and next step.

Never record secrets.

## 15. Failure Handling

Document and escalate when:
- Physical-disk mapping fails.
- Diagnostic output is incomplete.
- Endpoint is offline and evidence cannot be gathered.
- Provider reads fail.
- Diagnostic job fails or produces contradictory output.
- Required mutation authority is denied.

Do not silently skip failed steps.

## 16. Escalation Criteria

Move to Help Desk I when:
- Event ID 7 positively maps to an internal drive.

Escalate for technician review when:
- Disk identity cannot be established.
- SMART/reliability data indicates degradation.
- Repeated storage events indicate internal instability.
- Multiple storage subsystems appear unhealthy.
- Evidence conflicts.
- A disruptive or repair action would be required.

## 17. Verification

### Removable path
Verify:
- Disk is positively classified as removable/external.
- Internal system disk is not implicated.
- No critical internal-storage finding remains.
- Ticket documentation is complete.
- DRMM alert resolves successfully.
- Autotask ticket completes successfully.

### Internal path
Verify:
- Internal disk identity is positive.
- Evidence is documented.
- Ticket is successfully moved to Help Desk I.
- User notification is sent once an approved template capability exists.

## 18. Completion Criteria

### Removable
Complete when classification is authoritative, internal storage is not implicated, the alert is resolved, the ticket is completed, and the final resolution note exists.

### Internal
Jason's playbook processing is complete when internal disk identity and evidence are documented, the ticket is moved to Help Desk I, and notification is sent when supported. The underlying incident remains open for Help Desk handling.

## 19. Final Resolution Note

Removable example:

`Event ID 7 referenced Harddisk1. Read-only storage diagnostics mapped Disk 1 to removable/USB mass-storage rather than the internal system drive. No definitive active internal-disk failure was identified. DRMM alert resolved and ticket completed.`

Internal example:

`Event ID 7 was positively mapped to an internal storage device. Storage-health evidence has been documented and the ticket moved to Help Desk I for technician/hardware review.`

## 20. Required Capabilities

Narrow required capabilities:
- DRMM endpoint read.
- DRMM endpoint audit.
- DRMM current/historical alert read.
- Approved read-only storage diagnostic execution.
- Datto job status/output read.
- DRMM alert resolution.
- Autotask ticket read.
- Autotask internal-note creation.
- Autotask queue/status update.
- Autotask ticket completion.
- Persisted playbook state.

Future:
- Approved Autotask user-notification-template selection/delivery.

## 21. Acceptance Test

### Removable-media acceptance case
Use TUS-50896 at Terramar.

Observed evidence from 2026-09-22:
- Event ID 7 referenced `\\Device\\Harddisk1\\DR1`.
- `Comprehensive Disk & Storage Diagnostic [WIN] AOT Ver 07232026` completed.
- Diagnostic reported `CRITICAL_FINDINGS=0`.
- Diagnostic reported `Disk 1, Generic Mass-Storage` as offline / `No Media`.
- USB storage devices were present in diagnostic evidence.
- Diagnostic conclusion: no definitive active disk failure was confirmed.

Acceptance expectation:
- Jason classifies this as removable/external media.
- Jason documents the evidence.
- Jason resolves the DRMM alert.
- Jason completes the associated ticket when otherwise healthy.

### Internal-disk acceptance case
Use a controlled/safe test or verified real case.

Acceptance expectation:
- Jason positively maps Event ID 7 to an internal disk.
- Jason does not auto-close.
- Jason documents evidence.
- Jason moves the ticket to Help Desk I.
- Notification behavior is tested once approved templates exist.

## 22. Section Goal Closure

Close the Section Goal only after:
- Playbook is present in Project Jason.
- Removable branch is tested.
- Internal branch is tested.
- DRMM alert resolution is validated.
- Autotask queue/status/complete actions are validated.
- Notification-template capability is implemented/tested.
- Grafana/Project Jason status is updated as needed.
- Remaining implementation gaps are recorded in TODO/support tracking.

## 23. Autonomous Execution Eligibility

`autonomous_allowed: false`

Approval owner: pending.
Approval date: pending.
Approved version/fingerprint: pending.

Initial version is not autonomous until acceptance testing succeeds and the owner explicitly approves the exact playbook version for autonomy.

Recommended eventual autonomous scope:
- Read diagnostics.
- Physical-disk classification.
- Evidence collection and documentation.
- Resolve alert and complete ticket when removable/external classification is conclusive.
- Move conclusively internal-drive cases to Help Desk I.
- Send a pre-approved notification template once available.

Actions that remain approval-bound:
- Reboot/shutdown.
- Disk repair.
- CHKDSK repair/offline repair.
- Firmware changes.
- Driver changes.
- Storage configuration changes.
- Hardware replacement.
- Any equivalent user-disruptive action.

Material playbook changes invalidate autonomous approval until re-reviewed.
