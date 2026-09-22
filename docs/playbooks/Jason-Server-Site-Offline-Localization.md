# Jason Playbook: Server / Site Offline Localization

**Playbook ID:** `server_site_offline_localization`  
**Version:** `1.0.0`  
**Status:** Implemented — diagnostic/localization logic ready; production acceptance evidence recorded  
**Autonomy posture:** Read-only diagnostics may be eligible when the underlying capability is standing-safe. No modifying or disruptive remediation is granted by this playbook.  
**Primary evidence strategy:** DRMM/Kaseya-first, including DRMM SNMP/network-device evidence before direct-vendor integrations.

## 1. Section Goal

**Goal:**  
Determine whether a server-offline, multi-server-offline, or apparent site-offline event is caused by an individual endpoint, hypervisor/vSwitch, server switch/uplink, site LAN, gateway/firewall, WAN/ISP, DNS, Datto RMM/provider path, or another unresolved layer, using bounded read-only evidence before remediation.

**Success means:**
- the affected client/site and assets are correctly identified;
- Jason establishes a timestamped scope of impact rather than trusting one alert;
- live reachability is tested from both inside and, where available, outside the client site;
- DRMM "online" state is corroborated with a current read-only execution when practical;
- the incident is assigned one bounded localization classification or escalated as unknown;
- no disruptive action is taken solely because a device appears offline;
- all meaningful evidence is documented and duplicate alert tickets are correlated.

Do not consider the Section Goal complete until the classification logic has been proven against a controlled production case and known capability gaps are documented.

---

## 2. Trigger

Apply when one or more of the following occurs:
- DRMM device offline alert for a managed server;
- two or more devices at the same site report offline within a bounded correlation window;
- a server and one or more related VMs/hosts report offline;
- an Autotask monitoring ticket indicates server/site loss of connectivity;
- a technician asks Jason to determine whether a site, server group, or server is actually offline.

Initial correlation window: **5 minutes**. Expand to **15 minutes** when provider polling cadence or device-class monitoring cadence differs.

Jason must not infer that workstations remained healthy merely because they lack matching offline alerts; server and workstation DRMM polling/monitoring cadence may differ.

---

## 3. Scope and Boundaries

### In Scope
- Autotask ticket/alert correlation;
- DRMM endpoint state, last-seen, reboot time, alert history, audit data, WAN/LAN IPs;
- live read-only endpoint commands/components;
- public-IP reachability from an AOT-controlled external probe where available;
- gateway, DNS, Internet-by-IP, Internet-by-name, and peer reachability tests;
- read-only Windows network/NIC/event-log diagnostics;
- hypervisor/guest correlation;
- DRMM-discovered SNMP/network-device evidence as the preferred first source for firewall/router/switch/UPS and other infrastructure telemetry;
- direct vendor read-only telemetry only when DRMM cannot answer the required localization question;
- duplicate alert suppression and site-level incident correlation.

### Out of Scope
- reboot, shutdown, forced logoff;
- NIC disable/enable, service restart, adapter reset, vSwitch change;
- firewall, router, switch, VLAN, DNS, DHCP, ISP, or Hyper-V configuration changes;
- power cycling;
- unapproved packet captures or intrusive network scans;
- treating ICMP failure alone as proof of outage.

Preserve Central Orchestrator authority, exact requester grants, provider/client isolation, audit trail, approval requirements, and `direct_provider_access=false`.

---

## 4. Initial Identification

1. Identify the exact Autotask ticket(s), DRMM alert UID(s), client, site, device(s), and alert timestamps.
2. Resolve every affected endpoint to authoritative DRMM identity.
3. Determine device role: physical host, VM guest, domain controller, application server, workstation, firewall/router, switch, or other.
4. Record current DRMM online state, last-seen, last reboot, LAN IP, WAN/public IP, and site ID.
5. Correlate alerts from the same site within 5 minutes; expand to 15 minutes where cadence differences justify it.
6. Determine whether multiple alert tickets represent one site event. Preserve ticket history even when one parent incident is used operationally.
7. Identify the site's apparent public IP from authoritative managed-endpoint evidence; do not infer it from another client.
8. Enumerate DRMM-discovered network/SNMP devices for the affected site and identify likely gateway, firewall, switch/uplink, UPS, and other infrastructure objects.
9. Note whether affected assets share a hypervisor, switch/uplink, VLAN, gateway, WAN IP, DNS path, or infrastructure power path when authoritative evidence exists.

If identity or site mapping is ambiguous:

`state = identification_blocked`

Document and escalate rather than guessing.

---

## 5. Expected State

Healthy state means:
- expected servers and critical endpoints answer current governed read-only checks;
- no unexplained synchronized offline events are active;
- default gateway is reachable from an in-site endpoint;
- Internet reachability by IP succeeds where expected;
- DNS name resolution and outbound connection by name succeed;
- public site IP is reachable by approved external checks when the firewall/ISP is expected to answer that test;
- hypervisor and guest relationship is internally consistent;
- no evidence shows repeated NIC link flap, switch/uplink failure, WAN renewal/flap, DNS outage, or provider-only disconnect.

A public IP that blocks ICMP may still be healthy; combine ICMP with other available external evidence.

---

## 6. State Model

`identified -> scope_correlating -> live_validating -> path_localizing -> classified -> verifying -> complete`

Additional states:
- `waiting_for_endpoint`
- `waiting_for_provider`
- `external_probe_unavailable`
- `network_telemetry_unavailable`
- `blocked`
- `unknown_escalate`
- `escalated`

Localization classifications:
- `endpoint_only`
- `hypervisor_or_vswitch`
- `server_switch_or_uplink`
- `site_lan`
- `gateway_firewall`
- `wan_isp`
- `dns_only`
- `rmm_provider_path`
- `transient_site_connectivity`
- `unknown_escalate`

Persist the latest completed diagnostic layer so Jason does not repeat completed tests unnecessarily.

---

## 7. Diagnostic Workflow

### Step 1: Establish the incident timeline
**Purpose:** Determine whether this is one device or a correlated site event.  
**Evidence source:** DRMM alerts/history, Autotask tickets.  
**Read:** endpoint alert search/history plus ticket search/read.  
**Expected result:** Exact first-seen/resolved times for each affected device.

**Decision**
- One endpoint only -> continue endpoint diagnostics.
- Two or more separate devices at same site within correlation window -> treat as a site/shared-path candidate.
- Hyper-V guests and host share timing -> include hypervisor/upstream path in scope.
- Different device classes have different monitoring cadence -> do not exclude them solely for missing alerts.

### Step 2: Check for reboot or power evidence
**Purpose:** Separate connectivity loss from host/OS restart.  
**Evidence source:** DRMM endpoint state/audit; Windows events when available.  
**Expected result:** Last reboot predates the outage.

**Decision**
- Reboot aligns with alert -> investigate endpoint/power/shutdown path.
- No reboot across multiple affected systems -> connectivity/shared infrastructure becomes more likely.

### Step 3: Prove current "online" state
**Purpose:** Do not trust DRMM green state alone.  
**Evidence source:** current read-only component/command execution.  
**Command/component:** safe deterministic command such as hostname/time/network-summary query.  
**Expected result:** Fresh job completes and returns current output.

Select:
- at least one affected server that now shows online;
- 2-3 representative workstations from the same physical site/network when available;
- the hypervisor when relevant.

**Decision**
- Fresh output succeeds -> device is truly reachable through DRMM now.
- DRMM says online but current read-only execution repeatedly cannot run -> possible provider/RMM-path or agent problem.
- Device remains offline -> continue with peers and infrastructure evidence.

### Step 4: Test inside-site path to default gateway
**Purpose:** Determine whether endpoint-to-LAN/gateway path works.  
**Evidence source:** live endpoint diagnostic.  
**Command:** read current default gateway, then bounded ping/Test-Connection to gateway.  
**Expected result:** gateway reachable with low loss.

**Decision**
- Gateway unreachable from multiple live endpoints -> `site_lan`, `server_switch_or_uplink`, or `gateway_firewall`; inspect network layer.
- Only one endpoint cannot reach gateway -> `endpoint_only` likely.

### Step 5: Test Internet by IP
**Purpose:** Separate DNS from WAN routing.  
**Command:** bounded reachability to a stable approved public IP such as `1.1.1.1`; use more than one target if required by policy.  
**Expected result:** external IP reachable.

**Decision**
- Gateway reachable, public IP not reachable from multiple in-site endpoints -> `gateway_firewall` or `wan_isp`.
- Public IP reachable -> WAN path exists; continue DNS test.

### Step 6: Test DNS and Internet by name
**Purpose:** Identify DNS-only failure.  
**Evidence source:** live endpoint plus configured DNS servers.  
**Command:** read DNS server list; resolve an approved known Internet name; optionally test TCP 443 to the resolved host.  
**Expected result:** DNS query succeeds and outbound connection succeeds.

**Decision**
- Internet-by-IP succeeds but DNS lookup fails -> `dns_only`.
- DNS resolution succeeds but outbound TCP fails broadly -> firewall/WAN policy or path issue.
- AD-integrated DNS clients fail while external DNS works -> investigate internal DNS/DC path.

### Step 7: Test public site IP externally
**Purpose:** Determine whether the client WAN edge is reachable from outside.  
**Evidence source:** AOT-controlled external probe, not a client endpoint.  
**Target:** authoritative current site public IP.  
**Tests:** bounded ICMP plus another approved reachability method when available.  
**Expected result:** result consistent with known firewall policy.

**Decision**
- Public IP normally responds and fails during incident -> strong `wan_isp` / edge evidence.
- ICMP fails but service probe succeeds -> do not call outage.
- Public IP remains externally healthy while internal endpoints lose Internet -> investigate firewall/LAN/DNS.
- No external probe capability -> `external_probe_unavailable`; continue other layers.

### Step 8: Compare hypervisor and guests
**Purpose:** Distinguish guest/vSwitch failure from upstream site loss.  
**Evidence source:** DRMM endpoint state/audit/history.  
**Expected result:** host/guest timing relationship established.

**Decision**
- Guest(s) offline while host remains freshly reachable -> `hypervisor_or_vswitch` candidate.
- Host and all guests disappear together, no reboots -> upstream network/WAN path is more likely.
- Physical host offline but unrelated physical endpoints remain healthy -> host/NIC/switch-port path.

### Step 9: Review NIC and Windows network events
**Purpose:** Detect local adapter reset/link loss.  
**Evidence source:** Windows System log, read-only network state.  
**Look for:** NDIS, vendor NIC events, TCP/IP path loss, adapter resets, link down/up, duplicate IP, gateway loss.  
**Expected result:** no local link flap matching incident.

**Decision**
- Matching NIC/link events on one host -> endpoint/host NIC path.
- Same host has no NIC event while multiple systems disappear -> look upstream.

### Step 10: Harvest DRMM SNMP/network-device evidence first
**Purpose:** Use AOT's existing RMM telemetry before adding or invoking direct-vendor integrations.  
**Evidence source:** DRMM network-device discovery, endpoint device read, endpoint audit/SNMP data, DRMM alert history.  
**Expected result:** identify site infrastructure objects and capture every available DRMM field relevant to the incident.

For each relevant DRMM-discovered infrastructure device, record when available:
- device type/vendor/model/description;
- management IP and MAC;
- SNMP uptime;
- current DRMM online/monitor state;
- current and historical alerts;
- interface/port state and counters;
- link transitions, errors, CRCs, discards;
- STP/LACP/uplink state;
- WAN/interface health;
- UPS/power state.

**Decision**
- DRMM contains the needed evidence -> use it as the authoritative first source.
- DRMM identifies the device but omits the needed telemetry -> record a bounded capability gap and then use an approved direct-vendor read capability if one exists.
- DRMM has no authoritative network object -> use documented topology/provider evidence and mark the missing DRMM coverage.

Do not interpret a missing SNMP field as a healthy value.

### Step 11: Review firewall/router/WAN telemetry
**Purpose:** Localize edge/WAN failure.  
**Evidence source priority:** DRMM SNMP/network-device telemetry first; direct SonicWall/UniFi/vendor read-only telemetry second when DRMM is insufficient.  
**Look for:** WAN link up/down, DHCP/PPPoE renewals, ISP failover, gateway monitoring loss, DNS forwarder failures, device reboot/uptime change, packet loss, interface errors.  
**Expected result:** stable edge state.

If neither DRMM nor an approved vendor read can provide the evidence:
`state = network_telemetry_unavailable`
and document the capability gap.

### Step 12: Review switch/uplink telemetry
**Purpose:** Localize LAN/server-switch failure.  
**Evidence source priority:** DRMM SNMP/network-device telemetry first; direct switch/controller API second when required.  
**Look for:** port/uplink flap, STP topology change, CRC/errors, discards, port reset, LACP member loss, PoE/power event where relevant.  
**Decision:** correlated errors on shared uplink -> `server_switch_or_uplink` or `site_lan`.

### Step 13: Review power-management evidence
**Purpose:** Determine whether infrastructure power, not server OS, dropped.  
**Evidence source:** iLO/iDRAC, UPS, PDU, switch/firewall uptime/logs where governed.  
**Important:** unchanged Windows server uptime does not exclude a switch/firewall/ISP-device power event.

### Step 14: Test for DRMM/provider-path-only failure
**Purpose:** Avoid declaring client outage when only RMM transport failed.  
**Evidence:** external site reachability, local gateway/Internet/DNS tests, independent monitoring, current endpoint reads.  
**Decision:**
- client network tests healthy while only DRMM disconnected -> `rmm_provider_path`;
- independent network symptoms align with DRMM alerts -> classify underlying network layer.

---

### Approved read-only path test

AOT owner approval is recorded for this playbook to perform the following **read-only localization diagnostic** on an exact authorized in-scope endpoint:

1. read the current default gateway;
2. send a bounded reachability test to that gateway;
3. send a bounded reachability test to an approved public IP (default `1.1.1.1`);
4. resolve an approved public DNS name (default `www.microsoft.com`);
5. perform a bounded TCP 443 connectivity test to that resolved/public name;
6. record results, timestamps, target device, and job/correlation IDs.

**Authority classification:** read-only / non-destructive diagnostic.

This approval does **not** authorize any network or endpoint mutation, including NIC reset, DNS change, route change, firewall change, service restart, reboot, or switch/router action.

The playbook approval does not bypass Jason's live governance. If the current execution policy still requires a per-run approval token/signal, Jason must use the requester approval for that exact run and must not weaken or bypass the policy.

---

## 8. Decision Gates

Before any remediation:
1. exact client/site is confirmed;
2. device identities are confirmed;
3. current outage versus historical/stale alert is established;
4. localization classification is supported by at least two independent evidence points when practical;
5. any disruptive action is separately approved;
6. provider capability exists for the proposed action;
7. no maintenance/change window already explains the event.

Never reboot a server, restart a network device, bounce a NIC, reset a switch port, or change DNS/firewall configuration merely to test a theory.

---

## 9. Remediation

This playbook is **diagnostic/localization first**.

Automatic/standing-safe remediation: **none by default**.

After classification, route to the appropriate approved playbook or technician workflow:
- endpoint-only -> endpoint/network-stack troubleshooting;
- hypervisor/vSwitch -> Hyper-V playbook/technician;
- switch/uplink -> network infrastructure workflow;
- gateway/firewall -> firewall workflow;
- WAN/ISP -> ISP/escalation workflow;
- DNS-only -> DNS/DC workflow;
- RMM-provider path -> Datto RMM/provider investigation.

All modifying or disruptive remediation remains separately governed.

---

## 10. Retry Policy

- Live read-only reachability test: maximum 2 retries per target per diagnostic phase.
- External probe: maximum 2 retries with a short bounded interval.
- Provider read failure: retry once when transport failure is plausible.
- Do not redispatch a still-active DRMM job; poll the same job.
- After repeated contradictory or unavailable evidence, transition to `unknown_escalate`.

---

## 11. Periodic Rechecks

For an active outage:
- default recheck: every 5 minutes for critical server/site events;
- recheck current endpoint state, public reachability where supported, and newly resolved/open alerts;
- suppress duplicate scheduled checks for the same site incident.

Stop when:
- classification and stable recovery are verified;
- a human takes ownership;
- ticket closes;
- escalation occurs;
- maintenance explains the event.

---

## 12. Aging / Stale Condition

Escalate repeated brief outages when:
- 2 or more correlated site events occur in 24 hours; or
- 3 or more occur in 7 days; or
- the pattern has persisted without a root-cause disposition.

Repeated auto-resolving alerts are not considered healthy simply because each individual ticket closes.

Investigate ISP instability, edge device logs, switch/uplink health, DNS path, DRMM provider path, and infrastructure power.

---

## 13. Dependency Handling

Potential dependencies:
- no external AOT probe;
- DRMM does not expose required SNMP/interface/port telemetry;
- no firewall/router log capability after DRMM-first review;
- no switch telemetry after DRMM-first review;
- no UPS/iLO telemetry;
- no current network diagram or asset mapping;
- DRMM ad-hoc command approval required;
- client edge blocks expected external tests.

Document the missing dependency and add/associate a TODO/support item when it materially prevents localization. Do not fabricate evidence.

---

## 14. Documentation Requirements

Document:
- incident correlation window and affected devices;
- current DRMM states and last-seen/reboot times;
- whether current "online" was proven by fresh execution;
- gateway, public-IP, DNS, and peer test results;
- external public-IP test result and test type;
- relevant network/NIC/firewall/switch/power evidence;
- localization classification and confidence;
- unresolved evidence gaps;
- job IDs/correlation IDs;
- next action/escalation.

Suggested note titles:
- `Jason - Offline Localization - Incident Correlation`
- `Jason - Offline Localization - Live Validation`
- `Jason - Offline Localization - Network Path`
- `Jason - Offline Localization - Classification`
- `Jason - Offline Localization - Escalation`
- `Jason - Offline Localization - Resolution`

Never document secrets or private credentials.

---

## 15. Failure Handling

Document and branch on:
- DRMM transport unavailable;
- endpoint changes state while testing;
- live command cannot execute despite green state;
- public IP blocks ICMP;
- DNS test target unavailable independently;
- network telemetry connector absent;
- contradictory internal/external results;
- provider job remains active or output is unavailable.

Do not treat missing evidence as healthy evidence.

---

## 16. Escalation Criteria

Escalate when:
- site remains materially unavailable;
- outage repeats above aging thresholds;
- localization is `unknown_escalate`;
- firewall/switch/ISP evidence is required but unavailable;
- physical intervention is likely;
- disruptive remediation is required;
- external/provider dependency requires vendor engagement;
- repeated correlated alerts continue after apparent recovery.

Escalation note must include timeline, affected devices, reboot evidence, live validation, gateway/WAN/DNS results, public-IP test, classification, and recommended next check.

---

## 17. Verification

After recovery:
1. prove at least one affected server is freshly reachable;
2. prove representative workstation(s) are freshly reachable where applicable;
3. verify gateway reachability;
4. verify Internet by IP;
5. verify DNS/name resolution;
6. verify external public-IP state where meaningful;
7. confirm affected alerts resolved;
8. observe a stability window appropriate to severity, default 15 minutes for repeated site events;
9. confirm no new correlated offline alerts appeared during the stability window.

Auto-resolve alone is not sufficient verification.

---

## 18. Completion Criteria

Complete only when:
1. affected objects are identified;
2. incident scope/timeline is documented;
3. current connectivity is independently verified;
4. a reasonable localization classification is established or a human accepts an unresolved vendor/network disposition;
5. required remediation belongs to an approved downstream workflow or was separately approved and verified;
6. no new correlated alert occurs during the defined stability window;
7. final resolution note exists.

---

## 19. Final Resolution Note

Include:
- original alert/ticket set;
- correlated outage times;
- affected device roles;
- whether any device rebooted;
- live workstation/server validation;
- internal gateway/Internet/DNS findings;
- external public-IP findings;
- infrastructure telemetry findings;
- final classification;
- remediation or vendor escalation;
- stability verification period and timestamp;
- remaining follow-up items.

---

## 20. Required Capabilities

Current/narrow capabilities:
- `service.ticket.search/read`
- `service.ticket.notes.search`
- governed internal-note create
- `endpoint.device.search/read`
- `endpoint.audit.read`
- `endpoint.alert.search`
- `endpoint.alert.history.search`
- DRMM network-device discovery and `endpoint.audit.read` SNMP evidence
- DRMM network-device alert/history reads
- `automation.component.search/execute`
- `automation.job.read`
- `automation.job.output.read`
- persisted/scheduled recheck support when available.

Desired capability gaps:
- governed DRMM-first SNMP/network-device telemetry exposing interface/port/uplink/error/WAN/power fields and bounded approved OID reads where necessary (`TODO-NET-002`);
- governed external network probe (ICMP/TCP/HTTPS/DNS) from AOT-controlled infrastructure;
- direct firewall/router WAN-health and event-log reads only where DRMM is insufficient;
- direct switch port/uplink/STP/error reads only where DRMM is insufficient;
- governed UPS/PDU and server-management-controller event reads;
- explicit site topology/dependency mapping.

---

## 21. Acceptance Test

**Initial production case:** Riggins Company, 2026-09-22.

Observed correlated events:
- `MAINSRV`, `SAGESRV`, `ADSRV`, and `VMHOST` produced synchronized offline alerts in multiple waves.
- No affected server reboot aligned with those events.
- DRMM server monitoring cadence is more frequent than workstation monitoring, so lack of workstation offline alerts is not exclusionary evidence.
- Workstation `2023i5PC8` recorded `The remote name could not be resolved: 'endoflife.date'` near two correlated server-offline windows, providing independent DNS/Internet symptom evidence.

### Acceptance evidence already demonstrated

Riggins production evidence collected on 2026-09-22:
- synchronized offline waves were correlated across `MAINSRV`, `SAGESRV`, `ADSRV`, and `VMHOST`;
- physical host versus VM roles were identified;
- affected systems showed no reboot aligned with the incident;
- fresh governed DRMM executions completed on `ADSRV` and workstation `2023i5PC8`, proving current reachability rather than trusting DRMM green state alone;
- workstation `2023i5PC8` independently logged DNS-resolution failures near two outage windows;
- an AOT-controlled external probe to public IP `184.180.34.123` returned 4/4 replies, 0% packet loss, approximately 16 ms average latency after recovery;
- DRMM SNMP audit identified the site edge as a SonicWall TZ 500 at `192.168.1.1` and showed uptime exceeding one day, ruling out a firewall reboot during the event;
- evidence was documented in Autotask internal note `30506232`;
- no disruptive action was taken.

Current bounded classification for the acceptance case: `transient_site_connectivity`, with WAN/DNS/edge path more likely than server, guest, hypervisor, or firewall power failure. Exact root-cause localization remains limited by missing historical interface/port/WAN telemetry.

### Remaining acceptance / implementation gaps

- Live gateway, Internet-by-IP, DNS-name resolution, and TCP 443 testing from an in-site endpoint is an approved read-only playbook diagnostic. The Riggins acceptance run should execute it under the current live governance policy and record the exact job/correlation evidence.
- Deeper DRMM SNMP/interface/port telemetry is tracked in `TODO-NET-002`.
- External/infrastructure telemetry beyond current capabilities is tracked in `TODO-NET-001`.
- Direct vendor integrations are fallback paths only when DRMM cannot provide the required evidence.

Acceptance must prove:
1. trigger/site correlation;
2. physical host vs VM identification;
3. no-reboot evidence;
4. fresh live validation on representative server and workstation;
5. gateway/Internet-by-IP/DNS checks;
6. external public-IP check against the Riggins public IP where supported;
7. bounded classification;
8. ticket documentation;
9. correct handling of unavailable firewall/switch telemetry;
10. no disruptive action.

---

## 22. Section Goal Closure

Section Goal remains open until:
- the Riggins acceptance case demonstrates incident correlation, no-reboot checks, live endpoint validation, external public-IP reachability, DRMM SNMP infrastructure identification, and correct bounded classification/escalation behavior;
- missing DRMM SNMP depth and external/network telemetry capabilities are recorded as explicit follow-up work (`TODO-NET-001` and `TODO-NET-002`);
- results are documented in the authoritative ticket/case;
- Grafana/Project Jason operational visibility is updated where applicable;
- the playbook is reviewed for autonomy eligibility.

This playbook provides diagnostic logic only; it does not grant remediation authority.
