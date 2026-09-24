# Jason BackupIQ / Datto Endpoint Backup Playbook

## 1. Section Goal

Jason must determine whether a BackupIQ ticket represents an inactive endpoint, an Endpoint Backup agent connectivity problem, a disabled/misconfigured backup, a stale asset, or a genuine backup failure; perform only governed remediation supported by evidence; and verify a new successful backup before completion.

## 2. Trigger

Apply when an Autotask ticket is created from BackupIQ / UniView indicating an endpoint backup has not completed within the configured threshold, including titles such as "BackupIQ: Backup for asset is not available for <client>".

Confirm the ticket, client, endpoint/asset name, alert timestamp, threshold, and associated DRMM site/device before proceeding.

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

Persist ticket, DRMM device UID, UniView asset ID, classification, last provider query time, last successful backup, last online timestamp, current retry count, and next recheck time.

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
   classify=asset_identity_or_lifecycle_issue. Investigate renamed/reimaged/retired/replaced/duplicate endpoint before remediation.

6. Recent successful backup within threshold:
   classify=stale_or_recovered_alert. Verify provider health and close ticket/alert when appropriate.

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

While waiting_device, recheck at least hourly unless ticket policy specifies a different cadence.

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

Escalate when:
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

## 22. Section Goal Closure

Close the Section Goal after:
- Backup.net OAuth integration is implemented and registered
- provider read capabilities are live and client-isolated
- credentials are stored only in the approved secret system
- DGV-50859 or another controlled target passes acceptance
- Grafana/Project Jason status reflects the capability and health
- remaining limitations are documented

## 23. Autonomous Execution Eligibility

autonomous_allowed: false

Approval owner: pending
Approval date: pending
Approved version/fingerprint: pending

This playbook is not eligible for autonomous remediation until the API integration, acceptance test, and explicit playbook-level autonomy review are complete.

Read-only provider/DRMM diagnostics may later be considered for autonomous execution after approval. Any action that can disrupt a user or materially alter backup configuration remains governed and approval-bound.
