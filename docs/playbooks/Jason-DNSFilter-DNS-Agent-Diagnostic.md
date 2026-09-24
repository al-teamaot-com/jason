# Jason Playbook: DNSFilter / DNS Agent Diagnostic

## 1. Section Goal

**Goal:** Allow Jason to investigate and repair routine Windows DNSFilter / DNS Agent deployment-health alerts autonomously: prove the endpoint should have DNSFilter, verify installation, install the approved client when it is missing, inspect both DNSFilter Windows services, review Windows and DNSFilter operational logs, test DNS resolution/filtering, verify recovery, and document the result. Higher-risk actions remain separately governed.

**Success means:**
- exact ticket/client/device/alert identity is proven;
- endpoint availability is checked before diagnostics;
- service/install/version/event/DNSFilter-log/DNS evidence can be collected without per-run approval;
- if DNSFilter is required but genuinely missing, Jason can run the exact approved `Install DNSFilter AOT Ver 08262024` component after all install gates pass;
- both the filtering service and Service Manager are verified after install and during diagnostics;
- healthy/stale alerts can be resolved through the governed native alert path;
- one consolidated Autotask note summarizes each work session;
- uninstall, DNS/NIC changes, registry modification, disabling protection, and reboot remain outside this playbook.

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
- read-only DNSFilter filtering-service, Service Manager, and auto-update log review;
- read-only DNS configuration and DNS resolution/filtering tests;
- approved installation with `Install DNSFilter AOT Ver 08262024` when the endpoint is eligible, DNSFilter is required, installation is genuinely absent, and required site configuration is proven;
- current DNSFilter vendor release/known-issue research when relevant;
- exact DRMM alert resolution after healthy-state verification.

### Out of Scope
- starting/stopping/restarting DNS Agent;
- changing startup type;
- changing DNS servers/NIC configuration;
- adapter reset;
- `ipconfig /flushdns` as remediation;
- arbitrary/manual installer execution outside the approved install component;
- automatic reinstall/repair-over-install when an existing installation is corrupt or partially present;
- uninstall;
- registry modification;
- disabling DNSFilter;
- reboot/shutdown;
- collection of browsing/query history;
- disclosure of DNSFilter site/registration keys.

Preserve all Jason governance, including Central Orchestrator authority and `direct_provider_access=false`.

**Owner policy decision — 2026-09-24:** this workflow is approved for autonomous routine diagnosis and missing-agent installation once the dedicated diagnostic component is deployed/standing-approved and the existing `Install DNSFilter AOT Ver 08262024` component has passed the controlled acceptance gates below. This does not authorize uninstall, DNS/NIC changes, reboot, or repair-over-install of a corrupt existing client.

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
- filtering service exists (`DNS Agent` for whitelabel/MSP or `DNSFilter Agent` for branded installs);
- for agent versions that include it, Service Manager exists (`DNS Agent Service Manager` / `DNSFilter Agent Service Manager`);
- required DNSFilter services are `Running`;
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

`diagnosing -> agent_missing -> installing -> verifying`

`diagnosing -> agent_corrupt_or_partial -> remediation_required`

`diagnosing -> dns_resolution_failure -> remediation_required`

`diagnosing -> version_or_known_issue -> remediation_required`

`diagnosing -> evidence_inconclusive -> escalated`

Persist ticket ID, alert UID, device UID, CI ID, whether DNSFilter is required, install-state proof, filtering-service state, Service Manager state, installed version, relevant Windows/DNSFilter log evidence, diagnostic/install job IDs, DNS/filtering test result, classification, and next state.

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
- detect branded vs whitelabel naming;
- check filtering service: `DNS Agent` or `DNSFilter Agent`;
- check Service Manager where applicable: `DNS Agent Service Manager` or `DNSFilter Agent Service Manager`;
- if CyberSight is present, report its service state but do not treat it as required unless policy says it is enabled;
- for each discovered service return Name, DisplayName, State, StartMode, StartName, PathName, ExitCode, ServiceSpecificExitCode, ProcessId.

DNSFilter documentation states that agent v2.1+ includes a Service Manager that monitors the filtering service and can restart it after an unexpected stop, so both services must be evaluated together.

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

**Recent Windows events**
- previous 6 hours by default, extend to 24 hours when needed;
- System Service Control Manager entries referencing DNS Agent/DNSFilter;
- relevant Application errors from DNSFilter/DNS Agent executables/providers;
- newest first, bounded output;
- timestamp, event ID, provider, level, short error/message.

**DNSFilter operational logs**
- discover version-appropriate log roots instead of assuming one fixed path;
- v3.x candidates include `%ProgramData%\\DNSFilter, Inc\\Logs` and whitelabel ProgramData variants;
- legacy candidates include install-directory log folders such as `C:\\Program Files\\DNSFilter Agent\\logs` and `C:\\Program Files\\DNS Agent\\logs`;
- inspect bounded recent entries from filtering-service/agent-operations logs, Service Manager logs, and auto-update logs;
- return filenames, modification times, and recent Warning/Error/Exception/registration/update/service-failure lines with bounded context;
- do **not** return raw DNS query logs in routine diagnostics because they may contain user browsing/query history;
- do not change log level or enable DEBUG automatically.

**DNS state**
- active adapters;
- configured DNS servers;
- DNS Client service state;
- one bounded normal DNS lookup against a neutral hostname;
- run `nslookup -type=txt debug.dnsfilter.com` or equivalent read-only DNSFilter diagnostic query and report whether expected DNSFilter diagnostic fields are returned, without recording unrelated query history;
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
- install/upgrade/uninstall inside the diagnostic component itself;
- reboot;
- disable protection;
- collect DNS query history or secret registration values.

### Step 4 — Required-installation gate and approved install path

Before installing, prove all of the following:
- endpoint is a supported Windows client OS/role for the DNSFilter Roaming Client;
- client/site policy requires the Roaming Client on this endpoint;
- the device is not a Windows Server, domain controller, shared desktop/RDS host, or other unsupported role unless DNSFilter support documentation explicitly says otherwise;
- installation is genuinely absent, not merely hidden from DRMM inventory;
- no existing filtering service, Service Manager, install registry evidence, binary, or active DNSFilter client is found;
- required DNSFilter site configuration/secret is available to the existing component through the approved Datto/site-variable mechanism without exposing the secret;
- endpoint has network connectivity and required runtime prerequisites.

If all gates pass:
- run exact component `Install DNSFilter AOT Ver 08262024`;
- poll the same job to terminal state;
- do not redispatch while active;
- then rerun the diagnostic component for authoritative verification.

If install evidence is partial/corrupt or an existing client is present but broken:
- do **not** blindly reinstall over it;
- set `agent_corrupt_or_partial -> remediation_required` and escalate/seek the separately authorized repair path.

DNSFilter currently documents the Windows Roaming Client for Windows 10+ client systems and states it is not supported on Windows Server/shared desktop environments; v3.x also requires .NET 8 runtime prerequisites. Treat those as hard install gates.

### Step 5 — Vendor evidence when relevant

If version/behavior suggests a client defect, consult current official DNSFilter release/known-issue material first. Compare the installed version to current production and check for applicable DNS/VPN/IPv6/config-sync/stability fixes.

Do not upgrade solely because a newer version exists.

### Step 6 — Classify

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

**Agent missing**
- DNSFilter is required;
- supported client endpoint;
- service/install/binary evidence all prove it is absent.
- Run the approved install component, then verify both services/logs/DNS.

**Agent corrupt/partial**
- mixed evidence: service exists but executable/registry/install metadata is broken or inconsistent.
- `remediation_required`; do not blind reinstall.

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

### Missing-agent install
Existing component:
`Install DNSFilter AOT Ver 08262024`

Classification: modifying, bounded installation.

**Owner-approved workflow:** eligible for autonomous use only when all Step 4 install gates pass and after controlled acceptance proves the exact component behaves safely. The component must use the approved client/site configuration source and must never expose the site secret in output or ticket notes.

After install, Jason must verify:
- filtering service exists and is Running;
- Service Manager exists/runs when applicable;
- installed version is identified;
- DNSFilter operational logs do not show unresolved install/registration/service failure;
- normal DNS resolution succeeds;
- DNSFilter diagnostic TXT lookup returns expected filtering evidence;
- exact DRMM alert clears or can be safely resolved.

### Existing-but-broken client
Do not automatically reinstall over a partial/corrupt installation under this playbook. Escalate to a separately approved repair/reinstall path.

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
- executable/install appears corrupt or partially installed;
- endpoint is an unsupported DNSFilter Roaming Client OS/role;
- DNS remains broken while the service is running;
- remediation needs restart/reinstall/uninstall/DNS changes/reboot without authority;
- vendor known issue materially matches the endpoint;
- two bounded diagnostic attempts fail.

---

## 17. Verification

After install or any separately authorized remediation, require:
- endpoint online;
- filtering service `Running`;
- Service Manager `Running` where applicable;
- required services remain running through a short observation interval;
- normal DNS lookup succeeds;
- DNSFilter diagnostic TXT lookup shows expected DNSFilter handling;
- recent DNSFilter agent/Service Manager logs show no unresolved installation/registration/service-start failure;
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
- create `DNSFilter / DNS Agent Diagnostic [WIN] AOT` with both-service checks, Windows events, DNSFilter operational-log parsing, DNS configuration, and DNSFilter diagnostic TXT lookup;
- review it as read-only/non-disruptive;
- register it in Jason's durable Datto component approval registry after acceptance;
- review and acceptance-test exact existing installer `Install DNSFilter AOT Ver 08262024` (UID `3a3f04c4-3f69-45aa-9260-d8146958a24b`) for the gated missing-agent path before granting standing use under this playbook.

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
4. filtering service + Service Manager/install/Windows-event/DNSFilter-log/DNS evidence is returned;
5. exact job is polled without duplicate dispatch;
6. one consolidated ticket note is written;
7. incident is correctly classified;
8. if the agent is genuinely missing on a supported/required endpoint, the exact approved installer runs once and is verified rather than repeatedly dispatched;
9. after install, both services, relevant logs, DNS resolution/filtering, and alert state are verified;
10. healthy case resolves exact alert;
11. partial/corrupt install stops at `remediation_required` rather than blind reinstall;
12. audit records bind exact diagnostic and installer component identities/fingerprints.

---

## 22. Section Goal Closure

Close only after:
- dedicated diagnostic component is created in Datto RMM;
- read-only diagnostic behavior is reviewed;
- diagnostic component is standing-approved in Jason's durable registry;
- exact `Install DNSFilter AOT Ver 08262024` component passes controlled gated-install acceptance and is approved for the playbook's missing-agent path;
- AVMAC-1077 acceptance succeeds;
- note quality and retry behavior are verified;
- limitations/TODOs are documented;
- Project Jason/Grafana tracking is updated.

Until then, the playbook design is owner-approved, but autonomous diagnostic execution remains capability-blocked.
