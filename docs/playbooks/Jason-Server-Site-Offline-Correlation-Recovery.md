# Jason Playbook: Server / Site Offline Correlation & Recovery

Version: 0.3.0-design
Playbook ID: server_site_offline
Status: Owner-approved design direction; source-controlled draft only. No autonomous remediation authority is granted by this document.

## Standard Manifest

playbook:
  id: server_site_offline
  name: Jason - Server / Site Offline Correlation & Recovery
  version: 0.3.0-design
  owner: AOT IT Operations
  target_type: ticket
  trigger:
    provider: Autotask/Datto RMM
    match: endpoint/server offline or site-connectivity monitoring condition
  ownership:
    while_open: Jason
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 0
  recheck:
    enabled: true
    cadence: rapid incident clock for probable site outage; otherwise 10 minutes during ordinary endpoint confirmation, then policy-driven
    stale_after: role-dependent
  verification:
    authoritative_source: multi-source availability evidence plus originating monitor
    success_condition: exact endpoint/site condition is authoritatively healthy or correctly classified for human review
  completion:
    terminal_disposition: Complete or Help Desk I / Human Review
  autonomy:
    allowed_branches:
      - identify
      - correlate
      - classify
      - wait_and_recheck
      - close_verified_recovered
    approval_bound_branches: []
    disruptive_branches:
      - reboot
      - shutdown
      - network_adapter_reset
      - firewall_or_switch_restart
      - ISP_equipment_restart

## 1. Section Goal

Goal: Jason must determine whether an offline alert represents a single endpoint problem, an RMM/monitoring problem, a partial network problem, or a broader site outage; correlate related devices and tickets; verify natural recovery; and automatically close only when authoritative evidence proves recovery.

Success means:
- the exact ticket, client, site, endpoint, and CI are identified;
- device availability is determined from multiple independent sources where available;
- device_online and device_on_site are evaluated separately;
- only an online endpoint whose current network evidence confirms it is physically/logically on the affected site may act as a site-health witness;
- successful governed live command execution with fresh output from a confirmed on-site fixed server is strong affirmative evidence that the site is up and should immediately eliminate the broad site-down branch for that server's reachable network path;
- roaming laptops and remote users cannot falsely prove the office is healthy;
- Jason uses DRMM, Datto Endpoint Backup, VulScan, Datto EDR/AV, and network evidence where available without treating any one signal as absolute;
- neighboring managed endpoints and the local gateway are used to distinguish endpoint, segment, and site failures;
- recovered alerts are independently verified before completion;
- site-wide incidents are correlated rather than treated as unrelated endpoint failures;
- no disruptive recovery action occurs without separate explicit authority;
- a probable site outage produces a useful preliminary incident notification quickly, without waiting for the entire diagnostic workflow to finish;
- continued investigation enriches the incident after notification rather than delaying awareness.

## 2. Trigger

Primary triggers:
- Autotask/DRMM ticket reports a managed Windows endpoint or server offline;
- DRMM server/site monitoring condition indicates loss of contact;
- multiple same-site devices become unavailable within a bounded correlation window;
- a technician requests availability/site correlation for a named client/site/device.

Jason must confirm the current condition rather than assuming the trigger remains true.

## 2A. Ticket Augmentation Mode

Offline-ticket context augmentation is implemented as a separate lightweight playbook:
`offline_ticket_context_augmentation@0.1.0`.

It may run on an open technician-owned offline ticket before this full incident playbook takes ownership. Its purpose is to answer a fast contextual question:

**Does current evidence say the site is up, likely up, likely down, partially affected, or still unknown?**

The augmentation path:
- does not move the ticket;
- does not change status/work type/resource assignment;
- does not consume an active-work slot;
- uses the shared availability/site-presence model;
- may use one fresh governed read-only command on a fixed same-site server as the strongest site-up witness;
- treats failed PC ping as inconclusive;
- excludes mobile/roaming laptops from site-health proof;
- may use DEB as independent target-availability corroboration;
- writes only a duplicate-suppressed internal note when evidence changes.

If augmentation produces `site_likely_down` or `partial_or_segment_outage_suspected`, this full playbook may independently admit the event and enter its rapid outage clock.

## 3. Scope and Boundaries

### In Scope
- Autotask ticket/site/CI correlation;
- DRMM endpoint status and last-seen evidence;
- Datto Endpoint Backup asset status/last-online evidence when available;
- VulScan last-contact/recent-scan evidence when available;
- Datto EDR/AV endpoint last-contact evidence when available;
- read-only network probes from an approved same-site managed endpoint;
- public-IP reachability tests where meaningful;
- known managed neighboring endpoint correlation;
- ticket correlation, waiting, verification, closure, and human handoff.

### Out of Scope
- reboot/shutdown;
- service restart that could disrupt active work;
- network-adapter reset;
- firewall, switch, access point, modem, ONT, or ISP-device restart;
- arbitrary subnet scanning;
- cross-client probing;
- assuming an online laptop is physically at the office;
- direct provider access outside Jason governance.

Preserve direct_provider_access=false, Central Orchestrator authority, exact requester grants, client/provider isolation, audit, disruption controls, and bounded attempts.

## 4. Initial Identification

1. Identify exact Autotask ticket and client.
2. Run the global CI/device-association gate.
3. Resolve the exact DRMM endpoint and site.
4. Record device class/role where known: server, desktop, laptop, hypervisor, network appliance, or unknown.
5. Record current DRMM state, last-seen time, current private IP, public/external IP, and gateway when available.
6. Search for related same-site offline tickets/alerts within the correlation window.
7. Resolve known managed peer devices at the same site/subnet.
8. Before substantive ticket-specific diagnostics, complete the global work-start lifecycle: Jason queue, In Progress, Remote Support, authoritative readback.
9. If ticket/device/site identity is ambiguous, set state=identification_blocked and stop.

## 5. Expected State

Healthy endpoint:
- at least one authoritative or corroborating provider indicates current/recent check-in;
- network evidence is consistent with the endpoint's expected location and role;
- the originating offline monitor is clear or current evidence proves the endpoint has recovered.

Healthy site:
- one or more confirmed on-site witnesses are available and/or authoritative site/network evidence is healthy;
- same-site infrastructure/network path is available;
- no correlated multi-device outage remains unresolved.

Important:
device_online does not imply device_on_site.
device_online does not, by itself, prove site_health.
A site witness requires online=true AND site_presence_confirmed=true.

## 6. State Model

detected -> owned -> identified -> availability_collecting -> site_presence_classifying -> correlating -> classified

Classification states:
- endpoint_online_rmm_unhealthy
- endpoint_online_remote
- single_endpoint_offline
- probable_local_port_or_nic_issue
- probable_segment_or_vlan_issue
- probable_site_connectivity_outage
- probable_site_power_outage
- stale_or_retired_asset
- recovered
- evidence_conflict
- human_review

Waiting states:
- waiting_initial_10m
- waiting_device_recovery
- waiting_site_recovery
- waiting_provider_propagation

Persist:
- provider availability observations and timestamps;
- current network identity;
- site-presence confidence and evidence;
- selected probe endpoint;
- peer-device sample;
- correlated ticket/alert IDs;
- next recheck;
- evidence fingerprint.

## 7. Diagnostic Workflow

### Step 1: Multi-source endpoint availability

Purpose:
Determine whether the operating system/device is probably running.

Evidence sources, where available:
- DRMM current status and last seen;
- Datto Endpoint Backup asset status / last online;
- VulScan recent contact or scan evidence;
- Datto EDR/AV last endpoint contact;
- current ping response from a valid network vantage point.

Decision:
- Multiple recent provider signals -> endpoint_online=true.
- DRMM offline but another current agent/provider is communicating -> classify likely RMM/monitoring issue and continue endpoint-specific diagnosis.
- All available provider signals stale/offline -> continue network/site correlation.
- Conflicting evidence -> preserve evidence_conflict rather than guessing.

No single source is universally authoritative for physical power state.

### Step 2: Establish site presence before using an endpoint as a witness

Purpose:
Prevent a roaming laptop or remote user from falsely proving the office is healthy.

Evidence:
- current external/public IP matches the documented/observed site WAN IP;
- current private IP/subnet matches the site's expected LAN;
- current default gateway matches known same-site evidence;
- DRMM/IT Glue site assignment;
- contemporaneous same-public-IP evidence from other known on-site devices;
- network-device/firewall evidence when available.

Classification:
- site_presence_confirmed
- site_presence_probable
- site_presence_not_confirmed
- site_presence_remote
- site_presence_unknown

Rules:
- An endpoint with a different current public IP from the site is not a site witness.
- A laptop may be online and healthy while the office is completely down.
- Historical site assignment alone is insufficient when current network identity contradicts it.
- Only confirmed on-site endpoints count as strong site-health witnesses.

### Step 3: Prefer a confirmed on-site fixed server as an active witness

Purpose:
Use successful governed command execution as stronger site-health evidence than passive provider status or ICMP.

If Jason can execute a read-only governed command on a confirmed on-site fixed server and retrieve fresh output:
- server_online = true;
- device_on_site = true, assuming current site-presence evidence remains valid;
- site_witness = true;
- the broad site-down branch is rejected for the network path that reaches that server;
- use that server as the preferred local vantage point for gateway, peer, and target probes.

This proves the site is not completely offline, but it does not prove every VLAN, switch, ISP path, or network segment is healthy. Continue localization if the original affected device remains unreachable.

Do not use a cloud-hosted server, colocated server, remote server, or server whose site presence is uncertain as proof that the physical client site is up.

### Step 4: Select a valid network vantage point

Purpose:
Run read-only local reachability tests from a machine actually on the affected network.

Preferred probe:
- known-online;
- same client;
- site_presence_confirmed;
- same site and preferably same subnet/VLAN;
- stable desktop/server preferred over roaming laptop;
- no current outage ambiguity.

If no valid same-site probe exists, do not invent local ping evidence. Continue with provider/site evidence and classify confidence accordingly.

### Step 5: Target and infrastructure probes

From an approved same-site probe, test:
- affected endpoint IP if known/current;
- endpoint hostname when local name resolution is meaningful;
- default gateway;
- known managed peers on the same subnet/site;
- public Internet target such as 8.8.8.8 when appropriate;
- DNS resolution separately when appropriate.

Ping failure alone is not proof of offline because ICMP may be blocked.

### Step 6: Known neighboring endpoint correlation

Use known managed peers from DRMM/IT Glue/provider inventory before considering adjacent-address probing.

Preferred evidence:
- peer A current provider state;
- peer B current provider state;
- peer C current provider state;
- peer current IP/public IP/site presence;
- local ping only when a valid site probe exists.

Optional adjacent-IP probing may be used only when:
- the subnet/client boundary is proven;
- the address range is explicitly bounded;
- it is read-only;
- it is needed to answer a specific network question;
- it does not become broad discovery/scanning.

### Step 7: Classify outage scope

Examples:

Confirmed on-site fixed server accepts a governed read-only command and returns fresh output:
-> broad site_down=false for that reachable path; use the server as the preferred probe source and localize the remaining issue.

Target responds locally, provider/RMM says offline:
-> endpoint_online_rmm_unhealthy.

Target fails, gateway responds, several confirmed same-site peers respond:
-> single_endpoint_offline or probable local port/NIC/host condition.

Target and multiple same-segment peers fail, gateway responds:
-> probable_segment_or_vlan_issue.

Target, peers, and gateway fail from a valid same-site probe:
-> probable site network/power issue, subject to probe-path sanity.

No same-site probe, multiple DRMM/DEB/EDR sources show same-site devices disappear together:
-> probable_site_connectivity_outage with confidence based on evidence.

Only roaming laptops remain online:
-> do not use them as site-health witnesses.

## 8. Decision Gates

Before any conclusion:
1. exact client/site/device identity proven;
2. timestamps normalized to the same incident window;
3. remote/mobile endpoints excluded as site witnesses unless current site presence is confirmed;
4. public-IP/private-subnet evidence checked where available;
5. ping interpretation accounts for ICMP filtering;
6. known peers preferred over arbitrary scanning;
7. cross-client evidence excluded;
8. outage classification includes confidence/evidence, not just a label.

## 9. Remediation

This v0.1 design is primarily correlation, diagnosis, waiting, and verified closure.

Autonomous safe actions:
- read-only provider checks;
- read-only approved ping/network probes;
- correlation of tickets/alerts/devices;
- waiting/rechecks;
- verified recovered closure.

No autonomous disruptive remediation is granted.

Endpoint-specific RMM-agent repair may later call a separate approved playbook rather than being embedded here.

Network/site remediation requiring restart, failover, adapter reset, equipment reboot, or other disruption is human-review/approval bound.

### Step 8: Rapid outage clock and early incident communication

Purpose:
Prevent a site outage from sitting in a long diagnostic state while technicians or clients are waiting for awareness.

A site outage is time-sensitive. Jason must separate:
- time to first useful incident classification;
- time to full diagnosis;
- time to remediation.

Jason must not wait for the full playbook to finish before surfacing a probable site outage.

Default design clock:
- T+0: trigger received; immediately begin identity, peer correlation, and multi-source availability checks.
- By approximately T+2 minutes: if evidence already shows multiple same-site fixed/infrastructure endpoints unavailable, publish a preliminary AOT incident update such as "Probable site outage - investigation in progress" with the evidence known so far.
- By approximately T+5 minutes: if the probable site-outage classification remains, route/escalate it as an active site incident with the current best classification, affected-device count, known site-presence evidence, and next diagnostic step.
- T+10 minutes: perform the ordinary confirmation/recovery recheck, but do not delay the earlier incident notification waiting for this timer.

The timer is an operational response target, not proof of root cause. Jason may state that classification is preliminary while continuing diagnostics.

Communication rules:
- Never use "Jason isn't done yet" as the operative status for a probable site outage.
- State what is known now, the current probable scope, what Jason is checking next, and whether human action is required.
- Technician/AOT notification may occur before final root cause is known.
- Client-facing notification requires an approved external communication workflow/template; if that authority is unavailable, notify AOT staff immediately rather than delaying the incident internally.
- If later evidence narrows the event from site outage to a single endpoint or monitoring fault, update the incident classification rather than treating the preliminary notice as an error.
- Early communication does not authorize disruptive remediation.

## 10. Retry Policy

- Ordinary single-endpoint confirmation: one 10-minute wait/recheck cycle unless severity/role requires faster handling.
- Probable site outage: do not wait 10 minutes before notification/escalation; use the rapid outage clock in Step 7.
- Read failures: bounded same-read retry.
- Ping: small bounded sample; no continuous flood.
- No remediation retries in v0.1 because this playbook does not autonomously remediate infrastructure.
- Do not redispatch duplicate probes when a current probe job is active.

## 11. Periodic Rechecks

Initial ordinary endpoint recheck: 10 minutes.

Probable site outages use the rapid outage clock for awareness/escalation first, followed by the 10-minute confirmation/recovery recheck.

Recheck:
- originating monitor;
- DRMM state;
- DEB/EDR/VulScan freshness where available;
- site-presence evidence;
- correlated peers/site devices;
- current site/network evidence.

Unchanged polling updates persisted state only. Do not create repeated ticket notes.

Waiting releases the active-work slot while retaining declared queue ownership.

## 12. Aging / Stale Condition

Role-aware aging:
- server/infrastructure endpoint: short tolerance; unresolved offline condition escalates quickly;
- fixed desktop: moderate tolerance based on business hours/site context;
- laptop/mobile endpoint: longer tolerance and explicit remote/off-site possibility.

After stale threshold investigate:
- retired/replaced device;
- renamed/reimaged endpoint;
- duplicate CI;
- stale DRMM object;
- intentionally powered-off equipment;
- remote/mobile use;
- site closure/business-hours pattern;
- persistent local network fault.

Do not indefinitely recheck a lifecycle problem.

## 13. Dependency Handling

Potential dependencies:
- current site WAN/public IP reference;
- reliable CI/device/site mapping;
- DEB asset mapping;
- EDR endpoint mapping;
- VulScan freshness evidence;
- approved read-only site probe capability;
- documented network/subnet/gateway data.

Missing dependencies reduce confidence or route to Human Review. Never borrow network values from another client.

## 14. Documentation Requirements

Technician-scannable note order:
1. STATUS
2. NEXT STEP / ACTION REQUIRED
3. WHEN / ESCALATION
4. KEY EVIDENCE
5. WHAT JASON DID
6. CHANGES MADE
7. JASON STATE

Key evidence should include only what drives the classification:
- DRMM status/last seen;
- DEB/EDR/VulScan corroboration when relevant;
- current external IP/private IP/gateway;
- site-presence classification;
- probe source;
- target/gateway/peer results;
- number of correlated same-site devices;
- resulting classification and confidence.

Do not paste raw repetitive ping output.

## 15. Failure Handling

Fail closed/document:
- ambiguous endpoint/site;
- no trustworthy site presence evidence;
- no valid probe vantage point;
- provider read failure;
- conflicting provider timestamps;
- stale provider objects;
- ping capability unavailable;
- peer/site mapping unavailable;
- cross-client ambiguity.

Absence of one source does not invalidate other sources, but Jason must state confidence appropriately.

## 16. Escalation Criteria

Escalate / Human Review when:
- critical server remains offline after initial confirmation;
- multiple same-site systems indicate likely site outage; this condition is time-sensitive and must enter the rapid outage clock rather than wait for full diagnostics;
- network/power infrastructure action is required;
- evidence conflicts materially;
- endpoint/site identity is uncertain;
- outage persists beyond role-aware threshold;
- only disruptive remediation remains;
- no valid evidence can distinguish endpoint versus site failure.

## 17. Verification

Recovered endpoint:
- current provider evidence shows endpoint available;
- originating monitor clears or authoritative current state proves recovery;
- if RMM alone was stale, another source and/or local network evidence confirms the device was actually online;
- current site presence is re-evaluated before using the endpoint as site evidence.

Recovered site:
- confirmed on-site witnesses return;
- gateway/site/network evidence returns where available;
- correlated same-site alerts clear or devices recover;
- remote laptops alone cannot satisfy site recovery.

## 18. Completion Criteria

Complete only when:
1. exact object/site identity is proven;
2. outage scope was classified;
3. required waiting/rechecks completed;
4. authoritative current evidence establishes recovery or a valid non-incident/stale classification;
5. no unresolved critical correlated outage remains;
6. documentation is complete;
7. final ticket disposition succeeds and is read back.

## 19. Final Resolution Note

Include:
- original trigger;
- affected device/site;
- outage classification;
- provider availability evidence;
- site-presence result;
- peer/site correlation;
- network probe summary;
- recovery time;
- final authoritative verification;
- final disposition.

## 20. Required Capabilities

Existing/likely reusable:
- service.ticket.search/read/update/note.create
- service.configuration.search/read
- endpoint.device.search/read
- endpoint.alert.search/history
- backup.endpoint.asset.search/read
- endpoint.security.status.read where available
- persisted playbook state and scheduled rechecks

Implementation gaps to bind explicitly:
- VulScan provider freshness/read capability suitable for availability corroboration;
- governed read-only local network probe/ping capability;
- current public-IP/gateway/subnet evidence normalized into the availability model;
- reusable site-presence/site-witness classifier;
- cross-ticket/site correlation service.

No broader shell/provider access should be added solely for convenience.

## 21. Acceptance Test

Use a controlled AOT/client test with:
- one fixed on-site endpoint;
- one same-site peer;
- one laptop intentionally taken off-site or otherwise proven remote;
- known site WAN/public IP and gateway;
- a safe simulated/stale DRMM condition where possible.

Prove:
1. correct trigger and CI association;
2. DRMM + DEB corroboration;
3. VulScan/EDR corroboration when available;
4. remote laptop remains online but is rejected as a site witness;
5. confirmed on-site endpoint is accepted as a site witness;
6. target ping success does not override site-presence validation;
7. target ping failure with healthy gateway/peers classifies endpoint-local;
8. multiple peer failures correlate toward segment/site outage;
10. gateway/site evidence changes outage classification;
11. ICMP-blocked endpoint is not falsely declared powered off;
12. probable site outage produces an early preliminary incident update without waiting for the 10-minute recheck;
13. the early update contains current evidence/scope/next step rather than "Jason isn't done yet";
14. unchanged 10-minute recheck creates no duplicate note;
15. recovered endpoint completes only after authoritative verification;
16. remote endpoints alone cannot satisfy site recovery;
17. no disruptive action occurs;
18. terminal ticket write/readback succeeds.

## 22. Section Goal Closure

Close after:
- playbook source is implemented and registered;
- shared availability/site-presence model is implemented;
- provider capability gaps are bound explicitly;
- controlled test proves remote-laptop rejection and valid site-witness behavior;
- peer/site correlation works;
- rapid site-outage notification/escalation timing is proven;
- 10-minute wait/recheck and duplicate suppression are proven;
- recovered closure is proven;
- Grafana/Project Jason status is updated;
- known limitations are documented.

## 23. Autonomous Execution Eligibility and Owner Review

Owner design approval: person-al
Design approval date: 2026-09-30

Approved design principles:
- device_online and device_on_site are separate facts;
- only online + site_presence_confirmed may serve as a strong site witness;
- remote/roaming laptops must not prove office health;
- multi-source availability evidence is preferred to DRMM-only status;
- known managed peers are preferred to blind subnet scanning;
- read-only ping/network probes are diagnostic evidence, not remediation;
- probable site outages require early useful communication/escalation before full diagnostics complete.

This design approval does not by itself grant unattended production execution authority. Autonomous branches require source-controlled implementation, acceptance evidence, and exact durable promotion under Jason governance.
