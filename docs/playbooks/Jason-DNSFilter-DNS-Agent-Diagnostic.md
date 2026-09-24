# Jason Playbook: DNSFilter / DNS Agent Diagnostic

## 1. Section Goal

**Goal:** Allow Jason to investigate Windows DNSFilter / DNS Agent alerts autonomously with bounded read-only diagnostics, classify the condition, document the result, and stop before any user-impacting remediation unless separately approved.

**Success means:**
- exact ticket/client/device/alert identity is proven;
- endpoint availability is checked before diagnostics;
- service/install/version/event/DNS evidence can be collected without per-run approval;
- healthy/stale alerts can be resolved through the governed native alert path;
- unhealthy cases are classified and handed to an authorized remediation path;
- one consolidated Autotask note summarizes each work session;
- no service restart, reinstall, uninstall, DNS change, or reboot occurs under diagnostic authority.

This Section Goal is complete only after the dedicated diagnostic component is deployed, standing-approved, and acceptance-tested.

---

## 2. Trigger

Apply when:
- ticket/alert references `DNS Agent`, `DNSFilter`, or the Windows Roaming Client;
- DRMM reports `Service 'DNS Agent' isStopped`, service-start failure, agent unavailable, or equivalent DNSFilter health failure;
- a technician explicitly invokes this playbook for a DNSFilter Windows endpoint.

Current monitor example:
- policy: `AOT - Policy DNSFilter Monitor/Resolve`

---

## 3. Scope and Boundaries

### In Scope
- Windows endpoints managed by DRMM;
- ticket/CI/device association;
- endpoint online/offline verification;
- current alert state;
- read-only service discovery;
- read-only install/version/path/registry discovery;
- read-only recent Service Control Manager event review;
- read-only DNS configuration and DNS resolution tests;
- current DNSFilter vendor release/known-issue research when relevant;
- exact DRMM alert resolution after healthy-state verification.

### Out of Scope
- starting/stopping/restarting DNS Agent;
- changing startup type;
- changing DNS servers/NIC configuration;
- adapter reset;
- `ipconfig /flushdns` as remediation;
- install/upgrade/reinstall/uninstall;
- registry modification;
- disabling DNSFilter;
- reboot/shutdown;
- collection of browsing/query history;
- disclosure of DNSFilter site/registration keys.

Preserve all Jason governance, including Central Orchestrator authority and `direct_provider_access=false`.

**Owner policy decision — 2026-09-24:** this diagnostic workflow is approved for autonomous use once its dedicated read-only Datto component is deployed and registered as standing-safe. This approval does not extend to remediation.

---

## 4. Initial Identification

1. Identify exact Autotask ticket and DRMM alert UID.
2. Identify client/site and endpoint.
3. Validate existing CI or run the global device-association gate.
4. Resolve exactly one authoritative DRMM device UID.
5. Confirm the alert is DNSFilter/DNS Agent related.
6. Record alert timestamp, monitor/policy, and any monitor-provided diagnostics/remediation result.
7. If endpoint is online, run the global ticket-work-start lifecycle before substantive diagnostics:
   - queue Jason;
   - status In Progress;
   - Work Type Remote Support;
   - require readback verification.
8. If endpoint is offline, do not claim solely to wait; add a recheck note and set `state = waiting_endpoint`.

If identity is ambiguous: `state = identification_blocked`.

---

## 5. Expected State

Healthy DNSFilter Windows state:
- endpoint online;
- required DNSFilter client installed;
- service associated with display name `DNS Agent` exists;
- service state `Running`;
- startup mode not disabled;
- service executable exists;
- installed version can be identified;
- no unresolved recurring service-start/crash event;
- normal DNS resolution succeeds;
- current DNS configuration is consistent with the active agent mode;
- DRMM DNS Agent monitor is healthy / alert cleared.

The alert alone does not prove the agent is currently unhealthy.

---

## 6. State Model

`identified -> waiting_endpoint -> diagnosing -> healthy_stale_alert -> complete`

`diagnosing -> service_stopped -> remediation_required`

`diagnosing -> service_start_failure -> remediation_required`

`diagnosing -> agent_missing_or_corrupt -> remediation_required`

`diagnosing -> dns_resolution_failure -> remediation_required`

`diagnosing -> version_or_known_issue -> remediation_required`

`diagnosing -> evidence_inconclusive -> escalated`

Persist ticket ID, alert UID, device UID, CI ID, service state, version, relevant event/error evidence, diagnostic job ID, DNS result, classification, and next state.

---

## 7. Diagnostic Workflow

### Step 1 — Current device and alert state

**Reads:** `endpoint.device.read`, `endpoint.alert.search`, `endpoint.alert.history.search`.

- Offline -> `waiting_endpoint`.
- Alert already resolved and endpoint healthy -> verify and close normally.
- Alert open -> continue.

### Step 2 — Native software inventory

Use `endpoint.software.search` for DNSFilter/DNS Agent variants.

Absence from DRMM software inventory is not sufficient proof that DNSFilter is absent.

### Step 3 — Dedicated read-only component

Create:

`DNSFilter / DNS Agent Diagnostic [WIN] AOT`

Standing classification after acceptance:
- read-only;
- non-disruptive;
- eligible for unsupervised approval.

The component must collect only:

**Service state**
- query exact `DNS Agent` first, with DNSFilter-related fallback discovery;
- Name, DisplayName, State, StartMode, StartName, PathName, ExitCode, ServiceSpecificExitCode, ProcessId.

**Install metadata**
- check:
  - `HKLM:\SOFTWARE\DNSFilter\Agent`
  - `HKLM:\SOFTWARE\DNSAgent\Agent`
  - uninstall inventory for DNSFilter/DNS Agent;
- return only non-secret product name/version/install path/product code.

**Binary evidence**
- executable exists;
- file/product version;
- optional Authenticode signature status.

**Recent service events**
- previous 6 hours by default;
- Service Control Manager entries referencing DNS Agent/DNSFilter;
- newest first, bounded output;
- timestamp, event ID, level, short error/message.

**DNS state**
- active adapters;
- configured DNS servers;
- DNS Client service state;
- one bounded normal DNS lookup against a neutral hostname;
- lookup success/failure and elapsed time.

**System context**
- hostname;
- OS/build;
- uptime/last boot;
- pending reboot state if available.

The diagnostic component must never:
- Start/Stop/Restart a service;
- change startup type;
- change NIC/DNS configuration;
- flush DNS;
- modify registry;
- install/upgrade/uninstall;
- reboot;
- disable protection;
- collect DNS query history or secret registration values.

### Step 4 — Vendor evidence when relevant

If version/behavior suggests a client defect, consult current official DNSFilter release/known-issue material first. Compare the installed version to current production and check for applicable DNS/VPN/IPv6/config-sync/stability fixes.

Do not upgrade solely because a newer version exists.

### Step 5 — Classify

**Healthy / stale monitor**
- service running;
- DNS resolution healthy;
- no current failure evidence.
- Verify -> resolve exact DRMM alert -> complete ticket.

**Service stopped**
- service exists but is not running.
- `remediation_required`.

**Service start failure**
- monitor/event evidence shows start attempt failed.
- Capture exact error/event evidence -> `remediation_required`.

**Agent missing/corrupt**
- service absent plus install/binary evidence absent or inconsistent.
- `remediation_required`.

**DNS failure while service runs**
- do not assume restart fixes it;
- inspect DNS configuration/vendor-known issues/network context;
- `remediation_required` or escalate.

**Known affected version**
- document installed/current versions and official vendor evidence;
- recommend bounded upgrade path;
- remediation remains separately governed.

---

## 8. Decision Gates

Before diagnostics:
- exact endpoint proven;
- endpoint online;
- ownership lifecycle succeeded;
- exact dedicated diagnostic component fingerprint is still approved.

Before remediation:
- specific unhealthy condition proven;
- unrelated site/network outage excluded where practical;
- remediation action is covered by separate authority;
- user-impact risk evaluated.

Diagnostic approval is not remediation authority.

---

## 9. Remediation

### Standing-approved diagnostic
`DNSFilter / DNS Agent Diagnostic [WIN] AOT`

Classification: read-only / non-disruptive.

### Service start/restart
Potentially useful but can interrupt DNS.

Classification: modifying / potentially user-impacting.

**Not autonomously approved by this playbook.**

### Install/upgrade
Existing component:
`Install DNSFilter AOT Ver 08262024`

Classification: modifying.

**Not approved by this diagnostic playbook.**

### Uninstall
Existing component:
`Uninstall DNS Filter / DNS Agent AOT Ver 11052025-1`

Classification: destructive/security-control removal.

**Explicit approval required. Never autonomous through this playbook.**

---

## 10. Retry Policy

- Diagnostic component: maximum 2 executions per session only when the first fails for a transient/provider reason.
- Poll the exact job to terminal state; never redispatch while active.
- Never repeat a successful diagnostic just to obtain different output.
- Repeated diagnostic failure -> escalate.

---

## 11. Periodic Rechecks

If endpoint is offline:
- use normal Jason queue cadence;
- each later availability check is documented with one concise recheck note;
- resume from persisted state when online.

If waiting for remediation authority:
- do not rerun identical diagnostics merely because the ticket is still open.

---

## 12. Aging / Stale Condition

If endpoint remains offline >3 business days, investigate retirement/replacement/reimage, CI mismatch, stale DRMM object, or broader connectivity issue.

If DNS Agent stops more than twice in 7 days after verified remediation, treat as recurring:
- review client version;
- vendor known issues;
- VPN/network coexistence;
- endpoint event history;
- escalate to problem investigation rather than repeatedly restarting.

---

## 13. Dependency Handling

Potential dependencies:
- current DNSFilter installer;
- correct client/site registration;
- supported agent version;
- Datto diagnostic component;
- standing component approval.

Never document secret DNSFilter registration/site keys.

If a dependency is missing, search for an existing dependency ticket before creating another.

---

## 14. Documentation Requirements

Use the AOT/Jason session-summary rule:
- one consolidated progress note per work session;
- not one note per command/read;
- a later offline/waiting recheck is a separate note-worthy event.

Minimum note:
- endpoint/alert;
- online/offline state;
- DNS Agent service state/start mode;
- installed version evidence;
- relevant recent SCM error/event evidence;
- DNS resolution result;
- vendor evidence if used;
- job/correlation ID;
- classification;
- remediation performed, if any;
- next step.

Never document secrets or raw browsing/query history.

---

## 15. Failure Handling

Document provider failures, component failures, missing output, ambiguous service identity, corrupt install metadata, inconclusive DNS tests, vendor-evidence gaps, and authority denials.

Failure to collect evidence is not proof that DNSFilter is absent or broken.

---

## 16. Escalation Criteria

Escalate when:
- service/device identity is ambiguous;
- service repeatedly fails;
- executable/install appears corrupt;
- DNS remains broken while the service is running;
- remediation needs restart/reinstall/uninstall/DNS changes/reboot without authority;
- vendor known issue materially matches the endpoint;
- two bounded diagnostic attempts fail.

---

## 17. Verification

After any separately authorized remediation, require:
- endpoint online;
- DNS Agent `Running`;
- service remains running through a short observation interval;
- normal DNS lookup succeeds;
- exact DRMM DNS Agent alert clears or is safely resolved;
- no new matching service failure appears during verification.

A successful component return alone is not resolution proof.

---

## 18. Completion Criteria

Complete only when:
1. exact endpoint/alert identified;
2. required diagnostics completed;
3. healthy state proven;
4. exact DNSFilter alert cleared/resolved;
5. any remediation is independently verified;
6. consolidated resolution note exists.

Unrelated endpoint issues remain separate unless they directly affect DNSFilter health.

---

## 19. Final Resolution Note

Summarize original condition, classification/root cause, installed version, service/event evidence, remediation, attempts, DNS verification, alert disposition, verification timestamp, and any separate unresolved endpoint issue.

---

## 20. Required Capabilities

Current:
- `service.ticket.search/read/notes.search/note.create/update`
- `service.configuration.search/read`
- `endpoint.device.search/read`
- `endpoint.alert.search/history.search/resolve`
- `endpoint.software.search`
- `automation.component.search/execute`
- `automation.job.read`
- `automation.job.output.read`

Implementation gap:
- create `DNSFilter / DNS Agent Diagnostic [WIN] AOT`;
- review it as read-only/non-disruptive;
- register it in Jason's durable Datto component approval registry after acceptance.

The generic `Run Ad Hoc Command (PowerShell 2-5) [WIN]` must not be promoted to unsupervised authority.

---

## 21. Acceptance Test

**Target**
- Ticket: `T20260924.0021`
- Client: AVMAC llc
- Endpoint: `AVMAC-1077`
- DRMM UID: `a95c92ff-5b53-4813-d39a-638d108b48bf`
- Alert: `ba827896-edfb-4d41-be67-3c176d6cf418`

Known baseline:
- endpoint online;
- Datto AV RunningAndUpToDate;
- reboot_required=False;
- monitor reported: `DNS Agent Cannot start service 'DNS Agent' on computer '.'`;
- native DRMM software search did not return a DNSFilter product;
- generic PowerShell diagnostic correctly stopped at the per-run approval gate.

Acceptance must prove:
1. exact identity;
2. dedicated component runs without per-run approval under standing-safe policy;
3. no modifying/disruptive action occurs;
4. service/install/event/DNS evidence is returned;
5. exact job is polled without duplicate dispatch;
6. one consolidated ticket note is written;
7. incident is correctly classified;
8. healthy case resolves exact alert;
9. unhealthy case stops at `remediation_required`;
10. audit records bind the exact component identity/fingerprint.

---

## 22. Section Goal Closure

Close only after:
- dedicated component is created in Datto RMM;
- read-only behavior is reviewed;
- component is standing-approved in Jason's durable registry;
- AVMAC-1077 acceptance succeeds;
- note quality and retry behavior are verified;
- limitations/TODOs are documented;
- Project Jason/Grafana tracking is updated.

Until then, the playbook design is owner-approved, but autonomous diagnostic execution remains capability-blocked.
