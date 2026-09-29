# Jason Playbook: Windows Unexpected Shutdown / Site Correlation

Version: 1.1.0  
Playbook ID: `unexpected_shutdown`  
Status: implementation candidate; owner-approved design change on 2026-09-29; production autonomy requires exact 1.1.0 durable promotion and acceptance  
Autonomous execution target: read-only diagnosis plus clean site-correlated closure; device-specific, ambiguous, protected-role, storage-risk, and repair branches require human review

## 1. Section Goal

**Goal:** Allow Jason to distinguish site/environmental shutdown events from device-specific shutdowns, verify each affected device independently for post-event storage/hardware damage, and safely complete only clean site-correlated incidents.

**Success means:**
- exact ticket/client/site/device identity is proven;
- shutdown timing and clean-vs-abrupt evidence is collected;
- same-site physical devices are correlated in a bounded incident window;
- virtual machines do not inflate the physical site threshold;
- every affected device still receives an independent risk check;
- read-only disk, volume, reliability, WHEA, and storage-event evidence is collected;
- a stable site-event ID groups correlated shutdowns without merging unrelated events;
- clean site/environmental cases may complete only after authoritative healthy verification;
- device-specific, ambiguous, recurring unexplained, protected-role, storage-risk, or repair-required cases go to Human Review;
- no repair or disruptive action is performed without separate authority.

## 2. Trigger

Apply to Windows unexpected shutdown/restart alerts or tickets, including:

`The previous system shutdown at <time> on <date> was unexpected.`

Evidence may originate from DRMM monitoring, Windows Event Log, Autotask, or a technician request tied to an exact endpoint.

## 3. Scope and Boundaries

### In Scope
- Windows physical workstations and servers.
- Windows VM guests for independent health assessment.
- Autotask ticket/recent-ticket reads and internal documentation.
- DRMM endpoint, alert, history, audit, and job reads.
- Governed read-only PowerShell for Windows event, WHEA, storage, disk, reliability, and volume health.
- Same-site physical-device correlation.
- Stable site-event grouping.
- Ticket completion for clean site-correlated incidents after verification.
- Human-review routing for unsafe/uncertain/device-specific cases.

### Out of Scope
- automatic reboot/shutdown;
- CHKDSK repair modes such as `/f` or `/r`;
- offline disk repair;
- formatting or partition modification;
- firmware/BIOS/driver changes;
- storage replacement;
- crash-dump deletion;
- UPS/PDU changes;
- service interruption;
- any other disruptive action without separate explicit authority.

The existing `Comprehensive Disk & Storage Diagnostic [WIN] AOT Ver 07232026` component is not standing-safe under current component governance and must not be silently promoted or substituted. The playbook uses the active governed read-only PowerShell capability for non-mutating health evidence. A future dedicated CHKDSK scan component may be reviewed separately.

Preserve Central Orchestrator authority, `direct_provider_access=false`, exact requester grants, provider/client isolation, bounded retries, approval controls, and auditability.

## 4. Initial Identification

Before substantive diagnostics:

1. Resolve exact Autotask ticket, company, site, and configuration item.
2. Resolve exact DRMM endpoint UID and hostname.
3. Record alert/event timestamp and timezone.
4. Determine physical vs virtual device classification.
5. Record current online state and uptime where available.
6. Complete the standard Jason work-start lifecycle:
   - queue **Jason**;
   - status **In Progress**;
   - Work Type **Remote Support** where applicable;
   - authoritative readback verification.
7. Fail closed on identity ambiguity or failed ownership transition.

## 5. Expected State

Healthy expected state:
- endpoint is online or has an explained current state;
- shutdown is classified as planned/clean, site-correlated, device-specific, or undetermined;
- no unresolved BSOD/WHEA/storage/controller/NTFS/disk health concern exists;
- no unexplained recurrence threshold is met;
- site correlation is complete enough to support the classification;
- current monitoring and endpoint health are stable;
- final documentation and terminal readback succeed.

## 6. State Model

Primary:

`identified -> ownership_ready -> diagnosing -> correlating -> health_check -> classifying -> verifying -> complete`

Waiting:
- `waiting_device_access`
- `waiting_site_recovery`
- `waiting_recheck`

Human-review / exception:
- `identification_blocked`
- `ownership_blocked`
- `diagnostic_blocked`
- `device_specific`
- `site_environmental`
- `site_correlated_small_site`
- `undetermined`
- `recurring_issue`
- `device_specific_risk`
- `protected_role_review`
- `evidence_conflict`
- `escalated`

Persist completed evidence and classification fingerprints so retries/rechecks do not duplicate work.

## 7. Diagnostic Workflow

### Step 1 — Establish shutdown character

Collect read-only Windows event evidence, including:
- 6008 unexpected shutdown;
- Kernel-Power 41;
- 6006 clean Event Log shutdown;
- 1074 planned/user/process restart;
- BugCheck 1001;
- WHEA;
- storage/controller/NTFS events such as 7, 9, 11, 51, 55, 57, 98, 129, 140, 153, 154, 157;
- Windows Update/reboot evidence where available.

Classify:
- `CLEAN_OR_PLANNED`
- `ABRUPT_OR_UNCLEAN`
- `UNDETERMINED`

Never infer root cause from Event 6008 or Event 41 alone.

### Step 2 — Current endpoint state

Collect:
- online/offline;
- uptime / last boot;
- reboot-required state;
- current critical DRMM alerts;
- endpoint role / device type.

Offline devices enter `Waiting Device Access`; they do not consume an active-work slot.

### Step 3 — DRMM operational correlation

Check component jobs, scripts, patch/reboot activity, monitor transitions, technician jobs, and other automation near the incident.

A restart is considered planned only when authoritative job/event timestamps align.

### Step 4 — Recurrence check

Search a 30-day default window for related shutdown/crash incidents on the same endpoint.

Recurrence becomes device-specific risk when **2 or more unexplained independent incidents** occur within 30 days.

Events belonging to the same verified site/environmental incident do not count as independent recurring device failures.

### Step 5 — Site/device correlation

Use an initial **±15 minute** incident window.

Count only distinct physical devices. VM guests do not establish the site threshold.

Record:
- affected physical devices;
- active physical devices at the site;
- physical peers checked;
- ambiguous peers;
- affected/active ratio.

Classification:
- **SITE_ENVIRONMENTAL** — at least 3 physical devices at the site show correlated unexpected shutdown evidence in the window.
- **SITE_CORRELATED_SMALL_SITE** — exactly 2 affected physical devices and they represent all known active physical devices at the small site, with no ambiguity.
- **DEVICE_SPECIFIC** — exactly 1 affected physical device and no unresolved peer ambiguity.
- **UNDETERMINED** — evidence is insufficient, peers are ambiguous/unreadable, or correlation cannot be proven.

A stable site-event ID is generated from site identity plus the incident-time bucket so separate tickets from the same event converge on one operational event.

### Step 6 — Independent per-device storage and hardware check

Run governed read-only PowerShell for:
- `Get-PhysicalDisk` health/operational state;
- storage reliability counters;
- `Get-Volume` filesystem/volume health;
- WHEA history;
- storage/controller/NTFS event history.

This check runs even when the shutdown is clearly site/environmental.

Do not treat a site event as proof that every device is healthy.

### Step 7 — Stability and role check

Critical/protected roles such as server, domain controller, Hyper-V/physical host, database server, or backup repository require Human Review in this version even when site correlation is strong.

Workstations may proceed toward site-event closure only when all independent health evidence is clean.

## 8. Decision Gates

### Gate 1 — Exact ticket/device identity proven?
- No -> block/escalate.
- Yes -> continue.

### Gate 2 — Work-start transition verified?
- No -> stop before diagnostics.
- Yes -> continue.

### Gate 3 — Evidence collection complete?
- No -> Human Review.
- Yes -> continue.

### Gate 4 — Site classification?
- `SITE_ENVIRONMENTAL` -> independent device-risk check.
- `SITE_CORRELATED_SMALL_SITE` -> independent device-risk check.
- `DEVICE_SPECIFIC` -> deeper device-specific investigation / Human Review.
- `UNDETERMINED` -> Human Review.

### Gate 5 — Independent device risk?
Risk includes:
- BSOD/BugCheck;
- WHEA;
- storage/controller/NTFS errors;
- physical disk/volume health warnings;
- reliability read/write errors;
- unexplained recurrence.

If yes -> Human Review regardless of site classification.

### Gate 6 — Protected/critical role?
- Yes -> Human Review.
- No -> continue.

### Gate 7 — Clean site-correlated workstation?
If site classification is `SITE_ENVIRONMENTAL` or `SITE_CORRELATED_SMALL_SITE`, all health evidence is complete/clean, endpoint is stable, and no independent risk exists -> verified closure path.

## 9. Remediation

### Autonomous permitted behavior
- governed reads;
- governed read-only endpoint PowerShell;
- internal Autotask notes;
- standard queue/status transitions;
- ticket completion only for a clean verified site-correlated workstation branch.

### Human-review / approval-bound behavior
- device-specific shutdown root-cause work;
- filesystem repair;
- CHKDSK repair/offline scan;
- storage repair/replacement;
- reboot/shutdown;
- driver/firmware changes;
- any service interruption.

No playbook branch self-authorizes repair.

## 10. Retry Policy

- Maximum one normal evidence collection pass per incident.
- Retry read/output retrieval rather than redispatching diagnostics when only output retrieval failed.
- Use bounded provider-read retries under common runtime policy.
- No endless polling.
- No duplicate site-event creation for the same site/time bucket.

## 11. Periodic Rechecks

Use rechecks when:
- target is offline;
- site devices are recovering;
- monitor state has not stabilized;
- current health cannot yet be verified.

Initial target cadence: every 10 minutes where runtime scheduling supports it.

Stop on verified recovery, closure, escalation, stale threshold, or retired/replaced asset classification.

## 12. Aging / Stale Condition

Escalate when:
- endpoint remains unavailable beyond the active recheck window;
- incident evidence is too old to classify reliably;
- device identity is stale/duplicate/replaced;
- required same-site evidence is unavailable;
- repeated unexplained incidents continue;
- provider evidence conflicts.

## 13. Dependency Handling

Required dependencies:
- Autotask ticket/configuration read/search/update/note;
- DRMM endpoint/search/read/history/audit;
- active governed `endpoint.powershell.read`;
- persisted playbook state;
- scheduled recheck support where used.

Missing capabilities are explicit blockers. Do not fall back to generic shell/provider access.

## 14. Documentation Requirements

Suggested note classes:
- `Jason - Unexpected Shutdown - Asset Validation`
- `Jason - Unexpected Shutdown - Diagnostic`
- `Jason - Unexpected Shutdown - Correlation`
- `Jason - Unexpected Shutdown - Device Specific`
- `Jason - Unexpected Shutdown - Recheck`
- `Jason - Unexpected Shutdown - Verification`
- `Jason - Unexpected Shutdown - Human Review`
- `Jason - Unexpected Shutdown - Resolution`

Include:
- incident timestamp;
- shutdown character;
- site classification;
- affected and active physical-device counts;
- site-event ID;
- VM exclusion statement;
- recurrence result;
- WHEA/storage/disk/volume/reliability findings;
- protected-role status;
- independent-device-risk result;
- what changed;
- final disposition.

Never record secrets.

## 15. Failure Handling

Fail closed for:
- ambiguous identity;
- failed ownership transition;
- unavailable/malformed alert history;
- incomplete same-site evidence;
- failed read-only PowerShell health collection;
- physical/virtual ambiguity affecting classification;
- conflicting evidence;
- missing required capability.

A failed diagnostic is not healthy evidence.

## 16. Escalation Criteria

Human Review when any of the following applies:
- `DEVICE_SPECIFIC`;
- `UNDETERMINED`;
- protected/critical role;
- 2+ unexplained independent shutdowns in 30 days;
- BSOD/BugCheck;
- WHEA;
- storage/controller/NTFS risk;
- physical disk/volume health warning;
- reliability read/write errors;
- evidence conflict;
- current instability;
- disruptive/repair action required.

## 17. Verification

Before site-correlated closure verify:
- exact endpoint/ticket identity;
- current endpoint online/stable;
- site classification proven;
- complete read-only health evidence;
- no unresolved BSOD/WHEA/storage risk;
- no unexplained independent recurrence;
- role is eligible for automatic closure;
- monitoring/alert state is cleared or explained;
- final note exists;
- Autotask terminal status write and independent readback succeed.

A command returning success is not incident resolution.

## 18. Completion Criteria

Automatic completion is allowed only for:
- `SITE_ENVIRONMENTAL` or `SITE_CORRELATED_SMALL_SITE`;
- eligible workstation;
- complete clean device health evidence;
- no independent device risk;
- successful final documentation;
- terminal ticket-state readback.

Device-specific, ambiguous, protected-role, or risk-bearing cases remain open and are handed to Help Desk I / Human Review.

## 19. Final Resolution Note

Example:

`Unexpected shutdown correlated to site event <site-event-id>. 6 of 8 active physical devices showed matching shutdown evidence within ±15 minutes. This endpoint passed independent post-event checks: no WHEA/storage/controller/NTFS finding, physical disk and volume health normal, no reliability read/write errors, and no unexplained independent recurrence. No repair or reboot was performed. Ticket completed after terminal readback verification.`

## 20. Required Capabilities

- Autotask ticket/configuration read/search;
- Autotask internal note create;
- Autotask ticket work-start/handoff/update/complete;
- DRMM endpoint search/read/audit;
- DRMM alert/history reads;
- governed `endpoint.powershell.read`;
- persisted playbook state;
- scheduled recheck support.

No disruptive capability is required for the autonomous closure branch.

## 21. Acceptance Test

Acceptance matrix must prove:

1. one affected workstation at a healthy multi-device site -> `DEVICE_SPECIFIC` and Human Review;
2. six of eight physical devices affected within ±15 minutes -> `SITE_ENVIRONMENTAL`;
3. two of two physical devices at a small site -> `SITE_CORRELATED_SMALL_SITE`;
4. VMs do not count toward physical threshold;
5. ambiguous/unreadable peers -> `UNDETERMINED`;
6. site event + clean workstation health -> completion;
7. site event + Event ID 7/WHEA/reliability/volume-health risk -> Human Review;
8. protected server role -> Human Review;
9. offline endpoint -> waiting-device state;
10. no CHKDSK repair/reboot/storage mutation occurs;
11. terminal completion is independently read back;
12. site-event IDs remain stable for tickets in the same incident bucket.

Controlled historical cases may be used for evidence-only acceptance. Do not intentionally cause an abrupt shutdown.

## 22. Section Goal Closure

Close implementation work only after:
- source change is committed;
- tests pass;
- PR review/CI passes;
- exact 1.1.0 durable autonomy approval is recorded;
- production deployment is confirmed;
- one controlled live or historical acceptance proves site correlation and disk-health evidence;
- Grafana/Project Jason status is updated;
- any CHKDSK-scan enhancement remains documented as a separate governed capability item.

## 23. Autonomous Execution Eligibility

Target autonomy:

`autonomous_allowed: site_environmental_clean_closure`

Owner decision: approved in conversation on 2026-09-29 for implementation of the described site-vs-device correlation, post-shutdown disk-health checks, and safe clean-site closure behavior.

The approval does **not** authorize:
- generic shell access;
- CHKDSK repair;
- storage repair;
- reboot/shutdown;
- firmware/driver changes;
- device-specific automatic closure.

Production authority still requires a durable exact `unexpected_shutdown@1.1.0` promotion record for:
- `service.ticket.note.create`
- `service.ticket.update`

Any later material change invalidates that exact-version promotion until re-reviewed.
