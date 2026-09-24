# Jason Windows Update / VulScan Missing Patch Playbook

## 1. Section Goal

Jason must distinguish a genuinely failed Windows update from an approved patch that is merely waiting for its normal patch window, perform bounded Windows Update diagnostics/remediation only when justified, protect active users from disruption, and verify the exact KB/build state before completing the ticket.

For any missing or unapproved KB, Jason must also produce a plain-English KB intelligence summary and an evidence-based **Patch Reliability Score** before recommending approval, pilot deployment, hold, or rejection. Security urgency and operational reliability are separate dimensions: a critical security patch can still be operationally unsafe to deploy broadly.

Success requires a deterministic classification, documented KB intelligence, correct Autotask ownership/device association, bounded repair attempts, safe reboot handling, an evidence-based approval recommendation, and authoritative verification that the reported missing patch condition is resolved or appropriately escalated.

## 2. Trigger

Apply when an Autotask/VulScan/DRMM ticket or alert identifies a missing Windows security/quality update or a failed Windows patch installation on a managed Windows endpoint.

Examples:
- "Vulnerability Detected by VulScan"
- "Missing Critical Security Patch"
- DRMM patch status InstallError
- exact KB reported missing

Confirm the exact KB/update identity before proceeding.

## 3. Scope and Boundaries

In scope:
- Autotask ticket ownership, queue, status, notes, and configuration-item association
- DRMM endpoint identity, online state, patch inventory/status, reboot-required state
- Windows Update health diagnostics
- Windows Update event-log evidence
- governed execution of approved AOT diagnostic/repair components
- patch-window waiting/recheck logic
- safe scheduled reboot logic
- exact post-remediation verification
- authoritative Microsoft KB / Release Health / MSRC research
- AOT fleet deployment evidence when available
- endpoint-role applicability analysis
- deterministic Patch Reliability Score and approval recommendation

Out of scope unless separately authorized:
- approving unapproved patches
- changing organization patch policy
- bypassing maintenance windows
- clearing WSUS policy without a specific evidence-based reason and approval
- immediate user-disruptive reboot when a user session exists
- unlimited repair/install retries

Preserve Central Orchestrator authority, exact requester grants, provider/client isolation, audit, approval rules, and direct_provider_access=false.

## 4. Initial Identification

Before diagnostics:
1. Read the Autotask ticket.
2. Move a Jason-owned ticket to queue **Jason** (queue ID 29683489) and verify by readback.
3. Set the appropriate working status.
4. Identify the exact DRMM endpoint.
5. Associate the correct Autotask configuration item when a reliable match exists.
6. Identify the exact KB/update and current DRMM patch object.
7. Check for relevant prior ticket notes/attempts to avoid repeating completed work.

If identity is ambiguous, set state=identification_blocked and stop rather than guessing.

## 5. Expected State

Healthy state requires:
- exact KB/update is installed or superseded by an authoritative newer update/build
- DRMM no longer reports InstallError for the relevant patch condition
- no approved patch remains unexpectedly pending after the applicable maintenance cycle
- Windows Update services/stack are functional
- no unresolved reboot requirement blocks completion
- the VulScan/monitor condition is cleared or otherwise proven stale/resolved

## 6. State Model

identified -> patch_intelligence -> patch_state_check

patch_intelligence ->
- intelligence_ready
- intelligence_blocked

patch_state_check ->
- complete_candidate
- waiting_patch_window
- diagnosing_install_failure
- approval_recommended
- approval_blocked
- hold_watch
- do_not_install

approval_recommended -> approval_blocked | waiting_patch_window
hold_watch -> patch_intelligence
do_not_install -> supersedence_check | escalated

waiting_patch_window -> post_window_verification

post_window_verification ->
- complete_candidate
- diagnosing_install_failure
- reboot_pending

diagnosing_install_failure -> repairing_update_stack

repairing_update_stack ->
- retrying_patch
- reboot_pending
- escalated

retrying_patch ->
- verifying
- reboot_pending
- diagnosing_install_failure
- escalated

reboot_pending -> post_reboot_verification

post_reboot_verification -> verifying

verifying -> complete | escalated

Persist ticket ID, device UID, configuration item ID, KB/patch ID, current state, patch-window timestamp, diagnostic job IDs/results, repair attempts, reboot decision, next recheck, security-urgency classification, Patch Reliability Score, score inputs, evidence timestamp, known-issue applicability, and superseding-update evidence.

## 7. Diagnostic Workflow

### A. Patch-state classification

Read the exact KB/update from DRMM.

Branch:
- INSTALLED: move to verification.
- APPROVED_PENDING: determine whether the normal patch window has occurred.
- INSTALL_ERROR/FAILED: move to diagnostics.
- NOT_APPROVED: set approval_blocked; Jason does not approve patches unless specifically authorized.
- ambiguous/missing object: investigate supersedence or identity before remediation.

An approved-pending patch before its maintenance window is not a failure.

### B. KB intelligence and Patch Reliability Score

Before recommending approval of a missing/unapproved KB, Jason must research and document the patch itself.

#### Required KB intelligence

For each exact KB, capture:
- KB number and exact Microsoft title;
- product / OS / build applicability;
- release date;
- security vs quality classification;
- relevant CVEs and official severity/exploitation status where available;
- reboot requirement;
- Microsoft Known Issues / Release Health status;
- whether Microsoft has paused, withdrawn, safeguarded, mitigated, or superseded the update;
- whether a later cumulative or out-of-band update specifically resolves regressions in the original patch;
- credible external issue reports, clearly separated from official confirmation;
- AOT deployment evidence on comparable endpoints when available;
- whether any known issue is actually relevant to the target endpoint's role, hardware, domain state, applications, or features.

Use authoritative Microsoft sources first: the KB article, Windows Release Health, MSRC/CVE guidance, .NET release notes, and Microsoft Update Catalog metadata where appropriate. Community reports are secondary evidence and must never outweigh a current official Microsoft statement.

#### Security Urgency

Security urgency is recorded separately from reliability.

Suggested values:
- `Emergency` — active exploitation / KEV / urgent vendor direction or equivalent;
- `Critical` — critical RCE/EoP or equivalent high-impact security exposure;
- `High` — important security exposure with meaningful risk;
- `Standard` — normal security/quality maintenance.

A high Security Urgency does **not** increase the Patch Reliability Score. If a patch is urgent but unreliable, Jason should escalate the tradeoff and seek a superseding update, mitigation, or bounded pilot rather than pretending the patch is safe.

#### Patch Reliability Score

Score each KB from **0-100** using the following deterministic dimensions:

1. **Official vendor health — 0-35**
   - 35: no current official known issue relevant to the update/platform and no pause/safeguard/withdrawal;
   - 25: known issues exist but are confirmed not applicable to the target endpoint/role;
   - 15: known issues are applicable but mitigated and low operational risk;
   - 0: active severe relevant known issue, Microsoft pause/withdrawal/safeguard, or official recommendation that makes broad deployment inappropriate.

2. **AOT fleet evidence — 0-30**
   - 30: at least 25 comparable successful installs, >=97% success, with no correlated post-patch incident pattern;
   - 20: at least 10 comparable successful installs, >=95% success, with no correlated incident pattern;
   - 10: 3-9 comparable successful installs with no correlated incident pattern;
   - 5: insufficient internal deployment evidence;
   - 0: material correlated failures, rollback pattern, or significant AOT incident evidence.

3. **Release maturity — 0-15**
   - 15: released >=14 days;
   - 10: 7-13 days;
   - 5: 3-6 days;
   - 0: <72 hours.

4. **Credible ecosystem evidence — 0-10**
   - 10: no credible widespread problem pattern found;
   - 5: isolated/unconfirmed reports only;
   - 0: broad reproducible issue pattern from credible sources.

5. **Target applicability — 0-10**
   - 10: known problem areas do not apply to the endpoint's actual role/features;
   - 5: applicability cannot be confidently determined;
   - 0: endpoint uses a feature/role/hardware directly affected by a known issue.

Total: **0-100**.

#### Reliability labels

- **80-100 — Considered Safe**
  - reasonable candidate for normal approval/maintenance;
  - this means no material blocker was found under the current evidence window, **not zero risk**.
- **60-79 — Generally Safe**
  - reasonable to approve after normal safeguards; consider a pilot first for servers/critical roles or when AOT fleet evidence is thin.
- **40-59 — Caution**
  - do not broadly approve yet; pilot only when justified by security urgency and governance.
- **20-39 — Hold**
  - do not approve broadly; recheck vendor status, AOT telemetry, and supersedence.
- **0-19 — Don't Install**
  - do not approve the patch in its present form; seek a superseding/corrective update or alternate mitigation.

#### Hard-stop / score-cap rules

Regardless of arithmetic:
- if Microsoft has withdrawn/paused the patch or recommends rollback/uninstall, cap at **19 / Don't Install**;
- if a severe known issue directly applies to the target and has no effective mitigation, cap at **39 / Hold**;
- if a newer cumulative/OOB update specifically fixes regressions in the older cumulative update, do not recommend approving the older update when the corrective update is applicable; classify the older update as **Don't Install / Prefer superseding update**;
- if exact KB identity, applicability, or authoritative source evidence cannot be established, do not invent a score: set `intelligence_blocked`;
- AOT internal success telemetry may improve confidence but may not override a Microsoft withdrawal/safeguard or a directly applicable severe known issue.

The score is **KB + platform + endpoint-role specific**. The same KB may legitimately receive a different recommendation for an RDS server, a domain-joined workstation, and a standalone laptop.

#### Approval recommendation

After scoring:
- Considered Safe: recommend approval in the normal maintenance path.
- Generally Safe: recommend approval with normal safeguards; pilot first for critical systems when internal evidence is limited.
- Caution: recommend pilot/limited deployment only; hold broad approval.
- Hold: recommend no approval yet and schedule a recheck.
- Don't Install: recommend rejection of the specific KB and evaluation of a superseding/corrective update or mitigation.

Jason may **recommend** approval based on this workflow. Actual patch approval remains governed and must use an explicitly authorized patch-approval capability if one is added in the future.

### C. Patch-window check

If APPROVED_PENDING and the applicable patch window has not completed:
- do not force-install
- set state=waiting_patch_window
- document the expected recheck
- use Scheduled - Remote or another appropriate waiting status if configured
- resume after the patch window plus reasonable processing/reboot grace

### D. Standard Windows Update diagnostic component

Primary component:
**Diagnose & Fix Windows Update Issues [WIN] AOT Ver 06102026-1**
Component UID: **3369bb12-66e5-42bb-a5d6-669e3bbb20ec**

First diagnostic execution should use:
- WU_AutoFixCore=False
- Schedule230AMReboot=False
- usrClearWSUS=False

Purpose:
- report OS/update health
- inspect Windows Update services
- identify WSUS configuration
- test Microsoft Update connectivity
- report Datto patch-policy presence
- provide ticket-ready findings

Retrieve terminal job state and actual StdOut/StdErr. Job submission alone is not success.

### E. Supplemental evidence when needed

If diagnosis is inconclusive or patch failure persists:
- exact WindowsUpdateClient Event ID/error/HRESULT
- DISM /Online /Cleanup-Image /CheckHealth
- DISM /ScanHealth when justified
- SFC verification/scan when justified
- Windows Update service state
- current reboot-required state
- WSUS policy configuration
- recent patch/install history

Do not assume error 0x80073712 proves persistent component-store corruption. OWNi7JAN25 demonstrated that Windows Update can return 0x80073712 while DISM/SFC later report healthy state.

## 8. Decision Gates

Before recommending patch approval:
- exact KB identity and applicability proven
- Patch Reliability Score completed from current evidence
- hard-stop rules evaluated
- Security Urgency recorded separately
- supersedence/corrective-update check completed
- recommendation documented in the ticket

Before repair:
- exact device and KB identified
- Jason ownership/device association complete
- endpoint online
- applicable patch window has completed OR explicit owner approval allows earlier remediation
- patch remains missing/pending/failed
- diagnostic evidence supports Windows Update stack remediation
- no conflicting patch-policy/maintenance condition exists

Before reboot:
- query live Windows interactive session state; never use DRMM last_logged_in_user as proof
- Active or Disconnected session = user session present
- no user session = unattended

Before clearing WSUS:
- confirm WSUS policy is erroneous/unwanted for that endpoint
- obtain explicit approval unless an approved autonomous playbook version explicitly grants it

## 9. Remediation

### A. Windows Update core repair

Use:
**Diagnose & Fix Windows Update Issues [WIN] AOT Ver 06102026-1**

Repair flags:
- WU_AutoFixCore=True
- Schedule230AMReboot=False by default
- usrClearWSUS=False by default

This resets core Windows Update components only when issues are detected, including BITS/WUAUSERV, SoftwareDistribution, Catroot2, and triggers a scan.

Authority: modifying but normally non-user-disruptive. Remains governed.

### B. WSUS policy repair

Set usrClearWSUS=True only when authoritative evidence shows stale/incorrect WSUS policy is the blocker and the action is specifically authorized.

Authority: modifying/configuration-changing.

### C. Reboot handling

Do not use the component's reboot flag blindly.

Preferred Jason logic:
1. Perform a live interactive-session check.
2. If no Active/Disconnected session and reboot is approved within playbook authority, reboot according to governance.
3. If any user session exists, do not reboot immediately.
4. Schedule a one-time **2:30 AM** reboot.
5. Persist state=reboot_pending.
6. Resume at approximately **3:00 AM**.
7. Verify reboot actually occurred using last-boot timestamp/DRMM evidence before continuing.

If using the component's Schedule230AMReboot=True option, Jason must still satisfy the live-session and authority gates before scheduling it.

### D. Patch retry

After repair, re-detect patch state and allow the normal/authorized patch installation mechanism to retry the already-approved update.

Do not silently approve new patches.

## 10. Retry Policy

Maximum two full repair/install cycles.

A full cycle includes:
- current patch-state read
- diagnostic evidence
- Windows Update repair if justified
- patch re-detection/retry
- reboot handling if required
- post-action patch verification

After two failed cycles, transition to escalated.

Do not repeat DISM/SFC/cache-reset work indefinitely.

## 11. Periodic Rechecks

For hold_watch:
- for Emergency/Critical security urgency, recheck vendor status/internal evidence at least daily while the ticket remains actionable;
- for High/Standard urgency, recheck on a reasonable 48-72 hour cadence or when Microsoft/AOT evidence changes;
- each later recheck is documented as a recheck event, but do not create command-by-command note noise.

For waiting_patch_window:
- recheck after the scheduled maintenance window plus a reasonable grace period.

For reboot_pending:
- recheck around 3:00 AM after a 2:30 AM scheduled reboot.

For retrying_patch:
- use bounded rechecks appropriate to Datto patch execution timing.

Suppress duplicate scheduled jobs/reboots and stop rechecks after complete/escalated/closed/stale state.

## 12. Aging / Stale Condition

If a critical missing-patch ticket remains unresolved across multiple patch windows or beyond the defined SLA:
- investigate stale VulScan evidence
- check supersedence/build mismatch
- check endpoint rename/reimage/replacement
- validate patch-policy assignment
- escalate rather than leave the ticket in an endless waiting state

## 13. Dependency Handling

Dependencies include:
- valid DRMM endpoint identity
- Autotask configuration item
- Datto patch inventory
- approved AOT Windows Update diagnostic/repair component
- scheduler/recheck support
- interactive-session checker
- governed reboot capability
- authoritative public patch-intelligence retrieval (Microsoft KB / Release Health / MSRC)
- AOT fleet patch-outcome telemetry or a bounded fallback method to establish internal evidence

If fleet-wide patch success/failure aggregation is not yet available, score AOT fleet evidence as `5 - insufficient internal deployment evidence` rather than guessing. Track fleet telemetry aggregation as an implementation gap; it should eventually correlate patch install outcomes with post-patch Autotask/DRMM incidents.

If a dependency is missing:
1. verify it is actually missing
2. search for an existing support/dependency issue
3. suppress duplicates
4. create one when appropriate
5. cross-reference it
6. set state=blocked

## 14. Documentation Requirements

Use the global session-summary rule: do not create one ticket note per command. During a normal troubleshooting/research session, create one consolidated progress note covering the meaningful work. A later scheduled recheck (for example, patch still held or endpoint still offline) is a new note-worthy event.

Every patch/VulScan progress note must include a plain-English **KB intelligence summary** for each targeted KB.

Minimum KB fields:
- KB number and title;
- release date/product/build;
- what the update fixes or why it matters;
- security urgency;
- current DRMM install/approval state;
- reboot requirement;
- Microsoft known-issue status;
- relevant target-specific known issues;
- superseding/corrective update, if any;
- AOT fleet evidence level;
- Patch Reliability Score and label;
- recommendation: Approve / Pilot / Hold / Don't Install / Prefer superseding update;
- evidence timestamp and named authoritative sources.

Also document, as applicable:
- whether the patch window has occurred;
- endpoint online/reboot state;
- component flags used;
- meaningful job ID and terminal status;
- relevant sanitized StdOut/StdErr;
- HRESULT/event evidence;
- DISM/SFC results when used;
- repair/retry count;
- live-session/reboot decision;
- post-action verification.

Recommended progress-note format:

```
Jason - Patch Playbook - Progress Update

KB512xxxx - <Microsoft title>
Security urgency: <Emergency|Critical|High|Standard>
DRMM state: <NOT_APPROVED|APPROVED_PENDING|INSTALLED|INSTALL_ERROR>
Reboot required: <Yes|No>
Patch Reliability: <score>/100 - <label>
Microsoft status: <known issues / no known issues / safeguard / superseded>
Target applicability: <relevant endpoint-specific impact>
AOT fleet evidence: <summary or insufficient data>
Recommendation: <Approve|Pilot|Hold|Don't Install|Prefer superseding update>
Why: <short evidence-based rationale>

Session progress: <diagnostics/remediation summary>
Next step: <next action/recheck/blocker>
```

Suggested notes:
- Jason - Patch Playbook - Progress Update
- Jason - Patch Playbook - Recheck
- Jason - Patch Playbook - Waiting Patch Window
- Jason - Patch Playbook - Windows Update Repair
- Jason - Patch Playbook - Reboot Scheduled
- Jason - Patch Playbook - Verification
- Jason - Patch Playbook - Escalation
- Jason - Patch Playbook - Resolution

## 15. Failure Handling

Explicitly document:
- component provider failure before job creation
- component job failure
- missing output
- Windows Update HRESULT
- patch still pending after maintenance
- contradictory DISM/SFC/event evidence
- failed reboot verification
- update still missing after repair/retry

Do not infer success from a component submission.

## 16. Escalation Criteria

Escalate to Help Desk I when:
- two full repair/install cycles fail
- Windows servicing corruption cannot be repaired by the approved component path
- patch remains missing across authorized windows without explainable state
- WSUS/policy changes beyond approved scope are required
- supersedence/build state is ambiguous
- Patch Reliability is Hold/Don't Install and the vulnerability is Emergency/Critical, requiring a human risk decision or alternate mitigation
- authoritative patch intelligence is unavailable or contradictory
- manual servicing/install media is required
- disruptive action beyond playbook authority is required

Include all HRESULTs, repair jobs, outputs, patch states, and recommended next step.

## 17. Verification

Authoritative verification must include:
- exact KB installed OR authoritative supersedence/build proof
- if an approval recommendation was required, the KB intelligence/score was refreshed close enough to the decision to remain current
- patch no longer APPROVED_PENDING/INSTALL_ERROR for the targeted condition
- DRMM patch status healthy or otherwise explained
- no unexpected approved pending patch remains
- reboot_required=False after any required reboot
- endpoint remains healthy/online
- VulScan/monitor finding clears or is proven stale

## 18. Completion Criteria

Complete only when:
- identity/association are correct
- patch state/root cause is classified
- required remediation/reboot completed
- authoritative exact-KB/build verification succeeds
- related monitoring condition is resolved/stale by evidence
- final internal note exists

## 19. Final Resolution Note

Include original missing KB, patch state, Windows Update error/HRESULT if any, diagnostic findings, repair component/flags/jobs, reboot handling, number of attempts, final KB/build/DRMM state, and resolution timestamp.

## 20. Required Capabilities

- Autotask ticket read/update/note/create
- Autotask configuration search/association
- DRMM endpoint read/search
- DRMM patch search
- Microsoft KB / Release Health / MSRC intelligence retrieval
- AOT fleet patch-outcome aggregation (preferred; currently a capability gap if unavailable)
- DRMM component search/execute/job/output
- governed read-only Windows commands when supplemental evidence is required
- interactive Windows session check
- governed reboot/scheduled reboot
- persisted state and scheduler/recheck support

## 21. Acceptance Test

Primary acceptance case:
- Ticket: T20260905.0004
- Client: Riggins Company
- Device: OWNi7JAN25
- KB: KB5121003

Known case evidence:
- patch is approved
- patch previously failed with Windows Update HRESULT 0x80073712
- DISM/SFC/component-store evidence subsequently appeared healthy
- patch remains APPROVED_PENDING
- owner directed Jason to respect the normal patch window rather than force installation

Secondary live scoring case:
- Ticket: T20260923.0066
- Client: Full Circle Financial Group
- Device: LT-FCF50827
- KBs: KB5124008 and KB5126052
- Known case evidence on 2026-09-24: both exact patches were NOT_APPROVED in DRMM.
- Acceptance should prove that Jason researches each KB separately, detects corrective/superseding update evidence, produces distinct reliability scores, writes the KB intelligence into the ticket note, and hands off cleanly when patch approval capability is unavailable.

Acceptance must prove:
1. ticket moved/kept in Jason queue
2. correct configuration item association
3. exact KB identification
4. APPROVED_PENDING before-window path waits instead of forcing install
5. post-window path rechecks exact KB
6. diagnostic component first runs with all repair flags false
7. WU_AutoFixCore=True is only used after repair gate
8. WSUS clearing remains separately gated
9. live-session gate protects logged-in users from reboot
10. 2:30 AM/3:00 AM scheduled reboot/resume path works
11. maximum two repair cycles
12. exact final KB/build verification before completion

## 22. Section Goal Closure

Close after:
- playbook implementation is registered in Project Jason
- OWNi7JAN25 acceptance completes or an equivalent controlled case passes
- required session-check/recheck capabilities are proven
- Grafana/Project Jason playbook status is updated
- limitations/support items are documented

## 23. Autonomous Execution Eligibility

autonomous_allowed: false

Approval owner: pending
Approval date: pending
Approved version/fingerprint: pending

This new/changed playbook version requires explicit autonomy review before any autonomous remediation is permitted.

Potential future autonomous scope after acceptance:
- read-only ticket/device/patch diagnostics
- ownership/device-association updates
- diagnostic-only component execution
- waiting/recheck state transitions

Still per-run approval-bound unless explicitly approved by policy:
- patch approval changes, regardless of score, until a separate patch-approval authority policy is accepted
- WU_AutoFixCore=True remediation
- usrClearWSUS=True
- reboot/shutdown
- any user-disruptive action
- patch approval changes
