# Jason Playbook Candidate — Entra Device Trust / Windows Hello Recovery

```yaml
playbook:
  id: PB-ENTRA-DEVICE-TRUST-001
  name: Entra Device Trust and Windows Hello Recovery
  version: 0.1.0-candidate
  owner: AOT MSP Engineering
  target_type: endpoint
  trigger:
    provider: Autotask/Datto RMM
    match: "PIN/Windows Hello error, Entra device-authentication failure, or failed device key-sign test"
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 1
  recheck:
    enabled: true
    cadence: on_next_user_signin_then_technician_check
    stale_after: 2_days
  verification:
    authoritative_source: local_dsregcmd_and_Entra_directory
    success_condition: "AzureAdJoined YES; DeviceAuthStatus SUCCESS; AadRecoveryEnabled NO; KeySignTest PASSED; user PIN enrollment separately verified"
  completion:
    terminal_disposition: Complete_or_Human_Review
  autonomy:
    allowed_branches: [read_only_diagnosis, evidence_correlation, non_disruptive_recheck]
    approval_bound_branches: [policy_change, managed_repair]
    disruptive_branches: [forced_signout, reboot, leave_or_rejoin, TPM_reset, credential_store_deletion]
```

## 1. Section Goal
Restore and verify Entra device trust, then separately confirm Windows Hello PIN setup. No false resolution when device signing is repaired but user PIN enrollment has not been tested.

## 2. Trigger
Autotask user report of PIN enrollment failure or device logs show `DeviceAuthStatus: FAILED`, `AadRecoveryEnabled: YES`, or `KeySignTest: FAILED`.

## 3. Scope and Boundaries
Windows Entra-joined managed endpoints with governed DRMM access; tenant-scoped read-only Microsoft Graph device lookup. Never run `dsregcmd /leave`, clear TPM, delete NGC, force sign-out/reboot, or modify tenant/device policy without independent specific approval. No assumption that SYSTEM diagnostics describe a user's PRT/WAM state. Existing central orchestrator, exact grants, `direct_provider_access=false`, and isolation stay mandatory.

## 4. Initial Identification
Resolve ticket, requester, tenant, endpoint, DRMM and Autotask configuration item. Associate the unique same-company CI before work, execute required Jason queue/In Progress/Remote Support start/readback, and record the device ID and relevant log timestamps. Stop on mismatch or ambiguity.

## 5. Expected State
Device Entra-joined; directory device exists and is enabled; registered certificate valid and private-key capable; `DeviceAuthStatus: SUCCESS`; `KeySignTest: PASSED`; `AadRecoveryEnabled: NO`. User Windows Hello PIN setup succeeds if required by customer policy.

## 6. State Model
`detected -> owned -> identified -> diagnosing -> classified -> waiting_user_signin | waiting_approval | remediating | verifying -> verified_device_trust -> waiting_pin_confirmation -> complete`; alternate `blocked`, `human_review`, `escalated`. Persist endpoint/tenant IDs, observed evidence fingerprints, last action, approval state, recheck trigger and correlation/job IDs.

## 7. Diagnostic Workflow
1. Governed endpoint read or SYSTEM DRMM component: `dsregcmd /status`. Capture `AzureAdJoined`, `DeviceAuthStatus`, `KeyProvider`, `TpmProtected`, `AadRecoveryEnabled`, `KeySignTest`, certificate validity. System-level `AzureAdPrt/IsUserAzureAD/WamDefaultSet/NgcSet` do NOT establish interactive user state.
2. Read TPM presence/readiness/lockout with `Get-Tpm`; inspect machine device certificate existence, validity and private-key presence. Do not export keys.
3. Check `Microsoft-Windows-User Device Registration/Admin` Event 360 and CloudAP Event 215 and network errors 233/252. Interpret event time and execution identity; `0x80072ee7` may indicate transient DNS failure, and historical events must not be treated as current failure.
4. Verify Microsoft login/registration DNS and TCP 443 using governed read-only diagnostics. Distinguish current connectivity from historical events.
5. Use tenant-scoped governed Graph read by exact `deviceId` to check device presence/enabled state; do not infer directory status from local certificate alone.
6. Read effective Windows Hello policy from approved policy sources. A local registry value and a GP refresh are not proof of the interactive user's enrollment eligibility.

Decision: when `AadRecoveryEnabled=YES` AND `KeySignTest=FAILED`, classify local Entra device-key failure; do not start with PIN deletion.

## 8. Decision Gates
Confirm unique tenant/device match; authorized read and ticket association; preservation of remote access; no conflicting enrollment/recovery; latest status vs stale events; interactive Entra reauthentication dependency and user availability; separate approvals for policy writes and disruptive actions.

## 9. Remediation
- **Read-only/autonomous:** Diagnose and report exact evidence, check Entra directory status and identity endpoints, recheck after ordinary user sign-in.
- **Non-disruptive recheck:** If user naturally signs in and Windows' automatic device recovery runs, re-read status. Do not assert Jason caused recovery unless evidence establishes causality.
- **Human-attended recovery:** If trust remains failed, coordinate authorized interactive `dsregcmd /forcerecovery` in the correct session with verified user credentials, subject to change/availability approval. Never run unattended under SYSTEM expecting completed reauthentication.
- **Policy changes:** Through supported governed management policy and separate authorization only; avoid ad hoc local edits as a general fix.
- **PIN reset, credential-store deletion, Entra leave/rejoin, TPM clear, forced sign-out/reboot:** Never automatic; require explicit targeted approval and recovery plan; avoid broad store deletion.

## 10. Retry Policy
One interactive recovery attempt per unchanged failure fingerprint; no blind retry loops. On failure, escalation with exact device/log evidence. SYSTEM-only access is a blocker for interactive completion, not grounds for unsupported bypass.

## 11. Periodic Rechecks
On next ordinary login or scheduled bounded check; verify device signing and auth. Release active work slot while waiting. No duplicate notes for unchanged evidence.

## 12. Aging / Stale Condition
After two days with no user-assisted recovery or contradictory results, route Human Review. Historical failures remain documented but do not override newer verified success.

## 13. Dependency Handling
Microsoft Entra tenant access, governed Graph read, DRMM read component and an available user for interactive recovery. Record and link existing dependencies; no duplicate ticket.

## 14. Documentation Requirements
Technician note fields: STATUS, NEXT STEP, WHEN, KEY EVIDENCE, WHAT JASON DID, CHANGES MADE, JASON STATE. Preserve timestamps, actual commands and trustworthy outputs, policy change authority, current vs historical status, and outcome. Exclude secrets/cert private keys/PRTs.

## 15. Failure Handling
Classify Graph auth failure, no matching directory record, disabled device, local signing failure, missing TPM, policy not enabled, DNS/transport error, missing user, and uncertain repair status separately. No false PASS based on a printed message after script exceptions; use one terminating execution block and post-write readback.

## 16. Escalation Criteria
Missing/disabled directory device, unexpected cryptographic failure, repeated recovery failure, need for interactive recovery when unavailable, potential loss of remote access, unauthorized disruptive operation, or inability to validate new healthy state.

## 17. Verification
After recovery: `AzureAdJoined:YES`, `DeviceAuthStatus:SUCCESS`, `AadRecoveryEnabled:NO`, `KeySignTest:PASSED`. Independently verify PIN enrollment with the actual user; a policy registry value of 1 does not establish PIN success.

## 18. Completion Criteria
Correct ticket/CI; trustworthy diagnosis; authorized actions only; post-recovery device trust PASS; PIN user acceptance if requested; complete notes and authoritative terminal ticket disposition/readback. If PIN confirmation pending, remain `waiting_pin_confirmation` rather than close.

## 19. Final Resolution Note
Include initial failing status and error codes, validated directory state, what action actually occurred (or unknown), recovered device-key verification, PIN enrollment confirmation (or pending), timestamps, and resulting ticket state.

## 20. Required Capabilities
Autotask read/CI association/queue start/note/disposition; DRMM endpoint and component governed read; Graph Entra device read; persisted state, scheduled recheck, readback. Interactive recovery is technician/user-assisted, not a standing autonomous capability.

## 21. Acceptance Test
Use a safe isolated endpoint or approved fixture with: missing vs enabled directory object, key-sign failure, stale Event 360, broken DNS then restored DNS, SYSTEM vs user token-context distinction, ordinary login followed by successful recovery, user unavailable, disallowed destructive action, tenant mismatch, restart/resume, duplicate note suppression, and no resolution until separate user PIN acceptance.

## 22. Section Goal Closure
Record fixture results and live controlled proof, capability gaps, limitations, owner signoff, and linked memory evidence. This remains candidate/not deployed until tested and governed promotion.

## 23. Autonomous Execution Eligibility and Owner Review
Approve read-only diagnostic/recheck branches only, subject to exact privilege bounds. No standing permission for credential reset, registry policy edits, `dsregcmd /forcerecovery`, forced logout, reboot, join/leave, or TPM clear. Material scope/version changes require new owner review.

## Historical case evidence — AOT-50900 (2026-10-16)
- Initial: `AzureAdJoined YES`, `DeviceAuthStatus FAILED 0xd0090016`, `AadRecoveryEnabled YES`, `KeySignTest FAILED (device key)`; TPM healthy; Entra directory object present and enabled.
- Earlier events: CloudAP Event 215 `0xc0090016`, intermittent device registration DNS `0x80072ee7`.
- A computer-level Windows Hello policy setting was enabled and refreshed; this did NOT prove recovery or user PIN eligibility.
- After subsequent ordinary sign-in, readback: `DeviceAuthStatus SUCCESS`, `AadRecoveryEnabled NO`, `KeySignTest PASSED`; Windows appears to have recovered trust, but causal mechanism not independently proven.
- PIN creation was **not yet user-verified** at case conclusion.
- Lesson: never clear TPM or PIN credentials merely for Entra signing failure; check device trust first, and distinguish device-trust resolution from user PIN acceptance.

## Backlog alignment
Primary parent: TODO-OPS-001 Operational Resolution Memory (#1489). Idea intake reference: #877. Do not create duplicate TODO or automatically authorize live remediation.
