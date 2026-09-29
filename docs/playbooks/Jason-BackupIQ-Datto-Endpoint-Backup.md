# Jason BackupIQ / Datto Endpoint Backup Playbook

## Playbook Manifest

```yaml
playbook:
  id: backupiq_endpoint_backup
  name: BackupIQ / Datto Endpoint Backup
  version: 2.0.0-design
  owner: AOT
  target_type: endpoint
  trigger:
    provider: Autotask / BackupIQ
    match: open ticket title begins with "BackupIQ:"
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 2
  recheck:
    enabled: true
    cadence: 1h
    stale_after: 10d
  verification:
    authoritative_source: Backup.net / UniView
    success_condition: successful backup within expected threshold after recovery/remediation
  completion:
    terminal_disposition: Complete
  autonomy:
    allowed_branches:
      - identify
      - classify
      - wait
      - close_recovered
    approval_bound_branches:
      - reinstall_agent
      - lifecycle_mutation
      - backup_policy_change
    disruptive_branches: []
```

This playbook inherits the common lifecycle, work-start, identity, waiting/recheck, idempotence, documentation, retry, human-review, completion/readback, and observability behavior from `Jason-Playbook-Runtime-Automation-Contract.md`.

## 1. Section Goal

Jason must determine whether a BackupIQ ticket represents an inactive endpoint, an Endpoint Backup agent connectivity problem, a disabled/misconfigured backup, a stale asset, or a genuine backup failure; perform only governed remediation supported by evidence; and verify a new successful backup before completion.

## 2. Trigger

Apply when an Autotask ticket is created from BackupIQ / UniView indicating an endpoint backup has not completed within the configured threshold, including titles such as "BackupIQ: Backup for asset is not available for <client>".

Confirm the ticket, client, endpoint/asset name, alert timestamp, threshold, and associated DRMM site/device before proceeding.

Queue ownership invariant:

`Open + BackupIQ => Jason queue`

This invariant is independent of endpoint online/offline state, active-work capacity, waiting/recheck state, and whether remediation is currently possible. The global active-work limit controls concurrent execution only.

## 3. Scope and Boundaries

In scope: Autotask, Datto RMM, BackupIQ/UniView Public API, Datto Endpoint Backup asset state, endpoint software/services, site variables required by the approved installer component, governed remediation, periodic rechecks, ticket documentation, and verification.

Out of scope without separate approval: destructive backup deletion, restoring data, changing retention/policy, removing encryption, deleting provider assets, or borrowing registration/encryption values across clients.

Preserve Central Orchestrator authority, exact requester grants, provider/client isolation, audit, approval rules, and direct_provider_access=false.

## 4. Initial Identification

Identify:
- Autotask ticket number and company.
- DRMM site and exact device UID.
- DRMM hostname.
- BackupIQ / UniView asset name and provider asset ID.
- Any duplicate, renamed, reimaged, retired, or stale objects.

Use the UniView Public API as authoritative for Endpoint Backup provider state and DRMM as authoritative for endpoint management/connectivity state.

Boundary rules:
- Use the exact Autotask company identifier associated with the client boundary; do not assume valid company IDs must be greater than zero. The AOT self-company record legitimately uses company ID `0`.
- Require a validated `backup_net` company-to-customer boundary before provider reads. Never accept a caller-supplied Backup.net customer UUID as authority.
- A successful provider query returning an empty Endpoint Backup asset collection is authoritative evidence that no matching provider asset was exposed for that exact validated customer/query at that time. Treat it as a protection/onboarding/asset-placement condition to investigate, not as a connector authorization failure.
- Customer-boundary validation normally requires exact asset proof when provider assets exist. A zero-asset customer may be validated only when the exact unique provider customer is established and a bounded provider inventory query proves the customer currently has no Endpoint Backup assets.

If the provider asset cannot be uniquely matched to the DRMM endpoint, set state=identification_blocked, document the ambiguity, and escalate rather than guessing.

Apply the global CI-association gate from the shared runtime contract before substantive diagnostics. If queue/work-start transition or authoritative readback fails, fail closed and do not continue ticket-specific diagnostics.

## 5. Expected State

Healthy state requires:
- DRMM endpoint is active/managed when expected.
- Endpoint Backup provider asset exists and matches the endpoint.
- Backup is enabled.
- Provider asset is online/recently online as expected.
- A successful backup exists within the allowed BackupIQ threshold.
- Endpoint Backup agent software/service is healthy when the device is online.
- No unresolved duplicate/stale asset condition exists.

## 6. State Model

identified -> provider_check -> endpoint_check -> classify
classify -> waiting_device | waiting_backup_cycle | diagnosing | stale_asset_review | configuration_blocked
diagnosing -> remediating -> verifying -> complete
Any state may transition to escalated.

Persist ticket, DRMM device UID, UniView asset ID, classification, last provider query time, last successful backup, last online timestamp, current retry count, next recheck time, last meaningful evidence fingerprint, last ticket-note fingerprint, active job/correlation ID, and terminal-disposition state.

Waiting states retain Jason queue ownership and normally release the active-work slot.

## 7. Diagnostic Workflow

### A. UniView / Backup.net Public API provider check

Authenticate using OAuth 2.0 client credentials through Jason's secret broker/OpenBao. Never log or persist Client Secret or access tokens.

Required read operations:
- GET /api/epb/v1/assets filtered to the exact endpoint/asset.
- GET /v1/backupiq/alerts where useful to confirm provider alert context.
- GET /v1/backups when needed to inspect recent backup outcomes.

Record sanitized provider evidence:
- provider asset ID/name
- customer
- status / connectivity state
- backup enabled state
- last successful backup timestamp
- last online timestamp
- relevant policy/asset state
- recent backup result where available

### B. DRMM endpoint check

Read the exact DRMM device:
- online/offline state
- last seen/check-in
- recent availability evidence
- reboot required where relevant
- installed Endpoint Backup software
- service/process status when online

Do not equate DRMM last_logged_in_user with a live interactive session.

### C. Evidence classification

1. DRMM offline + Endpoint Backup offline:
   classify=inactive_or_offline_device. Do not reinstall. Enter waiting_device.

2. DRMM online + Endpoint Backup offline/stale:
   classify=backup_agent_connectivity_failure. Enter diagnosing after the online-duration gate.

3. DRMM online + Endpoint Backup online + backup enabled + stale last successful backup:
   classify=backup_failure. Enter diagnosing after the online-duration gate.

4. Backup disabled:
   classify=backup_configuration_issue. Do not reinstall solely for this condition. Document and escalate/change configuration only under appropriate authority.

5. Provider asset missing:
   - If the endpoint is active/expected to be protected: classify=unprotected_or_asset_lifecycle_issue. Treat the authoritative empty provider result as valid negative evidence, not as a connector failure. Investigate onboarding, asset placement, rename/reimage/replacement, retirement, or duplicate state before remediation.
   - If endpoint lifecycle evidence indicates retirement/replacement/staleness: classify=asset_identity_or_lifecycle_issue.
   - Do not reinstall solely because the provider asset is absent.

6. Recent successful backup within threshold:
   classify=stale_or_recovered_alert. Verify provider health and complete the ticket automatically when all common completion/readback gates pass and no contradictory evidence exists.

7. Backup disabled:
   classify=backup_configuration_issue. Configuration/policy changes remain approval-bound unless separately promoted for autonomy.

## 8. Decision Gates

Before remediation all must be true:
- exact DRMM endpoint identified
- exact UniView Endpoint Backup asset identified
- device has been continuously online long enough for one full AOT backup cycle (approximately two hours)
- provider evidence still shows unhealthy/stale backup state
- Endpoint Backup agent problem is supported by evidence
- required DRMM site variable exists and is usable
- remediation component is approved for the requested scope
- no conflicting maintenance/retirement/reimage evidence exists

If any gate fails, do not reinstall.

## 9. Remediation

Approved remediation component:
Datto Endpoint Backup Agent v2 [WIN]

Component metadata requires:
- usrDEBToken or site variable usrDEBTokenSITE (mandatory registration token)
- optional usrDEBEncryption or site variable usrDEBEncryptionSITE

Never reveal or copy the token/encryption value into tickets, logs, chat responses, or documentation.

A reinstall is modifying and must remain governed. Clean install creates a new asset record and may create duplicate billing; therefore do not select clean install unless the playbook branch explicitly requires it and asset lifecycle has been reconciled.

Record job ID, terminal status, actual sanitized StdOut/StdErr, and interpretation.

## 10. Retry Policy

Maximum two full remediation attempts.

A full attempt includes provider pre-check, endpoint pre-check, dependency validation, component execution, terminal output, post-install service check, provider recheck, and backup verification.

After two failed attempts, escalate.

## 11. Periodic Rechecks

While waiting_device, recheck at least hourly unless ticket policy specifies a different cadence. The ticket remains in the Jason queue but releases its active-work slot.

Unchanged rechecks update persisted state only and do not create duplicate Autotask notes.

Technician-triggered, autonomous, resumed, and scheduled executions use the same semantic BackupIQ note classes. A second execution reaching the same classification with materially equivalent evidence must not write a second diagnostic note merely because its actor/origin or title wording differs.

When the device becomes online:
- document observation time
- begin a continuous two-hour online qualification window
- transition to waiting_backup_cycle

If it goes offline during the window, reset the two-hour qualification.

During verifying, poll provider state on a reasonable cadence until a new successful backup is observed or the verification window expires.

## 12. Aging / Stale Condition

If the device remains offline more than 10 days, stop normal retry behavior and investigate:
- retired/replaced endpoint
- stale DRMM device
- renamed/reimaged endpoint
- duplicate provider asset
- broader management/connectivity problem

Do not retry indefinitely.

## 13. Dependency Handling

Required API dependency:
- UniView Public API Client ID
- UniView Public API Client Secret
- OAuth client-credentials token acquisition
- Jason secret-broker/OpenBao storage
- provider read capability for Endpoint Backup assets/backups/BackupIQ alerts

Required install dependency:
- usrDEBTokenSITE or approved per-run token source
- optional usrDEBEncryptionSITE if the site's policy uses a user-managed encryption key

If a required dependency is missing:
1. search for an existing open dependency ticket/issue
2. suppress duplicates
3. create one if none exists and authority allows
4. cross-reference it
5. set state=configuration_blocked

Never include secret values in the dependency ticket.

## 14. Documentation Requirements

Document provider query, DRMM state, classification, online-duration gate, diagnostic results, dependency presence, remediation jobs, rechecks, and final verification.

Recommended note titles:
- Jason - BackupIQ - Asset Validation
- Jason - BackupIQ - Provider State
- Jason - BackupIQ - Recheck
- Jason - BackupIQ - Diagnostic
- Jason - BackupIQ - Remediation
- Jason - BackupIQ - Verification
- Jason - BackupIQ - Resolution

## 15. Failure Handling

Treat API authentication failure, provider timeout, unmatched asset, contradictory DRMM/provider state, missing component output, missing site variable, and denied action authority as explicit failures. Document them and fail closed.

## 16. Escalation Criteria

Use Human Review when a technician decision is specifically required. Escalate only for operational failure/out-of-scope conditions.

Escalate or hand off when:
- asset identity cannot be established
- provider API remains unavailable beyond bounded retries
- backup disabled requires policy decision
- required secret/site variable is missing
- two remediation attempts fail
- device is stale/retired/duplicated
- clean-install/new-asset decision is required
- verification cannot establish a new successful backup

## 17. Verification

A component success is not incident resolution.

Preferred authoritative resolution evidence:
- UniView/Backup.net reports the correct asset healthy/online as applicable
- backup remains enabled
- a new successful backup timestamp occurs after remediation/recovery
- DRMM endpoint remains healthy/online long enough to support that backup
- related BackupIQ condition/alert clears or is no longer current

## 18. Completion Criteria

Complete only when the endpoint/provider asset mapping is correct, classification is established, required work is documented, and provider evidence shows a successful backup within the expected window or the alert is proven stale/recovered.

A successful component/job result is not resolution. Terminal Autotask disposition must be written and independently read back before state=complete.

## 19. Final Resolution Note

Include original BackupIQ condition, classification/root cause, DRMM availability, provider asset state, last successful backup before/after, remediation attempts, final provider verification timestamp, and disposition. Never include credentials/tokens.

## 20. Required Capabilities

Existing:
- Autotask ticket read/write/note/create
- DRMM device/software/component/job/output reads
- DRMM site-variable presence/read controls
- governed component execution
- persisted playbook state and scheduler/rechecks

Implementation required:
- backup.endpoint.asset.search/read
- backup.endpoint.backup.search
- backup.backupiq.alert.search
- OAuth client-credentials broker using OpenBao-held Client ID/Secret
- provider/client isolation and redaction
- health/readiness evidence for the Backup.net integration

## 21. Acceptance Test

Initial controlled production acceptance target:
- Autotask T20260922.0063
- Client: Deborah Gittens Virtuol Designs LLC
- Asset: DGV-50859

Acceptance must prove:
1. exact Autotask/DRMM/provider asset association
2. API authentication without exposing secrets
3. provider asset status/last online/last successful backup retrieval
4. DRMM/provider evidence classification
5. correct two-hour gate behavior
6. no reinstall when evidence indicates offline/inactive/stale device
7. governed reinstall only when evidence supports agent failure and dependencies exist
8. provider-side successful-backup verification before completion
9. ticket documentation and bounded retry behavior

Do not run the live API acceptance test until credentials are installed through the approved secret path.

### 2026-09-29 controlled reference-runtime acceptance

Production case: `T20260928.0082 / TUS-50822 / Terramar`.

Proven:
- exact open BackupIQ trigger and Jason queue ownership;
- exact same-company Autotask CI 544;
- CI referenceNumber exactly matched DRMM UID `56cf6985-cb5f-fc1c-813c-5782388d403f`;
- exact Backup.net asset `GWN65TK04`;
- governed work-start mutation associated the CI, set In Progress, and set Remote Support with one provider PATCH and verified readback;
- DRMM and Backup.net independently reported the endpoint offline;
- backup remained enabled;
- no reinstall/component/configuration change was attempted;
- the autonomous worker independently classified `inactive_or_offline_device`.

Acceptance findings:
- production v1 persisted this normal offline condition as terminal `escalated`, which released the slot but prevented automatic online resume;
- technician-triggered and autonomous execution produced materially duplicate diagnostic notes because note deduplication was origin/title/body dependent.

This v2 branch therefore implements resumable `waiting_device_access:backupiq_investigate` semantics and requires semantic cross-origin note deduplication. Full production acceptance remains incomplete until the new waiting -> online resume behavior is deployed and observed. Recovered-alert completion and agent remediation remain separately gated.

Integration review: PR #604 supersedes #603. Its shared-runtime overlap is VulScan-specific and does not conflict with the BackupIQ waiting/resume changes in this playbook branch.

## 22. Section Goal Closure

Close the Section Goal after:
- Backup.net OAuth integration is implemented and registered
- provider read capabilities are live and client-isolated
- credentials are stored only in the approved secret system
- DGV-50859 or another controlled target passes acceptance
- Grafana/Project Jason status reflects the capability and health
- remaining limitations are documented

## 23. Autonomous Execution Eligibility

Current production approval remains limited to the exact previously promoted diagnostic/classification branch until this v2 design passes controlled acceptance and receives a new owner promotion.

Proposed v2 branch model:
- autonomous-safe candidate: identify
- autonomous-safe candidate: classify
- autonomous-safe candidate: waiting/recheck
- autonomous-safe candidate: stale/recovered completion after authoritative verification and terminal readback
- approval-bound: normal agent reinstall until controlled production acceptance proves the bounded branch
- approval-bound: clean install/new asset creation
- approval-bound: backup policy/retention/configuration changes
- approval-bound: lifecycle mutation/delete/retire actions


Approval owner: person-al
Approval date: 2026-09-26
Approved scope: exact `backupiq_endpoint_backup@1.0.0` diagnostic/classification branch using governed DRMM and Backup.net/UniView reads plus internal ticket note/work-start updates.

The provider/API integration and client isolation are live. The autonomous branch may identify the exact DRMM/provider asset, classify offline/inactive, provider-connectivity, configuration, stale/recovered, and identity/lifecycle conditions, and document the result. It may not reinstall or clean-install the Endpoint Backup agent, retrieve or expose registration/encryption values, change backup policy/retention, delete provider assets/backups, restore data, or automatically close the ticket.

The existing v1 diagnostic approval is not broadened by this document. Scheduled rechecks, recovered-alert completion, and normal agent repair must each pass the standard acceptance matrix before activation. Any material version/capability/fingerprint change requires owner re-review before the changed branch executes autonomously.

Acceptance must additionally prove:
- all open matching tickets normalize to Jason regardless of active-slot capacity;
- an offline endpoint can be classified without being rejected before ownership;
- waiting releases the active slot while retaining ownership;
- an unchanged recheck does not duplicate notes;
- authoritative empty provider results are treated as negative evidence, not connector failure;
- stale/recovered alerts can reach Complete only after terminal ticket-state readback;
- unauthorized repair/configuration/lifecycle branches fail closed.
