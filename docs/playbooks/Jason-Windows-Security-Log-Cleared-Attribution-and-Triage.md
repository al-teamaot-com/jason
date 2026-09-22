# Jason Playbook: Windows Security Log Cleared Attribution and Triage

**Playbook ID:** `windows_security_log_cleared_attribution`
**Version:** `1.0.0`
**Status:** Implemented — diagnostic/attribution logic ready; autonomous known-good closure is gated by exact AOT execution-history evidence
**Autonomy posture:** Read-only evidence collection may be eligible when the underlying capability is standing-safe. Security containment, log clearing, service changes, reboots, or other modifying/disruptive actions are not granted by this playbook.
**Primary principle:** A Windows Security log clear is a security-significant event until Jason proves, with exact evidence, that it was an authorized administrative action.

---

## 1. Section Goal

**Goal:**
Investigate Windows Security log-clearing events, especially Event ID 1102 and EDR detections such as `Windows Event Logs Cleared`, determine whether the event was caused by an authorized AOT/DRMM action, an AOT-origin action that behaved unexpectedly, another approved administrator, suspicious/unattributed activity, or insufficient evidence, and then document and route the case correctly.

**Success means:**
- the exact endpoint, event timestamp, user/security context, process, command line, and process ancestry are preserved;
- Jason correlates the event to exact AOT/DRMM execution evidence before considering it authorized;
- `cagservice.exe`, `SYSTEM`, PowerShell, or Microsoft-signed `wevtutil.exe` alone are never treated as authorization evidence;
- suspicious or unattributed events are escalated without destructive remediation;
- authorized events are closed only when the matching administrative action and approval are proven and no contradictory security evidence exists;
- AOT-origin actions that unexpectedly clear the Security log are treated as an engineering/control problem rather than silently normalized.

---

## 2. Trigger

Apply when one or more of the following is present:
- Windows Security Event ID `1102` — “The audit log was cleared”;
- Datto EDR rule/detection such as `Windows Event Logs Cleared`;
- RocketCyber/SOC alert for Security log clear;
- command evidence such as:
  - `wevtutil.exe cl Security`
  - `wevtutil clear-log Security`
  - PowerShell `Clear-EventLog` or equivalent Security-log clear operation;
- an Autotask ticket title/description indicating the Windows Security log was cleared.

The trigger itself does not establish malicious or benign intent.

---

## 3. Scope and Boundaries

### In Scope
- Autotask alert/ticket and note review;
- DRMM endpoint identity and audit evidence;
- Datto EDR detection/search/read evidence;
- DRMM alert/history evidence;
- read-only Windows event-log/process evidence;
- correlation to AOT tickets, technician work, DRMM components, job IDs, approval evidence, and timestamps;
- determination of whether the Security log is currently readable and accumulating new events;
- documentation, ticket completion for fully proven authorized activity, or escalation.

### Out of Scope
- clearing any Windows event log;
- deleting or modifying forensic artifacts;
- rebooting or restarting services;
- disabling security tooling;
- user/account containment unless separately authorized under another security playbook;
- claiming an event is authorized only because it ran as `SYSTEM`;
- claiming an event is authorized only because the process ancestry includes `cagservice.exe`;
- direct provider access outside Jason governance.

Preserve:
- `direct_provider_access=false`
- Central Orchestrator authority
- exact requester grants
- provider/client isolation
- audit trail
- existing approval requirements
- evidence-preservation priority.

---

## 4. Initial Identification

Before triage:
1. Identify the exact Autotask ticket/alert and provider event ID.
2. Identify the client/site and exact endpoint.
3. Resolve the endpoint to authoritative DRMM identity.
4. Record:
   - event time and timezone;
   - alert creation time;
   - Windows Event ID if known;
   - account/SID;
   - process path/name;
   - exact command line;
   - parent and grandparent process;
   - source provider;
   - ticket number and external alert/detection ID.
5. Identify duplicate/consolidated alerts for the same device/event.
6. Determine whether there was known AOT work on that endpoint within the attribution window.

If endpoint/event identity is ambiguous:

`state = identification_blocked`

Document and escalate rather than guessing.

---

## 5. Expected State

Healthy/expected state means:
- the Security log is readable;
- normal Security events are being written after the clear event;
- any intentional Security-log clear has an exact authorized administrative reason;
- the clearing command is traceable to a specific operator/job/component/change;
- no unexplained security detections, suspicious process chain, credential activity, persistence, or defense-evasion evidence accompanies the event.

A cleared Security log cannot be reconstructed merely by declaring the activity benign. Evidence from EDR, Sysmon, PowerShell logs, System/Application logs, RMM job history, and provider telemetry should be preserved because pre-clear Security records may no longer exist locally.

---

## 6. State Model

`identified -> evidence_preserving -> attribution_search -> security_correlation -> classified -> verifying -> complete`

Additional states:
- `waiting_for_job_evidence`
- `attribution_blocked`
- `aot_origin_unexpected`
- `security_escalation`
- `insufficient_evidence`
- `escalated`

Classification values:
- `authorized_aot_activity`
- `aot_origin_unexpected_behavior`
- `approved_non_aot_admin_activity`
- `suspicious_unattributed`
- `provider_confirmed_security_incident`
- `insufficient_evidence_escalate`

Persist exact evidence already gathered so Jason does not repeat or overwrite forensic work unnecessarily.

---

## 7. Diagnostic Workflow

### Step 1: Preserve the original detection facts

**Purpose:** Capture what the security provider observed before running additional diagnostics.

**Evidence source:** Autotask ticket body, Datto EDR detection detail, DRMM alert/history, RocketCyber/SOC ticket content.

Record verbatim/sanitized fields:
- event/detection ID;
- endpoint;
- timestamp;
- user/SID;
- executable and path;
- exact command line;
- parent/grandparent;
- hash/signature where provided;
- MITRE technique where provided;
- provider severity/status.

**Decision**
- Evidence clearly shows a log-clear action -> continue attribution.
- Alert lacks process/command details -> gather independent endpoint/provider evidence; do not infer.

### Step 2: Establish the AOT/DRMM ancestry signal

**Purpose:** Determine whether the process appears to have been launched through Datto RMM.

Strong DRMM-origin signal:
- `wevtutil.exe` or equivalent clear process;
- parent PowerShell/cmd/script host;
- grandparent `cagservice.exe` / AEM agent context.

**Important:** this is **origin evidence, not authorization evidence**.

**Decision**
- DRMM ancestry present -> search for the exact AOT job/action.
- DRMM ancestry absent -> continue broader administrator/security attribution.

### Step 3: Correlate to an exact AOT execution

**Purpose:** Prove whether AOT intentionally caused this exact event.

Required correlation fields when available:
- exact endpoint/device UID;
- DRMM job ID;
- component/script name;
- job execution timestamp;
- operator/requester identity;
- approval/correlation ID;
- terminal status/output;
- command/script behavior;
- related Autotask ticket/note/change.

Default attribution window: **±5 minutes** around the log-clear event. Expand to **±15 minutes** only when provider timestamp skew is documented.

**Known-good authorization gate requires all of the following:**
1. exact endpoint match;
2. timestamp match;
3. exact job/component or technician action identified;
4. evidence that the action was approved/authorized;
5. the component/action was expected to clear the Security log, or the technician explicitly authorized that exact clear;
6. no conflicting security evidence.

If Jason only has `cagservice.exe` ancestry but cannot identify the exact job/action:
-> `classification = insufficient_evidence_escalate`

If an exact AOT job is identified but clearing the Security log was **not** expected or approved:
-> `classification = aot_origin_unexpected_behavior`

### Step 4: Search AOT operational context

**Purpose:** Determine whether a technician/Jason workflow around the same time explains the action.

Review:
- ticket notes;
- recent related tickets for the device;
- Jason job/correlation IDs documented in notes;
- approved troubleshooting/remediation steps;
- support/TODO items indicating a script or component defect.

Do not convert a vague statement such as “we were working on it” into authorization for a Security-log clear.

### Step 5: Correlate other security evidence

**Purpose:** Determine whether the log clear is isolated administrative activity or part of broader suspicious behavior.

Evidence sources:
- Datto EDR detection search/read;
- DRMM alert history;
- RocketCyber/SOC evidence when available in the ticket;
- endpoint security status;
- relevant independent Windows logs.

Check the surrounding window, default **30 minutes before and after**, for:
- malware/EDR detections;
- suspicious PowerShell;
- credential dumping or LSASS access;
- new services/tasks;
- persistence;
- account creation/group changes;
- unusual remote access;
- additional defense-evasion actions;
- repeated log clears.

If other credible IOCs exist:
-> security escalation regardless of apparent AOT ancestry until reconciled.

### Step 6: Collect independent Windows evidence

**Purpose:** Gather records that may survive Security-log clearing.

Read-only sources where available:
- System log;
- Application log;
- Microsoft-Windows-PowerShell/Operational;
- Sysmon;
- Task Scheduler Operational;
- Windows Defender/EDR operational logs;
- DRMM/AEM execution logs.

Look for:
- process creation around the exact time;
- PowerShell script block/command evidence;
- service/task creation;
- RMM script path under CentraStage/AEMAgent;
- unexpected executable parents;
- time skew.

Never clear or truncate any log as part of this diagnostic.

### Step 7: Verify current Security-log health

**Purpose:** Confirm Windows auditing is functioning now.

Read-only checks:
- `Get-WinEvent -LogName Security -MaxEvents 1` or equivalent;
- confirm the Security log opens successfully;
- confirm events newer than the clear event are accumulating;
- inspect Security log metadata such as enabled state and size/retention policy without modifying it.

**Decision**
- Log readable and accumulating -> continue classification.
- Log unreadable/corrupt/unavailable -> separate operational/security problem; document and escalate or route to a repair playbook.

### Step 8: Classify

#### A. `authorized_aot_activity`
Requires exact AOT execution/approval match, expected log-clear behavior, and no conflicting IOC evidence.

Disposition:
- document exact job/component/operator/approval;
- note that the security detection was valid but attributable to authorized AOT administrative activity;
- complete/resolve only after readback and Security-log health verification.

#### B. `aot_origin_unexpected_behavior`
Exact AOT/DRMM execution is identified, but the component/script was not supposed or not approved to clear the Security log.

Disposition:
- do not label benign;
- document the component/job;
- stop autonomous reuse of the offending workflow where governance supports it;
- create/associate a support or TODO item for component correction;
- escalate for technician/security review as appropriate.

#### C. `approved_non_aot_admin_activity`
A known authorized administrator/change is independently proven, but not through AOT/DRMM.

Disposition:
- require exact change/operator evidence;
- document and close only if no contradictory security evidence exists.

#### D. `suspicious_unattributed`
No exact authorized action explains the event.

Disposition:
- preserve evidence;
- treat as potential defense evasion;
- escalate to the security workflow/SOC;
- do not perform destructive remediation.

#### E. `provider_confirmed_security_incident`
Authoritative EDR/SOC evidence confirms malicious or incident-level activity.

Disposition:
- route immediately to the approved security incident workflow;
- preserve all evidence;
- no independent containment action unless separately authorized.

#### F. `insufficient_evidence_escalate`
Evidence suggests a possible administrative origin but cannot prove exact authorization.

Disposition:
- do not close as known-good;
- escalate with the evidence gap clearly stated.

---

## 8. Decision Gates

Before marking an 1102/log-clear event authorized:
1. exact endpoint is confirmed;
2. exact event timestamp is confirmed;
3. exact clear command/process is known or independently corroborated;
4. exact administrative job/change/action is identified;
5. the job/action is authorized;
6. Security-log clearing was expected or explicitly approved;
7. no credible conflicting IOC evidence exists;
8. current Security log is readable and accumulating events;
9. evidence and attribution are documented.

Failure of any gate prevents autonomous known-good closure.

---

## 9. Remediation

This playbook is **attribution and triage first**.

### Authorized AOT activity
**Action:** documentation and ticket/alert closure only.
**Authority:** non-disruptive ticket lifecycle action, subject to existing ticket/alert authority.
**Verification:** exact job/approval match plus healthy current Security log.

### AOT-origin unexpected behavior
**Action:** create/associate engineering/support follow-up; prevent unsupported autonomous reuse when governance permits.
**Authority:** documentation/workflow control only unless separate approval exists.
**Verification:** offending component/job is identified and follow-up is recorded.

### Suspicious/unattributed or provider-confirmed incident
**Action:** security escalation.
**Authority:** documentation/handoff only by default.
**No automatic:** isolation, account disable, password reset, reboot, service stop, log clear, file deletion, or containment unless an approved security playbook separately authorizes it.

---

## 10. Retry Policy

- Provider/connector read failure: retry once when transient transport failure is plausible.
- Read-only endpoint diagnostic: maximum 2 attempts if the first fails due to transport/availability.
- Do not rerun any log-clear-causing component to reproduce the event.
- Do not create duplicate support/security tickets for the same event.
- If exact attribution remains unavailable after bounded evidence collection:
  `state = escalated`.

---

## 11. Periodic Rechecks

Not normally required for a fully attributed historical event.

When waiting for exact job/security-provider evidence:
- default recheck: every 15 minutes for up to 1 hour when durable scheduling exists;
- recheck only missing evidence/state;
- do not repeat forensic commands unnecessarily.

Stop on:
- exact attribution;
- security escalation;
- human ownership;
- ticket closure;
- maximum wait reached.

If durable scheduling is unavailable, do not claim unattended rechecks occurred.

---

## 12. Aging / Stale Condition

Security-log-clear events should not age as ordinary stale monitoring alerts.

Escalate if:
- not attributed within the initial investigation window;
- repeated log clears occur on the same endpoint;
- the same AOT component causes unexpected clears on more than one endpoint;
- the ticket remains open without an attribution classification.

Repeated authorized clears should also be reviewed operationally; routine Security-log clearing reduces forensic visibility and should not become normal maintenance behavior without explicit policy justification.

---

## 13. Dependency Handling

Potential dependencies:
- exact DRMM job ID is not present in the ticket;
- Jason cannot search historical DRMM executions by device/time;
- EDR detection detail is unavailable;
- RocketCyber/SOC detail is only present in external provider UI;
- endpoint is offline;
- independent logs are unavailable after the clear.

Rules:
1. search existing ticket notes/evidence first;
2. do not create duplicate dependency tickets;
3. missing exact job history blocks `authorized_aot_activity` autonomous classification;
4. record the capability gap explicitly;
5. escalate instead of assuming.

---

## 14. Documentation Requirements

Document:
- original alert/event and provider ID;
- exact endpoint/client;
- event timestamp/timezone;
- user/SID;
- command line;
- process/parent/grandparent;
- signature/hash if available;
- AOT/DRMM job ID, component, operator, approval/correlation ID if matched;
- attribution window;
- other security detections checked;
- independent Windows evidence checked;
- current Security-log health;
- final classification;
- closure or escalation decision.

Suggested note titles:
- `Jason - Security Log Clear - Evidence Preservation`
- `Jason - Security Log Clear - AOT Attribution`
- `Jason - Security Log Clear - Security Correlation`
- `Jason - Security Log Clear - Classification`
- `Jason - Security Log Clear - Escalation`
- `Jason - Security Log Clear - Resolution`

Never store passwords, tokens, private keys, or full sensitive secrets.

---

## 15. Failure Handling

Document:
- provider read failures;
- missing process details;
- inability to identify endpoint;
- inability to search execution history;
- timestamp ambiguity;
- endpoint offline;
- unreadable Security log;
- contradictory AOT and EDR evidence;
- missing approval evidence.

A failed attribution is not evidence of benign activity.

---

## 16. Escalation Criteria

Escalate when:
- no exact authorized action explains the event;
- `cagservice.exe` ancestry exists but no exact AOT job can be proven;
- AOT job is proven but Security-log clearing was unexpected;
- additional IOCs exist;
- log clear repeats;
- Security log remains unreadable;
- provider marks the event incident-level;
- endpoint identity or timestamps conflict;
- required evidence cannot be obtained.

Escalation note must summarize the exact evidence gathered, missing evidence, current classification, and recommended security/engineering next step.

---

## 17. Verification

For `authorized_aot_activity` or `approved_non_aot_admin_activity`:
1. exact authorization match is documented;
2. no contradictory security evidence remains unresolved;
3. Security log is readable;
4. new Security events are accumulating;
5. provider alert disposition is consistent with closure where Jason has authority;
6. final ticket note exists.

For `aot_origin_unexpected_behavior`:
1. exact offending AOT job/component is documented;
2. engineering/support follow-up exists;
3. the event is not silently normalized;
4. security review disposition is recorded.

For suspicious/incident classifications:
verification means successful handoff with preserved evidence, not proof of remediation.

---

## 18. Completion Criteria

A ticket may complete as authorized activity only when:
1. endpoint/event identity is exact;
2. the clear command/process is understood;
3. an exact authorized action is proven;
4. Security-log clearing was expected/approved;
5. no unresolved conflicting IOC evidence exists;
6. Security log is healthy now;
7. all evidence is documented;
8. final resolution note exists;
9. ticket/alert closure is read back when Jason performs it.

Otherwise the terminal state is escalation/handoff, not known-good completion.

---

## 19. Final Resolution Note

Include:
- original Event ID/detection;
- endpoint/client;
- event time;
- user/SID;
- command/process ancestry;
- exact AOT job/change match, if any;
- approval evidence;
- security correlation results;
- current Security-log health;
- classification;
- support/security handoff if applicable;
- final disposition and timestamp.

For authorized AOT activity, wording should make clear that the detection itself was technically valid but matched a proven approved administrative action.

---

## 20. Required Capabilities

Current/narrow capabilities:
- `service.ticket.search/read`
- `service.ticket.notes.search`
- governed ticket note create/update/closure
- `endpoint.device.search/read`
- `endpoint.alert.search`
- `endpoint.alert.history.search`
- `endpoint.security.detection.search/read`
- `endpoint.security.status.read`
- `automation.job.read`
- `automation.job.output.read`
- governed read-only endpoint diagnostic execution
- persisted playbook state.

Required capability gap:
- governed **DRMM automation execution-history search** by device UID/hostname, time range, component, operator/requester, status, and job ID, returning approval/correlation evidence where available. This is required for autonomous attribution when the job ID is not already known.

---

## 21. Acceptance Test

### Primary production case
**Ticket:** `T20260919.0037`
**Device:** `Atomic-50291`
**Detection:** Datto EDR High Severity — Windows Event Logs Cleared.

Preserved provider evidence includes:
- user: `NT AUTHORITY\\SYSTEM`;
- process: `wevtutil.exe`;
- command: `C:\\WINDOWS\\system32\\wevtutil.exe cl Security`;
- parent: `powershell.exe`;
- grandparent: `cagservice.exe`;
- event time: 2026-09-19 18:45:15 UTC;
- MITRE ATT&CK: T1070.001.

This proves a strong DRMM-origin signal, but the acceptance test must **not** classify it authorized until the exact AOT execution/job and approval are matched.

### Secondary comparison case
**Ticket:** `T20260919.0039` / `SET-01` — Windows Security Log Cleared / Event ID 1102.

Use it to prove the playbook handles a provider ticket that contains Event ID 1102/SYSTEM evidence but less direct process ancestry.

Acceptance must prove:
1. trigger detection;
2. endpoint/event association;
3. evidence preservation;
4. process ancestry interpretation;
5. exact AOT job/approval correlation or correct attribution blocking;
6. IOC/security correlation;
7. current Security-log health verification;
8. correct distinction between authorized AOT activity and AOT-origin unexpected behavior;
9. suspicious/unattributed escalation;
10. ticket documentation;
11. no destructive action;
12. correct closure/handoff behavior.

---

## 22. Section Goal Closure

Section Goal remains open until:
- the Atomic-50291 acceptance case is correlated to exact AOT execution evidence or correctly remains attribution-blocked;
- the SET-01 comparison case is processed through the same logic;
- the DRMM execution-history search gap is implemented or explicitly accepted as an autonomy blocker;
- ticket documentation/closure and escalation behavior are verified;
- Grafana/Project Jason security-playbook visibility is updated where applicable;
- the playbook is reviewed for autonomy eligibility.

This playbook does not grant authority to clear logs, contain endpoints, disable accounts, or perform other security remediation.
