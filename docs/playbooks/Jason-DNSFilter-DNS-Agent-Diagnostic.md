# Jason Playbook: DNSFilter / DNS Agent Diagnostic

## 1. Section Goal

**Goal:** Allow Jason to investigate and repair routine Windows DNSFilter / DNS Agent deployment-health alerts autonomously: prove the endpoint should have DNSFilter, verify installation, install the approved client when it is missing, perform one bounded approved reinstall when the existing client is partial/corrupt or the DNS Agent is stopped/failing or DNSFilter-attributable DNS resolution fails, verify recovery, resolve the exact DRMM alert, complete the Autotask ticket, and document the result. Higher-risk unrelated actions remain separately governed.

**Success means:**
- exact ticket/client/device/alert identity is proven;
- endpoint availability is checked before diagnostics;
- service/install/version/event/DNSFilter-log/DNS evidence can be collected without per-run approval;
- where a client-safe DNSFilter boundary is proven, native DNSFilter reads correlate provider-side organization/network/agent/policy state with endpoint-local DRMM evidence;
- if DNSFilter is required but genuinely missing, Jason can run the exact approved `Install DNSFilter AOT Ver 08262024` component after all install gates pass;
- when a supported endpoint has a partial/corrupt install, service-stopped/start-failure condition, or DNSFilter-attributable DNS failure, Jason can perform one bounded governed uninstall/reinstall cycle after the reinstall gates pass;
- both the filtering service and Service Manager are verified after install/reinstall and during diagnostics;
- once authoritative healthy state is proven, Jason resolves the exact DRMM alert and completes the Autotask ticket automatically without Help Desk review;
- one consolidated Autotask note summarizes each work session;
- arbitrary DNS/NIC changes, registry modification outside the exact approved uninstall/install components, disabling protection outside the bounded reinstall, and reboot remain outside this playbook.

The dedicated diagnostic component milestone is complete as of 2026-09-24: `DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026` is deployed, production acceptance-tested, and standing-approved. DNSFilter client-network isolation work tracked in GitHub #253 is complete. The full Section Goal remains open until the exact install and uninstall/reinstall branches are acceptance-tested and promoted for this bounded autonomous use.

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
- one bounded governed reinstall cycle using the exact approved uninstall then install components when the endpoint is eligible and diagnostics prove a partial/corrupt install, DNS Agent stopped/start failure, or DNSFilter-attributable DNS failure;
- current DNSFilter vendor release/known-issue research when relevant;
- governed native DNSFilter read evidence when a validated client-safe organization/network boundary exists;
- exact DRMM alert resolution and automatic Autotask completion after authoritative healthy-state verification.

### Out of Scope
- starting/stopping/restarting DNS Agent;
- changing startup type;
- changing DNS servers/NIC configuration;
- adapter reset;
- `ipconfig /flushdns` as remediation;
- arbitrary/manual installer execution outside the approved install component;
- reinstall loops or repair-over-install that do not use the exact bounded uninstall/install sequence;
- uninstall for any purpose other than the approved DNSFilter reinstall branch;
- registry modification outside behavior already contained in the exact approved uninstall/install components;
- disabling DNSFilter;
- reboot/shutdown;
- collection of browsing/query history;
- disclosure of DNSFilter site/registration keys;
- native DNSFilter policy/site/agent mutations in the current read-only integration phase;
- using AOT self-company DNSFilter scope as a bypass for a client-scoped ticket.

Preserve all Jason governance, including Central Orchestrator authority and `direct_provider_access=false`.

**Owner policy decisions — 2026-09-24 and 2026-09-28:** routine DNSFilter diagnosis, healthy/stale closure, missing-agent installation, and one bounded reinstall cycle are approved target behaviors once their exact component/capability acceptance gates pass. The dedicated diagnostic component is deployed, acceptance-tested, and standing-approved. The reinstall branch is strictly: exact approved uninstall component once -> exact approved install component once -> full diagnostic verification. This does not authorize arbitrary uninstall, DNS/NIC changes, reboot, repeated reinstall loops, or unrelated native DNSFilter writes.

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
- DRMM DNS Agent monitor is healthy / alert cleared;
- when native DNSFilter client scope is safely available, the provider-side agent/network/policy evidence agrees with the identified endpoint and does not indicate an unprotected/bypassed/stale state inconsistent with local evidence.

The alert alone does not prove the agent is currently unhealthy. A missing native DNSFilter result also does not prove the local client is absent.

---

## 6. State Model

`identified -> waiting_endpoint -> diagnosing -> healthy_stale_alert -> resolving_alert -> completing_ticket -> complete`

`diagnosing -> service_stopped -> reinstalling -> verifying`

`diagnosing -> service_start_failure -> reinstalling -> verifying`

`diagnosing -> agent_missing -> installing -> verifying`

`diagnosing -> agent_corrupt_or_partial -> reinstalling -> verifying`

`diagnosing -> dns_resolution_failure -> reinstalling -> verifying`

`installing -> verifying -> resolving_alert -> completing_ticket -> complete`

`reinstalling -> verifying -> resolving_alert -> completing_ticket -> complete`

`diagnosing -> version_or_known_issue -> remediation_required`

`diagnosing -> evidence_inconclusive -> escalated`

Persist ticket ID, alert UID, device UID, CI ID, whether DNSFilter is required, install-state proof, filtering-service state, Service Manager state, installed version, relevant Windows/DNSFilter log evidence, diagnostic/install job IDs, DNS/filtering test result, native DNSFilter scope/read status, classification, and next state.

---

## 7. Diagnostic Workflow

### Step 1 — Current device and alert state

**Reads:** `endpoint.device.read`, `endpoint.alert.search`, `endpoint.alert.history.search`.

- Offline -> `waiting_endpoint`.
- Alert already resolved and endpoint healthy -> verify and close normally.
- Alert open -> continue.

### Step 1A — Native DNSFilter posture correlation when client isolation is authorized

Use native DNSFilter reads as complementary provider evidence, not as a replacement for endpoint-local diagnostics.

Preferred reads where authorized:
- `dns.protection.organization.read`
- `dns.protection.agent.search`
- `dns.protection.agent.counts.read`
- `dns.protection.site.search`
- `dns.protection.policy.search`
- bounded `dns.protection.agent.version.report` / site-drift or investigation reads only when they answer a specific diagnostic question.

Rules:
- always supply the exact Autotask `company_id`;
- organization/network/site scope must be server-derived and client-isolated;
- for client tickets, never substitute AOT self-company `company_id=0` merely because the client lives inside AOT's DNSFilter MSP organization;
- do not collect broad DNS query history during routine endpoint diagnosis;
- if native provider evidence conflicts with endpoint-local evidence, preserve both and investigate rather than silently choosing one.

Decision:
- exact provider-side agent match -> record agent state/status/version, authorized network/site, policy relationship where returned, and relevant sync/traffic state;
- no provider-side match -> continue local install/service diagnostics; absence from the provider search alone is not proof that the local client is absent;
- multiple or cross-client candidates -> `identification_blocked`;
- `CONNECTOR_AUTHORIZATION_DENIED` or missing safe client boundary -> document native connector evidence as unavailable, continue with the DRMM diagnostic path, and do not weaken isolation. Client-network isolation work tracked in GitHub #253 is complete; any remaining authorization denial must be treated as a live mapping/scope problem rather than bypassed.

**Production evidence — 2026-09-24:** AOT self-company reads succeeded and returned AOT-50282 as an active/protected Windows agent, version 3.3.6, on the AOT Office network. Earlier AVMAC reads failed closed until client network/site isolation was designed and implemented under GitHub #253. Preserve the rule that client execution is bounded to the server-derived authorized network/site set; never map every client broadly to the shared MSP/master organization.

### Step 2 — Native software inventory

Use `endpoint.software.search` for DNSFilter/DNS Agent variants.

Absence from DRMM software inventory is not sufficient proof that DNSFilter is absent.

### Step 3 — Existing standing-safe service and DNS diagnostics

Use the already standing-approved components first where they answer the question cleanly:

- `Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1`
  - run for filtering service (`DNS Agent` / `DNSFilter Agent`);
  - run for Service Manager (`DNS Agent Service Manager` / `DNSFilter Agent Service Manager`) when applicable;
  - captures detailed service properties and relevant Windows event evidence.
- `Get-DNS Settings AOT Ver 06042025-1`
  - capture current endpoint DNS configuration without modification.

These generic standing-safe components may be used immediately under existing policy and should not be duplicated merely because the DNSFilter playbook exists.

### Step 4 — Dedicated DNSFilter-specific read-only component

Use the production-accepted component:

`DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026`

Current UID:
`c3340a58-48d5-457b-bc30-5fd79e5ad8b1`

Standing classification:
- read-only;
- non-disruptive;
- production standing-approved for unsupervised diagnostic use.

**Implementation evidence — 2026-09-24:** the initial AVMAC-1077 acceptance run exposed a PowerShell automatic-variable collision between `$Matches` (created by `-match`) and a script collection named `$matches`. The corrected component renamed the collection to `$logMatches`; the controlled rerun and later production standing-safe rerun both completed successfully with empty stderr. Preserve this regression lesson in future component revisions.

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

### Step 5 — Required-installation gate and approved install path

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
- do not install over the broken client in place;
- if the reinstall gates in Section 9 pass, transition to `reinstalling`;
- perform the exact bounded uninstall/install sequence once;
- then rerun the diagnostic component for authoritative verification;
- if the reinstall branch fails or health cannot be proven, transition to Human Review.

DNSFilter currently documents the Windows Roaming Client for Windows 10+ client systems and states it is not supported on Windows Server/shared desktop environments; v3.x also requires .NET 8 runtime prerequisites. Treat those as hard install gates.

### Step 6 — Vendor evidence when relevant

If version/behavior suggests a client defect, consult current official DNSFilter release/known-issue material first. Compare the installed version to current production and check for applicable DNS/VPN/IPv6/config-sync/stability fixes.

Do not upgrade solely because a newer version exists.

### Step 7 — Classify

**Healthy / stale monitor**
- service running;
- DNS resolution healthy;
- no current failure evidence.
- Verify -> resolve exact DRMM alert -> complete ticket.

**Service stopped**
- service exists but is not running.
- Exclude a broader site/network outage where practical.
- If the endpoint is eligible and DNSFilter is required, transition to `reinstalling`.

**Service start failure**
- monitor/event evidence shows start attempt failed.
- Capture exact error/event evidence.
- If the endpoint is eligible and DNSFilter is required, transition to `reinstalling`.

**Agent missing**
- DNSFilter is required;
- supported client endpoint;
- service/install/binary evidence all prove it is absent.
- Run the approved install component, then verify both services/logs/DNS.

**Agent corrupt/partial**
- mixed evidence: service exists but executable/registry/install metadata is broken or inconsistent.
- Use the bounded reinstall branch; do not perform an in-place repair-over-install.

**DNS failure while service runs**
- inspect DNS configuration/vendor-known issues/network context first;
- exclude a broader site/network/DNS outage where practical;
- when evidence reasonably attributes the failure to the DNSFilter client on an otherwise supported endpoint, use the bounded reinstall branch.

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
`DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026`
UID: `c3340a58-48d5-457b-bc30-5fd79e5ad8b1`

Classification: read-only / non-disruptive.

### Native DNSFilter integration

Current classification: read-only.

Native provider reads may be used to corroborate agent/network/policy posture only when Jason proves an exact safe client boundary. They do not authorize starting/restarting services, reinstalling agents, changing policies, changing networks, resolving unblock requests, or any other DNSFilter mutation.

### Service start/restart
Do not use standalone service restart as the routine remediation branch. The approved target behavior for the qualifying failure states is the bounded reinstall sequence below.

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

### Bounded reinstall for existing broken client

Qualifying conditions:
- `agent_corrupt_or_partial`;
- filtering service stopped;
- documented service-start failure;
- DNSFilter-attributable DNS resolution/filtering failure after broader outage/configuration causes are excluded where practical.

Hard gates:
- supported Windows client endpoint/role;
- DNSFilter is required for this client/site/device;
- endpoint identity and CI are exact;
- endpoint is online;
- required DNSFilter site configuration is available without exposing secrets;
- no broader site/network outage reasonably explains the symptom;
- no reinstall has already been attempted for the same unchanged incident state.

Exact sequence:
1. Run `Uninstall DNS Filter / DNS Agent AOT Ver 11052025-1` once.
2. Poll the exact uninstall job to terminal state and verify DNSFilter is actually absent.
3. Run `Install DNSFilter AOT Ver 08262024` once.
4. Poll the exact install job to terminal state.
5. Rerun `DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026`.
6. Require full Section 17 healthy-state verification.
7. Resolve the exact DRMM alert.
8. Complete the Autotask ticket with readback verification.

Maximum reinstall cycles for one unchanged incident state: **1**.

If uninstall, install, verification, exact-alert resolution, or ticket completion fails, stop and hand off to Help Desk I / Human Review with the technician-scannable evidence and next step. Do not loop the reinstall.

### Uninstall
Existing component:
`Uninstall DNS Filter / DNS Agent AOT Ver 11052025-1`
UID: `449d39cc-e6e8-40a7-afb4-2ffeee069f5d`

Classification: modifying/security-control removal.

Autonomous use is limited to the single bounded reinstall sequence above after controlled acceptance and exact owner promotion. Standalone or unrelated uninstall remains approval-bound.

---

## 10. Retry Policy

- Diagnostic component: maximum 2 executions per session only when the first fails for a transient/provider reason.
- Poll the exact job to terminal state; never redispatch while active.
- Never repeat a successful diagnostic just to obtain different output.
- Repeated diagnostic failure -> escalate.
- Bounded reinstall: maximum 1 uninstall/install cycle for the same unchanged incident state.
- Never redispatch uninstall or install while the exact job is active.
- Failed reinstall or failed post-reinstall verification -> Human Review; no second reinstall loop.

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

Use the standard technician-scannable Jason note layout wherever practical:

- **STATUS** — HEALTHY / REINSTALLING / VERIFIED RESOLVED / HUMAN REVIEW REQUIRED.
- **NEXT STEP** or **ACTION REQUIRED** — state the immediate action at the top.
- **DEVICE / ALERT** — endpoint and exact DRMM alert.
- **KEY EVIDENCE** — service state, installed version, DNS resolution/filtering result, relevant bounded event/log evidence.
- **WHAT JASON DID** — diagnostic/install/reinstall/alert-resolution actions.
- **CHANGES MADE** — explicitly state None when no modifying action occurred.
- **JASON STATE** — persisted playbook state.

For a verified healthy or successfully repaired case, the note should make the terminal action obvious:
- STATUS: VERIFIED RESOLVED
- NEXT STEP: Resolve exact DNSFilter alert and complete ticket automatically

For a failed bounded reinstall:
- STATUS: HUMAN REVIEW REQUIRED
- ACTION REQUIRED: Review failed DNSFilter reinstall/verification evidence
- NEXT STEP: technician action only; Jason must not repeat the reinstall loop

Also include where relevant:
- endpoint online/offline state;
- DNS Agent service state/start mode;
- installed version evidence;
- recent SCM/DNSFilter error evidence;
- DNS resolution result;
- job/correlation IDs;
- exact alert-resolution result and ticket-completion readback.

Never document secrets or raw browsing/query history.

---

## 15. Failure Handling

Document provider failures, component failures, missing output, ambiguous service identity, corrupt install metadata, inconclusive DNS tests, vendor-evidence gaps, and authority denials.

Failure to collect evidence is not proof that DNSFilter is absent or broken.

---

## 16. Escalation Criteria

Escalate when:
- service/device identity is ambiguous;
- endpoint is an unsupported DNSFilter Roaming Client OS/role;
- reinstall gates cannot be proven;
- the single bounded reinstall attempt fails;
- post-reinstall healthy-state verification fails;
- DNS remains broken after the bounded reinstall;
- remediation requires DNS/NIC changes or reboot outside this playbook;
- vendor known issue materially matches the endpoint and the approved reinstall path does not restore health;
- two bounded diagnostic attempts fail.

---

## 17. Verification

After install or bounded reinstall, require:
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

When all verification gates pass:
1. resolve the **exact** DRMM DNSFilter/DNS Agent alert that triggered the work;
2. independently verify the exact alert is resolved/cleared;
3. write the consolidated resolution note;
4. complete the Autotask ticket automatically;
5. independently read back status=Complete.

Do not send a healthy verified ticket to Help Desk for routine review. Human Review is reserved for failed/ambiguous/out-of-scope conditions.

---

## 18. Completion Criteria

Complete automatically when:
1. exact endpoint/alert identified;
2. required diagnostics completed;
3. healthy state proven;
4. exact DNSFilter alert cleared/resolved and readback verified;
5. any install/reinstall remediation is independently verified;
6. consolidated resolution note exists;
7. Autotask completion write succeeds and status=Complete is independently read back.

No Help Desk review is required for a routine healthy/stale case or a successfully verified install/reinstall case.

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
- `dns.protection.organization.read`
- `dns.protection.agent.search`
- `dns.protection.agent.counts.read`
- `dns.protection.site.search`
- `dns.protection.policy.search`
- selected bounded DNSFilter investigation/report reads where a client-safe boundary is proven

Existing standing-safe building blocks:
- `Check Service Detail & Diagnostic [WIN] AOT Ver 12122025-1` for exact service state/details and relevant Windows events;
- `Get-DNS Settings AOT Ver 06042025-1` for current DNS configuration.

Completed implementation milestone:
- `DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026` is deployed;
- controlled AVMAC-1077 acceptance passed after correcting the `$Matches` collision;
- the exact diagnostic component is registered in Jason's durable standing-safe Datto component approval registry and has passed a production autonomous retest.

Remaining implementation gaps:
- acceptance-test exact existing installer `Install DNSFilter AOT Ver 08262024` (UID `3a3f04c4-3f69-45aa-9260-d8146958a24b`) for gated missing-agent and reinstall use;
- acceptance-test exact uninstall component `Uninstall DNS Filter / DNS Agent AOT Ver 11052025-1` (UID `449d39cc-e6e8-40a7-afb4-2ffeee069f5d`) specifically for the single bounded reinstall branch;
- prove the combined uninstall -> install -> diagnostic -> exact-alert resolve -> Autotask Complete lifecycle with readback. DNSFilter client-network isolation work tracked in #253 is complete.

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

Production acceptance results — 2026-09-24:
- dedicated diagnostic UID `c3340a58-48d5-457b-bc30-5fd79e5ad8b1` ran to terminal completion after the `$Matches` regression was corrected;
- filtering service `DNS Agent` was Stopped/Auto;
- `DNS Agent Service Manager` was Running/Auto;
- expected filtering executable `C:\\Program Files\\DNS Agent\\Agent\\DNS Agent.exe` was missing;
- Service Manager binary was present, version 3.7.11.0, with valid signature;
- normal DNS resolution succeeded;
- DNSFilter diagnostic TXT verification failed;
- bounded Windows and DNSFilter operational-log evidence was returned;
- incident classification was correctly `agent_corrupt_or_partial`;
- no blind reinstall, service restart, DNS/NIC change, uninstall, registry modification, or reboot occurred;
- the corrected component was subsequently standing-approved and rerun successfully without per-run approval;
- native DNSFilter client-scoped reads for AVMAC remain blocked pending safe network/site isolation (#253).

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
10. healthy/stale case resolves the exact alert and completes the Autotask ticket automatically without Help Desk review;
11. partial/corrupt install, service stopped/start failure, and DNSFilter-attributable DNS failure enter the single bounded reinstall branch;
12. bounded reinstall runs exact uninstall once, exact install once, then full diagnostic verification;
13. successful reinstall resolves the exact alert and completes the ticket automatically with independent readback;
14. failed reinstall/verification stops at Help Desk I / Human Review and does not loop;
15. audit records bind exact diagnostic, uninstall, installer, alert-resolution, and ticket-completion identities/fingerprints.

---

## 22. Section Goal Closure

Completed as of 2026-09-24:
- dedicated diagnostic component created in Datto RMM;
- read-only diagnostic behavior reviewed;
- diagnostic component standing-approved in Jason's durable registry;
- AVMAC-1077 diagnostic acceptance succeeded;
- partial/corrupt-install classification and fail-closed behavior were proven;
- production autonomous diagnostic rerun succeeded.

Remaining closure gates:
- exact `Install DNSFilter AOT Ver 08262024` component passes controlled acceptance for missing-agent and reinstall use;
- exact uninstall component passes controlled acceptance for the one-cycle reinstall branch;
- the combined reinstall -> verification -> exact-alert resolution -> automatic ticket completion lifecycle passes production acceptance;
- note quality and retry behavior remain verified after remediation acceptance;
- limitations/TODOs are documented;
- Project Jason/Grafana tracking is updated.

Autonomous diagnostic execution is no longer capability-blocked. The new owner-approved target is bounded reinstall plus automatic exact-alert resolution and ticket completion after healthy verification; production authority remains contingent on the exact acceptance/promotion gates above.
