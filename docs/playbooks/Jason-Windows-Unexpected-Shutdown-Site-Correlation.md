# Jason Playbook: Windows Unexpected Shutdown / Site Correlation

Version: 0.1.0  
Playbook ID: `windows_unexpected_shutdown`  
Status: diagnostic branch implementation-ready; isolated-event closure acceptance still pending  
Autonomous execution: diagnostic/correlation branch approved; automatic closure remains gated

## 1. Section Goal

**Goal:** Allow Jason to investigate Windows unexpected-shutdown tickets from intake through evidence-based classification, recurrence/site correlation, documentation, verification, and safe resolution or escalation without performing disruptive remediation.

**Success means:**
- the exact ticket/client/site/device is identified and correctly associated;
- the global ticket-work-start lifecycle is satisfied before substantive diagnostics;
- Windows and DRMM evidence around the shutdown is collected and correlated;
- recent related ticket history is checked for recurrence;
- other physical devices at the same site are checked in the incident window;
- site-wide evidence never masks independent device-specific risk;
- isolated healthy events may resolve only after authoritative verification;
- recurring, ambiguous, hardware/storage, BSOD, or site-wide-risk cases are documented and escalated appropriately.

## 2. Trigger

Apply to tickets/alerts indicating an unexpected Windows shutdown/restart, including messages such as:

`The previous system shutdown at <time> on <date> was unexpected.`

Trigger evidence may originate from DRMM monitoring, Windows Event Log, Autotask, or a technician request tied to a specific endpoint.

## 3. Scope and Boundaries

### In Scope
- Windows physical workstations and servers.
- Windows VM guests for independent device analysis.
- Autotask ticket and recent-ticket reads.
- DRMM endpoint/alert/job/history reads.
- Read-only Windows event/log/uptime diagnostics.
- Site-level correlation across managed devices.
- Internal Autotask documentation.
- Ticket completion for isolated, verified-healthy events when policy permits.
- Escalation/routing for recurring or higher-risk cases.

### Out of Scope
- automatic reboot/shutdown;
- firmware/BIOS changes;
- power-cycle actions;
- storage repair;
- crash-dump deletion;
- driver changes;
- UPS/PDU changes;
- any other disruptive action without separate explicit approval.

Preserve Central Orchestrator authority, `direct_provider_access=false`, exact requester grants, provider/client isolation, bounded retries, approval controls, and auditability.

## 4. Initial Identification

Before substantive diagnostics:

1. Resolve the exact Autotask ticket and client/site.
2. Run the global device-association gate from `docs/operations/Jason-Autotask-Ticket-Work-Lifecycle.md`.
3. Resolve the exact DRMM endpoint and hostname.
4. Record the alert/event timestamp and timezone.
5. Record current online state and current uptime.
6. Determine whether the endpoint is a physical device or VM guest.
7. Immediately before the first ticket-specific diagnostic action, complete the global ticket-work-start lifecycle:
   - queue **Jason**;
   - status **In Progress**;
   - Work Type **Remote Support**;
   - required readback verification.
8. If identity or ownership transition fails, set `state=identification_blocked` or `state=ownership_blocked`, document, and stop before substantive diagnostics.

## 5. Expected State

Healthy expected state:
- endpoint is currently online or has an explained current state;
- no unresolved critical hardware/storage/WHEA condition is present;
- no unresolved BSOD/crash condition remains;
- no repeated unexpected shutdown pattern exists within policy window;
- related DRMM jobs/patching/reboots explain the event when applicable;
- site correlation is classified and documented;
- monitoring has returned to healthy or the alert condition is no longer active.

## 6. State Model

Persisted states:

`identified -> ownership_ready -> diagnosing -> correlating -> classifying -> verifying -> complete`

Exception/terminal states:
- `identification_blocked`
- `ownership_blocked`
- `diagnostic_blocked`
- `recurring_issue`
- `possible_site_wide_event`
- `device_specific_risk`
- `evidence_conflict`
- `escalated`

Persist completed steps so rechecks do not repeat diagnostics unnecessarily.

## 7. Diagnostic Workflow

### Step 1: Shutdown timeline evidence

**Purpose:** establish what Windows recorded around the incident.

Collect read-only evidence around the event window, including:
- Event ID 6008 — unexpected shutdown;
- Kernel-Power 41;
- User32 1074 — planned/user/process restart;
- BugCheck 1001;
- WHEA hardware errors;
- disk/storage/NTFS/controller errors;
- relevant service/application failures;
- crash-dump presence and timestamps;
- Windows Update/reboot activity where available.

Do not infer root cause from Event ID 6008 alone.

### Step 2: Current endpoint state

Collect:
- online/offline;
- current uptime / last boot;
- logged-on user where relevant;
- basic disk/storage health indicators;
- critical current DRMM alerts.

### Step 3: DRMM operational correlation

Check DRMM activity around the incident time for:
- component jobs;
- scripts;
- scheduled reboots;
- patch deployment/restart activity;
- monitor transitions;
- technician-initiated jobs;
- other provider automation.

If a Jason/AOT job explains the restart, classify it as planned only when timestamps and authoritative job evidence align.

### Step 4: Recent-ticket / recurrence check

Search recent related Autotask tickets with a default **30-day lookback** for:
- same device;
- same user when relevant;
- same site;
- same or closely related shutdown/crash symptom.

Document matching ticket numbers, dates, symptoms, and prior resolutions.

If the same device has **2 or more unexpected shutdown incidents within 30 days**, classify `recurring_issue` and require technician attention.

Prior resolutions are evidence only and must not be blindly repeated.

### Step 5: Site-wide correlation

Check other managed devices at the same client site for unexpected shutdowns in an initial incident window of approximately **±15 minutes**.

For threshold purposes:
- count only separate **physical devices**;
- VM guests do **not** count toward establishing the site-wide threshold;
- a physical hypervisor host and another physical endpoint may count separately when they are distinct managed devices.

If **2 or more separate physical devices** at the same site show unexpected shutdown evidence within the incident window, classify/flag:

`Possible Site-Wide Event`

### Step 6: Independent per-device risk check

Even when a site-wide event is detected, evaluate each affected device independently for:
- prior unexpected shutdowns;
- BSOD/bugcheck evidence;
- WHEA errors;
- storage/controller/NTFS errors;
- hardware warnings;
- related open/recent tickets;
- abnormal uptime/restart patterns.

Never close or downgrade an individual device issue solely because a site-wide event exists.

## 8. Decision Gates

### Gate 1 — Exact ticket/device identity proven?
- No -> `identification_blocked`, document and escalate.
- Yes -> continue.

### Gate 2 — Ticket ownership transition verified?
- No -> `ownership_blocked`, stop before diagnostics.
- Yes -> continue.

### Gate 3 — Planned restart authoritatively explained?
- Yes -> classify planned restart and verify no independent risk.
- No -> continue.

### Gate 4 — BSOD/crash evidence?
- Yes -> classify crash/BSOD and escalate unless an approved diagnostic-only path fully explains and verifies health.
- No -> continue.

### Gate 5 — Hardware/storage/WHEA evidence?
- Yes -> classify device-specific risk and escalate.
- No -> continue.

### Gate 6 — Recurrence threshold met?
- Yes -> `recurring_issue`; escalate.
- No -> continue.

### Gate 7 — Site-wide threshold met?
- Yes -> flag `possible_site_wide_event`, then still complete independent device assessment.
- No -> continue.

### Gate 8 — Isolated event with current healthy evidence?
- Yes -> verification/resolution path.
- No/uncertain -> evidence-conflict/escalation path.

## 9. Remediation

Initial version is diagnostic/documentation only.

Allowed modifying actions:
- internal Autotask notes;
- ticket queue/status changes under the accepted global lifecycle;
- ticket completion only for isolated, verified-healthy events where no independent risk remains.

No automatic disruptive repair is authorized by this playbook.

## 10. Retry Policy

- Do not redispatch the same read-only diagnostic merely because output-read failed; retry the read/output operation.
- Maximum one normal diagnostic collection pass per incident unless new evidence justifies a bounded additional read.
- Provider/read failures may receive bounded retry under existing Jason policy.
- No endless polling or remediation loops.

## 11. Periodic Rechecks

Use a recheck when:
- the device is temporarily offline;
- current health cannot yet be verified;
- site devices are still recovering after a suspected power/network event;
- monitoring has not returned to healthy.

Default initial operational target: recheck every **10 minutes** for active offline/site-recovery cases when the runtime scheduler supports it.

Stop on:
- verified recovery;
- ticket closure;
- escalation;
- maximum waiting threshold;
- stale/retired asset determination.

Do not create duplicate scheduled rechecks for the same ticket/playbook generation.

## 12. Aging / Stale Condition

Escalate rather than wait indefinitely when:
- endpoint remains offline beyond the playbook's active recheck window;
- shutdown evidence is too old or incomplete to classify reliably;
- device identity becomes stale/duplicate/replaced;
- repeated events continue;
- provider history is incomplete or contradictory.

## 13. Dependency Handling

Required dependencies may include:
- Autotask ticket read/search/update/note capabilities;
- DRMM endpoint/alert/job/history reads;
- approved read-only Windows event diagnostic component/command;
- persisted playbook state;
- scheduled recheck support.

If scheduled rechecks are unavailable, document the limitation and hand off rather than pretending continuous monitoring exists.

## 14. Documentation Requirements

Every meaningful check must be written as an internal Autotask note.

Suggested titles:
- `Jason - Unexpected Shutdown - Asset Validation`
- `Jason - Unexpected Shutdown - Diagnostic`
- `Jason - Unexpected Shutdown - Correlation`
- `Jason - Unexpected Shutdown - Recheck`
- `Jason - Unexpected Shutdown - Verification`
- `Jason - Unexpected Shutdown - Escalation`
- `Jason - Unexpected Shutdown - Resolution`

Include:
- what was checked and why;
- exact read/command/component;
- target and timestamp;
- result;
- job/correlation ID where available;
- sanitized StdOut/StdErr summary;
- recurrence matches;
- site-correlation result;
- classification;
- next step.

Never record secrets.

## 15. Failure Handling

Document and stop/escalate for:
- ambiguous ticket/device identity;
- failed ownership transition;
- provider read failure;
- missing event evidence;
- ambiguous physical-vs-VM classification affecting threshold logic;
- contradictory shutdown evidence;
- job/output failure;
- unavailable required capability.

Failed checks must never be silently treated as healthy evidence.

## 16. Escalation Criteria

Escalate when any of the following applies:
- 2+ unexpected shutdown incidents on the same device within 30 days;
- BSOD/bugcheck evidence;
- WHEA/hardware/storage/controller/NTFS risk;
- evidence conflict;
- repeated current instability;
- endpoint identity cannot be proven;
- required diagnostics are unavailable;
- site-wide event exists and the individual device has independent risk;
- disruptive remediation would be required;
- current health cannot be authoritatively verified.

## 17. Verification

For an isolated-event resolution, verify:
- exact endpoint/ticket association;
- current endpoint state is healthy enough for closure;
- no unresolved BSOD/WHEA/storage risk;
- recurrence threshold not met;
- site correlation completed;
- no independent device-specific condition remains;
- monitoring/alert state is cleared or otherwise explained;
- all documentation succeeded.

A command returning success is not sufficient verification.

## 18. Completion Criteria

An isolated event may complete only when:
1. identity and ticket association are correct;
2. global ticket ownership lifecycle succeeded;
3. timeline diagnostics completed;
4. 30-day recurrence search completed;
5. site-wide correlation completed;
6. independent device-risk evaluation completed;
7. no unresolved higher-risk condition remains;
8. current healthy-state verification exists;
9. final resolution note is present.

Recurring/site-wide/device-specific-risk cases remain open or are handed off/escalated according to the accepted ticket lifecycle.

## 19. Final Resolution Note

Summarize:
- original shutdown timestamp;
- device/client/site;
- Windows/DRMM evidence;
- recurrence result;
- site-correlation result;
- physical-device threshold count;
- independent device-risk findings;
- classification;
- current health verification;
- final disposition.

## 20. Required Capabilities

Narrow required capabilities:
- Autotask ticket read/search;
- Autotask configuration read/search;
- Autotask internal note create;
- Autotask ticket work-start/handoff/update;
- DRMM endpoint search/read;
- DRMM alert/history reads;
- DRMM component/job/output reads for approved diagnostics;
- persisted playbook state;
- scheduled recheck support when used.

No new disruptive capability is required.

## 21. Acceptance Test

Controlled initial target:
- endpoint: **AOT-50282**
- event: **September 17, 2026, approximately 9:19:01 AM**
- associated Autotask ticket/alert from that incident.

Prove:
1. exact ticket and device association;
2. global ticket-work-start gate before substantive diagnostics;
3. shutdown timeline evidence collection;
4. 30-day related-ticket recurrence search;
5. ±15-minute same-site physical-device correlation;
6. VM guests excluded from threshold count;
7. independent per-device risk evaluation;
8. documentation notes;
9. classification;
10. current-health verification;
11. correct completion or escalation disposition;
12. no disruptive remediation.

Live acceptance must not be executed until Jason runtime/provider access is restored.

## 22. Section Goal Closure

Close only after:
- implementation is committed;
- controlled acceptance succeeds end-to-end;
- limitations/TODOs are documented;
- Grafana/Project Jason status is updated;
- the issue's recurrence/site-correlation rules are proven in acceptance evidence.

## 23. Autonomous Execution Eligibility

`autonomous_allowed: diagnostic_only`

Approval owner: person-al.  
Approval date: 2026-09-26.  
Approved scope: exact `unexpected_shutdown@1.0.0` diagnostic/correlation branch using governed reads plus internal ticket note/work-start updates. Automatic completion remains gated until isolated-event live acceptance succeeds.  
Material changes invalidate this approval until re-reviewed.

Material changes invalidate any future autonomous approval until re-reviewed.
