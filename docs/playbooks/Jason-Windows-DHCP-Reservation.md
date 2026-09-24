# Jason Playbook: DHCP Reservation - Microsoft Windows DHCP

## 1. Section Goal

**Goal:** Process requests to reserve a private IPv4 address for a device by first identifying the authoritative DHCP server and, only when that server is Microsoft Windows DHCP, creating exactly one DHCP reservation for the MAC address associated with the requested IP.

**Success means:**
- the correct client/site, private IP, and MAC are identified;
- the authoritative DHCP source is proven rather than assumed;
- Microsoft Windows DHCP is confirmed;
- the exact active scope is confirmed;
- IP/MAC conflicts are ruled out;
- exactly one reservation is created when required;
- readback proves the requested IP/MAC pair;
- the work is documented in Autotask;
- the ticket is returned to Help Desk I / In Progress unless separately directed.

**Hard-stop invariant:** If the authoritative DHCP source is not Microsoft Windows DHCP, Jason must make no DHCP configuration change under this playbook. Set `state = non_windows_dhcp`, document the discovered provider/source, and stop.

Do not consider this Section Goal complete until the controlled acceptance test is implemented and documented.

---

## 2. Trigger

Apply when an Autotask ticket or approved request asks for:
- DHCP reservation;
- reserved IP;
- static/reserved DHCP address;
- "reserve this IP for this machine";
- equivalent address-reservation work.

The request must provide or contain:
- a private IPv4 address; and
- a MAC address in the ticket, attachment, screenshot, device information, or another authoritative source.

Jason must confirm the trigger matches before starting the playbook.

---

## 3. Scope and Boundaries

### In Scope
- RFC1918 private IPv4 addresses.
- Microsoft Windows DHCP Server.
- Read-only DHCP-source discovery.
- Scope, lease, and reservation reads.
- One DHCP reservation creation.
- Autotask documentation and ticket routing.
- DRMM-managed Windows servers/endpoints used for governed diagnostics/execution.

### Out of Scope
- Public IP assignments.
- Scope creation or scope modification.
- DHCP exclusions, lease duration, DNS option, gateway option, VLAN, subnet, or relay changes.
- Deleting or reassigning existing reservations.
- SonicWall, UniFi, router, firewall, switch, or other appliance DHCP writes.
- Direct provider access, shell/API bypasses, or any path outside Jason governance.

Preserve:
- `direct_provider_access=false`
- Central Orchestrator authority
- exact requester grants
- provider/client isolation
- audit trail
- existing approval rules

---

## 4. Initial Identification

1. Identify the exact Autotask ticket or approved request.
2. Identify the client and site.
3. Extract the requested IPv4 address.
4. Confirm the address is private RFC1918 space.
5. Extract the MAC address associated with the requested address.
6. Normalize the MAC as `AA-BB-CC-DD-EE-FF`.
7. Preserve the hostname/device name when provided.
8. If the request contains an attachment or screenshot, verify that the displayed MAC and IP belong to the requested device.
9. Do not infer, invent, or substitute a MAC.
10. Apply the normal global ticket-work-start lifecycle before substantive diagnostics:
   - move ticket to queue Jason;
   - set status In Progress;
   - set Work Type Remote Support;
   - require post-mutation readback.
11. Device association is not mandatory when the affected object is a non-managed printer/appliance with no valid Autotask CI. If a managed CI is applicable, follow the global device-association gate.

If the IP or MAC cannot be established confidently:

`state = identification_blocked`

Document the missing/ambiguous evidence and stop.

---

## 5. Expected State

Healthy final state:
- exactly one authoritative DHCP source owns the subnet;
- that source is Microsoft Windows DHCP;
- DHCP Server service is running;
- exactly one active IPv4 scope contains the requested IP;
- no conflicting reservation exists;
- no conflicting active lease/device exists;
- the reservation maps exactly `requested IP -> requested MAC`;
- authoritative readback confirms the mapping.

---

## 6. State Model

`identified -> discovering_dhcp -> validating_scope -> checking_conflicts -> remediating -> verifying -> documented -> handed_off`

Alternate states:
- `identification_blocked`
- `dhcp_ambiguous`
- `non_windows_dhcp`
- `conflict_detected`
- `authority_blocked`
- `execution_failed`
- `escalated`

Persist the current state so Jason does not repeat completed work after handoff, restart, or conversation boundary.

---

## 7. Diagnostic Workflow

### Step 1: Determine the authoritative DHCP source

**Purpose:** Identify which system actually serves DHCP for the subnet. Never assume the DNS server, domain controller, or default gateway is the DHCP server.

**Evidence sources:**
- a managed Windows endpoint on the same subnet;
- Windows DHCP authorized-server inventory;
- DRMM server inventory;
- IT Glue/network documentation where available;
- current lease information showing the DHCP server identifier.

**Preferred read on a same-subnet Windows endpoint:**

`Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object { $_.DHCPEnabled } | Select-Object DHCPServer,IPAddress,DefaultIPGateway`

Supplement with authoritative documentation or server/service evidence as needed.

**Decision:**
- Exactly one Windows DHCP server identified -> continue.
- Multiple possible DHCP servers -> `state = dhcp_ambiguous`; stop.
- DHCP source is SonicWall, UniFi, firewall, router, appliance, or other non-Windows service -> `state = non_windows_dhcp`; document and **hard stop with no write**.
- DHCP source cannot be proven -> `state = dhcp_ambiguous`; stop.

### Step 2: Confirm Microsoft Windows DHCP

On the identified Windows server verify:

`Get-Service DHCPServer`

Expected:
- service exists;
- status = Running;
- startup type is appropriate for the server.

Then enumerate scopes:

`Get-DhcpServerv4Scope`

Identify the single scope containing the requested IP.

### Step 3: Validate the requested address

Confirm:
- requested IP belongs to the identified scope/subnet;
- it is not the network address;
- it is not the broadcast address;
- it is not the DHCP server itself;
- it is not the default gateway unless the request explicitly concerns that device;
- the scope belongs to the correct client/site.

Record:
- DHCP server hostname/IP;
- scope ID and name;
- start/end range;
- subnet mask;
- requested IP;
- requested MAC.

A requested address may be inside the dynamic pool; this alone does not block creation of a Windows DHCP reservation.

### Step 4: Conflict checks

Read reservation by requested IP:

`Get-DhcpServerv4Reservation -ScopeId <scope> -IPAddress <requested IP>`

Read all reservations in the scope and compare normalized ClientId with requested MAC.

Read current lease:

`Get-DhcpServerv4Lease -ScopeId <scope> -IPAddress <requested IP>`

Also determine whether the requested MAC currently holds another DHCP lease where practical.

**Decision:**
- same IP + same MAC reservation already exists -> no write; proceed to verification.
- requested IP reserved to a different MAC -> `state = conflict_detected`; stop.
- requested MAC reserved to a different IP -> `state = conflict_detected`; stop.
- requested IP leased to a different MAC -> `state = conflict_detected`; stop.
- requested IP leased to the same MAC -> reservation may proceed.
- no current lease -> reservation may proceed when the MAC is authoritatively supplied by the approved request/attachment.
- contradictory evidence -> stop and escalate.

Where reasonable, check active network use before reserving the address. An active device with a different MAC is a conflict.

---

## 8. Decision Gates

Before remediation all must be true:
- correct client/site confirmed;
- private IP confirmed;
- MAC confirmed;
- authoritative DHCP source uniquely identified;
- DHCP source is Microsoft Windows DHCP;
- DHCP Server service is running;
- exact active scope identified;
- requested IP belongs to that scope;
- no conflicting reservation;
- no conflicting lease/device;
- requester has authority;
- governed execution path is available.

**Non-Windows DHCP gate:** any authoritative evidence that DHCP is served by SonicWall, UniFi, a firewall/router/appliance, Linux DHCP, cloud DHCP, or another non-Microsoft service causes an immediate hard stop. Do not attempt an alternate provider write under this playbook.

---

## 9. Remediation

**Action:** Create exactly one Microsoft DHCP reservation.

Example governed command:

`Add-DhcpServerv4Reservation -ScopeId <scope> -IPAddress <IP> -ClientId <MAC> -Name <hostname> -Description "AOT reservation - <ticket number>" -ErrorAction Stop`

If hostname is unavailable, use a neutral ticket-derived reservation name; do not invent a device identity.

**Approval classification:** modifying / non-disruptive.

The playbook does not itself grant authority. Existing Jason approval and execution controls remain authoritative.

**Verification required:** post-write reservation readback must match the exact IP and MAC.

---

## 10. Retry Policy

Maximum automatic reservation-create attempts: **1**

Do not retry blindly.

If execution is ambiguous:
1. do not submit the mutation again;
2. read back the reservation;
3. if the exact reservation exists, treat the write as successful;
4. if it does not exist or remains ambiguous, document and escalate or require new authorization.

---

## 11. Periodic Rechecks

Normally not applicable.

For a DRMM component/job:
- poll the same Job ID;
- do not redispatch because status remains Active/Pending;
- retrieve output only from the same job;
- observe the returned `do_not_redispatch` contract.

Suggested escalation threshold for a normally short DHCP diagnostic/write job: 10 minutes.

---

## 12. Aging / Stale Condition

If the identified DHCP server remains offline/inaccessible or the request cannot be completed because required evidence remains unavailable, document the dependency and escalate. Do not retry indefinitely.

---

## 13. Dependency Handling

Possible dependencies:
- DHCP server offline;
- missing DRMM access;
- missing or unreadable request attachment;
- missing/ambiguous MAC;
- unknown DHCP provider;
- multiple DHCP servers;
- non-Windows DHCP;
- missing governed execution authority.

Do not fabricate missing configuration or borrow values from another client.

---

## 14. Documentation Requirements

Add an internal Autotask note with:
- requested IP;
- requested MAC;
- hostname/device name if known;
- authoritative DHCP server;
- DHCP type/provider;
- scope ID/name;
- scope range and subnet mask;
- conflict-check result;
- command/component used;
- Job ID / correlation ID where available;
- write result;
- readback result;
- statement that no unrelated DHCP configuration changed.

Suggested note title:

`Jason - DHCP Reservation - Completed`

For hard-stop cases use:

`Jason - DHCP Reservation - Non-Windows DHCP Hard Stop`

and document the discovered provider/source and why no mutation was attempted.

---

## 15. Failure Handling

Document and stop on:
- DHCP source cannot be determined;
- multiple DHCP servers;
- non-Windows DHCP;
- scope cannot be uniquely determined;
- MAC missing or ambiguous;
- IP/MAC conflict;
- DHCP service unavailable;
- requested IP outside expected scope;
- governed command unavailable;
- authority denied;
- job failure;
- ambiguous provider result not resolved by readback;
- contradictory evidence.

Never silently skip failed gates.

---

## 16. Escalation Criteria

Escalate when:
- DHCP is not Microsoft Windows DHCP;
- multiple DHCP servers may own the subnet;
- an existing reservation conflicts;
- an existing lease uses a different MAC;
- active network use conflicts;
- required data is missing;
- DHCP server is unhealthy;
- execution authority is unavailable;
- the bounded write attempt fails.

The escalation note must summarize the evidence, current state, and recommended next technician action.

---

## 17. Verification

After creation, independently run:

`Get-DhcpServerv4Reservation -ScopeId <scope> -IPAddress <requested IP>`

Verify exactly:
- ScopeId;
- IPAddress;
- ClientId/MAC;
- reservation name;
- description when used.

Normalize MAC delimiters before comparison.

Success requires:

`readback IP == requested IP`

and

`readback MAC == requested MAC`

Command submission alone is not success.

---

## 18. Completion Criteria

The playbook task is complete only when:
1. the authoritative DHCP source was identified;
2. Microsoft Windows DHCP ownership was confirmed;
3. the correct active scope was confirmed;
4. conflict checks passed;
5. the reservation was created or already existed correctly;
6. independent readback matches exactly;
7. the Autotask note was written;
8. no unrelated DHCP configuration changed.

After successful technical work:
- return the ticket to **Help Desk I**;
- set status **In Progress**;
- leave normal technician/customer follow-up unless separately authorized.

A `non_windows_dhcp` result is a successful **hard stop**, not a completed reservation.

---

## 19. Final Resolution Note

Include:
- original request;
- IP/MAC pair;
- DHCP source/server;
- DHCP provider/type;
- scope;
- conflict-check result;
- reservation action or hard-stop reason;
- mutation-attempt count;
- verification result;
- timestamp;
- final ticket disposition.

---

## 20. Required Capabilities

Current narrow capability set:
- Autotask ticket search/read;
- Autotask ticket notes search/create;
- Autotask ticket update;
- ticket/attachment content access where available;
- DRMM site/device search/read;
- DRMM component search;
- governed `automation.component.execute`;
- `automation.job.read`;
- `automation.job.output.read`;
- persisted playbook state.

Current implementation may use `Run Ad Hoc Command (PowerShell 2-5) [WIN]` through governed Datto RMM execution.

### Future Improvement

Add dedicated governed capabilities:
- `network.dhcp.source.discover`
- `network.dhcp.scope.read`
- `network.dhcp.reservation.search`
- `network.dhcp.reservation.create`

Future appliance-specific DHCP playbooks may be added later. Until then, this playbook must hard stop on every non-Microsoft DHCP provider.

---

## 21. Acceptance Test

Reference production evidence from BDS ticket `T20260924.0115 - Static IP`:
- requested IP: `192.168.1.85`;
- device: `imagePRESS-V800`;
- MAC: `00-03-2D-60-10-6A`;
- authoritative DHCP server: `BDS-DC`;
- provider: Microsoft Windows DHCP;
- scope: `192.168.1.0/24`;
- pool: `192.168.1.50 - 192.168.1.181`;
- reservation creation returned `RESERVATION_CREATED`;
- exit code `0`;
- Autotask ticket was documented and returned to Help Desk I / In Progress.

Before enabling autonomous execution, run a controlled playbook-level acceptance test proving:
1. trigger detection;
2. IP/MAC extraction;
3. DHCP-source discovery;
4. non-Windows hard-stop behavior;
5. Windows scope resolution;
6. conflict gates;
7. exactly one reservation mutation;
8. no blind retry;
9. readback verification;
10. Autotask documentation;
11. Help Desk I / In Progress handoff;
12. persisted state.

Do not modify unrelated production objects during testing.

---

## 22. Section Goal Closure

Close the Section Goal only after:
- this playbook is merged into Project Jason;
- deterministic DHCP-source discovery is implemented;
- non-Windows DHCP hard-stop behavior is enforced;
- Windows DHCP reservation execution is governed;
- controlled acceptance testing succeeds;
- ticket documentation/handoff is verified;
- known limitations are recorded;
- Grafana / Project Jason status is updated;
- dedicated DHCP capability work is tracked as follow-up.

Until then, the BDS result is implementation evidence, not blanket autonomous authority.
