# Jason BackupIQ / Datto Endpoint Backup Playbook

## Playbook Manifest

```yaml
playbook:
  id: backupiq_endpoint_backup
  name: BackupIQ / Datto Endpoint Backup
  version: 1.2.0
  owner: AOT
  target_type: endpoint
  trigger:
    provider: Autotask / BackupIQ
    match: open ticket title begins with "BackupIQ:"
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 1
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
      - wait_true_offline
      - recheck
      - resume_on_online
      - close_recovered
      - reinstall_agent
      - verify_reinstall
      - handoff_human_review
    approval_bound_branches:
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

Queue ownership rule:

`Open + actionable BackupIQ => Jason queue`

Exception: when Jason determines that technician review is required, it must write an actionable internal note, move the ticket to **Help Desk I (29682833)**, set **Human Review (37)**, verify both fields by provider readback, and leave the ticket outside Jason until a human explicitly changes the disposition. The queue normalizer must not pull an explicit BackupIQ Human Review ticket back into Jason.

The global active-work limit controls concurrent execution only.

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

Availability is a two-source decision. DRMM and Backup.net must be evaluated independently before Jason decides whether the endpoint is truly offline.

1. **DRMM offline + Backup.net offline**
   - classify=`true_offline_both_sources`
   - this is the only normal BackupIQ **true offline** condition
   - do not reinstall
   - keep the ticket in Jason, set **Waiting Device Access (38)**, release the active-work slot, and resume when the exact endpoint returns

2. **DRMM offline + Backup.net online**
   - classify=`drmm_only_offline_conflict`
   - this is contradictory availability evidence, not true offline
   - do not reinstall
   - document DRMM state, provider state, last check-in/online timestamps and backup evidence
   - move to **Help Desk I (29682833) + Human Review (37)** with verified readback

3. **DRMM online + Backup.net offline**
   - classify=`backup_agent_connectivity_failure`
   - endpoint connectivity is proven while the backup provider has lost the agent
   - the exact approved Endpoint Backup installer/reinstaller may run autonomously
   - one reinstall maximum per incident cycle

4. **DRMM online + Backup.net online + recent/successful backup**
   - if no current BackupIQ condition remains: classify=`stale_or_recovered_alert`, document and complete automatically after verified Autotask readback
   - if contradictory/current BackupIQ evidence remains and no lower-impact repair fits: classify=`persistent_backupiq_condition_after_success`; the approved reinstall may run autonomously

5. **DRMM online + Backup.net online + stale/failed backup**
   - classify=`backup_failure_or_stale_success`
   - continue diagnosis for any exact lower-impact repair that clearly fits
   - if no other repair fits, or a bounded applicable repair does not restore health, the approved reinstall may run autonomously
   - one reinstall maximum per incident cycle

6. **Backup disabled**
   - classify=`backup_configuration_issue`
   - do not reinstall solely for this condition
   - document and move to **Help Desk I + Human Review**

7. **Provider asset missing/ambiguous/duplicate**
   - classify=`asset_identity_or_lifecycle_issue`
   - do not guess, clean-install, or create a replacement asset autonomously
   - document and move to **Help Desk I + Human Review**

A successful installer job is action evidence only. It never proves incident resolution.

## 8. Decision Gates

Before autonomous reinstall all must be true:
- exact Autotask client/ticket boundary is established
- exact DRMM endpoint is established
- exact same-client Backup.net Endpoint Backup asset is uniquely established
- DRMM reports the endpoint online
- backup is expected to be enabled
- the approved reinstall branch is supported by current evidence
- no duplicate/reimage/retirement/lifecycle conflict exists
- the one-reinstall-per-incident limit has not already been consumed
- the exact installer component is standing-safe for this playbook
- installer variables are empty/server-governed only; Jason never reads or exposes registration/encryption secrets

The two-hour online qualification from older design revisions is not required for the specific **DRMM online + Backup.net offline** condition. DRMM already proves endpoint access and provider-offline evidence supports the agent-connectivity repair.

For Online/Online stale/failed or persistent-alert conditions, prefer an exact lower-impact repair when one exists. If none fits, reinstall is an approved bounded fallback.

## 9. Remediation

Approved standing-safe remediation component:

**Datto Endpoint Backup Agent v2 [WIN]**  
Component UID: `f39412b2-bfdc-4ac6-b4be-f2fa8bc5f967`

Durable component approval date: 2026-09-29. The approval is limited to exact managed endpoints under this playbook's identity, evidence, retry, and verification gates.

The component may use server-governed/site-scoped registration inputs such as `usrDEBTokenSITE` and optional `usrDEBEncryptionSITE`. Jason must not retrieve, log, copy, persist, or expose those secret values. Component invocation uses no caller-supplied secret variables.

Autonomous reinstall is approved when:
- DRMM is online and Backup.net is offline; or
- DRMM and Backup.net are online but a current BackupIQ condition/backup failure remains and no lower-impact repair clearly fits; or
- an applicable bounded lower-impact repair was attempted and the backup condition remains.

Clean install/new-provider-asset creation is **not** implied by reinstall authority. If the installer or provider evidence indicates a clean-install/new-asset/lifecycle decision, stop and route to Help Desk I / Human Review.

Record component UID/name, durable job ID, terminal provider status, sanitized output when available, and interpretation. Installer stdout is useful evidence but provider-side recovery is authoritative.

## 10. Retry Policy

Maximum **one autonomous Endpoint Backup reinstall per incident/playbook cycle**.

A reinstall attempt includes provider pre-check, endpoint pre-check, exact component execution, terminal job evidence, provider recheck, and successful-backup verification.

Never enter an uninstall/reinstall loop. If the reinstall fails, cannot be verified, or the provider remains unhealthy after the bounded verification window, document the evidence and move to **Help Desk I + Human Review**.

## 11. Periodic Rechecks

While waiting_device, recheck at least hourly unless ticket policy specifies a different cadence. The ticket remains in the Jason queue but releases its active-work slot.

Unchanged rechecks update persisted state only and do not create duplicate Autotask notes.

Technician-triggered, autonomous, resumed, and scheduled executions use the same semantic BackupIQ note classes. A second execution reaching the same classification with materially equivalent evidence must not write a second diagnostic note merely because its actor/origin or title wording differs.

When the device becomes online:
- document observation time
- begin a continuous two-hour online qualification window
- transition to waiting_backup_cycle

If it goes offline during the window, reset the two-hour qualification.

During post-reinstall verification, poll provider state on a reasonable cadence. Completion requires the exact Backup.net asset to be online and a **new successful backup timestamp after the reinstall baseline**. Use a bounded verification window (currently three hours). If the endpoint becomes truly offline (both DRMM and Backup.net offline), transition to Waiting Device Access and resume verification later. DRMM-only offline during verification is a Human Review handoff.

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

Escalate or hand off to **Help Desk I (29682833) / Human Review (37)** when:
- asset identity cannot be established
- DRMM alone reports offline while Backup.net remains online
- provider API remains unavailable beyond bounded retries
- backup disabled requires policy decision
- required installer dependency cannot be resolved server-side
- the single autonomous reinstall fails
- device is stale/retired/duplicated
- clean-install/new-asset decision is required
- post-reinstall verification cannot establish provider recovery and a new successful backup

Human-review notes must include DRMM state/last check-in, Backup.net state/last online, last successful backup, exact endpoint/provider asset identity, actions attempted, job/correlation IDs where available, and the specific reason human review is required. Never include secret values.

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
- governed component execution
- standing-safe Datto Endpoint Backup Agent v2 [WIN]
- Backup.net Endpoint Backup asset and BackupIQ alert reads
- persisted playbook state and scheduler/rechecks

Required governed read capabilities:
- `backup.endpoint.asset.search/read`
- `backup.endpoint.backup.search` when detailed backup history is required
- `backup.backupiq.alert.search`
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

This v2 branch therefore implements resumable `waiting_device_access:backupiq_investigate` semantics and requires semantic cross-origin note deduplication. Production deployment proved legacy offline-state migration and unchanged-note behavior. The waiting -> online resume transition is Owner-approved to execute when the exact endpoint naturally returns online, but its live transition proof remains an acceptance item. Recovered-alert completion and agent remediation remain separately gated.

Integration review: PR #604 supersedes #603. Its shared-runtime overlap is VulScan-specific and does not conflict with the BackupIQ waiting/resume changes in this playbook branch.

The PR integration gate is coordinated with #596, #603, and #604.

## 22. Section Goal Closure

Close the Section Goal after:
- Backup.net OAuth integration is implemented and registered
- provider read capabilities are live and client-isolated
- credentials are stored only in the approved secret system
- DGV-50859 or another controlled target passes acceptance
- Grafana/Project Jason status reflects the capability and health
- remaining limitations are documented

## 23. Autonomous Execution Eligibility

### Owner-approved production scope — BackupIQ 1.2.0

Approval owner: person-al  
Approval date: 2026-09-29  
Policy: `playbook-autonomy:backupiq_endpoint_backup`

Required action capabilities:
- `automation.component.execute`
- `service.ticket.note.create`
- `service.ticket.update`

Approved autonomous behavior:
- exact ticket/client/CI/DRMM/Backup.net identity;
- dual-source availability classification;
- **both DRMM and Backup.net offline** => Jason / Waiting Device Access;
- **DRMM offline only** => evidence note + Help Desk I / Human Review;
- **Backup.net offline only while DRMM online** => one standing-safe Endpoint Backup reinstall;
- **Online/Online recent success and no current condition** => verified recovered completion;
- **Online/Online with persistent condition, stale or failed backup** => diagnose, then one reinstall if no lower-impact repair fits or repair fails;
- post-reinstall provider verification requiring a new successful backup after the remediation baseline;
- Help Desk I / Human Review after failed install, unresolved verification, policy/lifecycle ambiguity, or other out-of-scope conditions.

Standing-safe component:
- `Datto Endpoint Backup Agent v2 [WIN]`
- UID `f39412b2-bfdc-4ac6-b4be-f2fa8bc5f967`
- Durable component approval recorded 2026-09-29 by person-al.

Hard boundaries:
- one autonomous reinstall per incident cycle;
- no clean-install/new-provider-asset lifecycle mutation;
- no asset deletion/retirement;
- no policy/retention change;
- no restore operation;
- no registration/encryption secret disclosure;
- no reboot or other disruptive endpoint action without separate approval.

The prior `backupiq_endpoint_backup@1.1.0` approval remains historical rollback evidence only. Version 1.2.0 requires a new durable playbook-autonomy promotion for the exact three-capability set before production execution.

