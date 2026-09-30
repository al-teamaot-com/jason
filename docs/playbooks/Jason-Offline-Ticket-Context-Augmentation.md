# Jason Playbook: Offline Ticket Context Augmentation

## Standard Manifest

```yaml
playbook:
  id: offline_ticket_context_augmentation
  name: Jason - Offline Ticket Context Augmentation
  version: 0.1.0
  owner: AOT IT Operations
  target_type: ticket
  trigger:
    provider: Autotask
    match: credible device/server/host offline language with exact same-client device context
  ownership:
    while_open: source_queue
    release_active_slot_when_waiting: true
  retry:
    max_remediation_attempts: 0
  recheck:
    enabled: true
    cadence: 10 minutes while the ticket remains open, or immediately after source-version change
    stale_after: not_applicable
  verification:
    authoritative_source: governed DRMM/DEB/site-witness evidence
    success_condition: one bounded site-context classification is produced
  completion:
    terminal_disposition: source ticket remains unchanged
  autonomy:
    allowed_branches:
      - read_only_context
      - internal_note_augmentation
    approval_bound_branches: []
    disruptive_branches: []
```

## 1. Section Goal

**Goal:** Enrich an open Autotask ticket that credibly reports a managed device/server offline with fast site context before a technician begins troubleshooting, without claiming the ticket, changing its queue/status, consuming an active-work slot, or performing remediation.

**Success means:**
- the exact ticket/company/CI/DRMM endpoint is verified;
- Jason distinguishes target availability from site availability;
- failed PC ICMP is never treated as proof of offline;
- a fresh governed read from a confirmed fixed same-site server can establish that the broad site-down branch is false;
- fixed same-site peer evidence can classify the site as confirmed up, likely up, likely down, partial/segment suspected, or unknown;
- mobile/roaming devices do not count as site witnesses;
- DEB may corroborate whether the target is online outside DRMM;
- one concise internal note is written only when evidence changes;
- no ownership, queue, status, remediation, client communication, or disruptive action occurs.

## 2. Trigger

Apply to open Autotask tickets with bounded endpoint-outage language such as:
- device/server/host/endpoint/workstation/computer/PC offline;
- device/server/host down;
- device/server/host unreachable;
- device/server/host not responding;
- lost contact / lost connection.

A generic phrase such as "offline files" must not trigger this playbook.

The initial implementation requires an exact existing Autotask configuration item. Missing CI identity is a no-write condition rather than permission to guess.

## 3. Scope and Boundaries

### In Scope
- governed Autotask ticket/CI reads;
- governed DRMM endpoint/site/peer reads;
- governed DEB exact-asset read when available;
- one classifier-approved read-only PowerShell call against a fixed same-site server when available;
- deterministic site-context classification;
- one internal Autotask note;
- durable 10-minute throttle and semantic note suppression.

### Out of Scope
- ticket ownership or requeue;
- ticket status/work type/resource mutation;
- CI association mutation;
- endpoint remediation;
- reboot/logoff/service/network changes;
- client-facing communication;
- blind subnet scanning;
- cross-client evidence;
- use of mobile laptops as site witnesses.

Preserve Central Orchestrator authority, `direct_provider_access=false`, exact requester grants, provider/client isolation, and existing disruption controls.

## 4. Initial Identification

1. Read the open ticket.
2. Confirm the trigger.
3. Require an existing configuration item.
4. Read that CI and prove same-company, active identity.
5. Resolve its exact DRMM UID/hostname.
6. Read the exact DRMM endpoint.
7. Use the endpoint's site only after exact target identity is established.
8. Do **not** run the normal ticket-work-start lifecycle; augmentation intentionally does not claim work.

If identity is missing/ambiguous, persist the augmentation check and make no ticket mutation.

## 5. Expected State

The augmentation does not define "healthy" for the endpoint. It defines a useful bounded site-context state:

- `site_confirmed_up`
- `site_likely_up`
- `site_likely_down`
- `partial_or_segment_outage_suspected`
- `site_status_unknown`

Separately record whether DEB reports the target online while DRMM reports it offline.

## 6. State Model

`detected -> identity_verified -> evidence_collecting -> classified -> documented`

No ownership lifecycle is entered.

Persist at minimum:
- ticket ID;
- source version;
- classification;
- evidence fingerprint;
- last check time.

## 7. Diagnostic Workflow

### Step 1: Target DRMM state
Read exact endpoint current state and site.

### Step 2: DEB corroboration
When the exact same-company DEB asset can be found by hostname, record provider status. If DEB is unavailable or ambiguous, continue without fabricating a result.

DRMM offline + DEB online means contradictory target availability evidence and should be called out as a likely RMM/monitoring-path issue. It does not independently prove the physical site is up.

### Step 3: Same-site peer inventory
Read same-site DRMM peers. Classify roles conservatively:
- server = fixed;
- desktop/workstation = fixed;
- laptop/notebook/portable = mobile and excluded from site-health proof;
- unknown role = do not count as a fixed witness.

### Step 4: Active fixed-server witness
If a same-site server reports online, Jason may run exactly one classifier-approved read-only command:

`Get-NetIPConfiguration`

Fresh returned output proves Jason can actively reach that fixed server through the governed management path. That is strong affirmative evidence that the broad site-down branch is false for the path reaching that server.

This does not prove every switch/VLAN/segment is healthy.

### Step 5: Classification
- fresh fixed-server read succeeds + fewer than two fixed peers offline -> **site confirmed up**;
- fresh fixed-server read succeeds + two or more fixed peers offline -> **partial/segment outage suspected**;
- at least two fixed peers online, no active-server proof -> **site likely up**;
- at least two fixed peers offline and no fixed online witness -> **site likely down**;
- otherwise -> **site status unknown**.

Failed ICMP on a PC is not used as negative evidence in this classifier.

## 8. Decision Gates

Before note creation:
- exact same-company CI;
- exact DRMM UID;
- no cross-client evidence;
- bounded trigger matched;
- exact augmentation source/version is owner-promoted for `service.ticket.note.create`;
- evidence collection completed without identity conflict.

## 9. Remediation

Not applicable.

The only write is the approved internal note. No ticket state or provider endpoint state changes.

## 10. Retry Policy

No remediation retries.

Evidence collection is throttled to once per 10 minutes per ticket, except a ticket source-version change may make it immediately eligible for reassessment.

## 11. Periodic Rechecks

Recheck while the open ticket remains in the governed queue set. Suppress unchanged notes by semantic fingerprint.

Do not create a new note merely because the worker cadence ran.

## 12. Aging / Stale Condition

Not applicable to remediation. The parent Server/Site Offline playbook owns outage aging/escalation.

## 13. Dependency Handling

Dependencies:
- exact CI/DRMM identity;
- DRMM site/peer reads;
- DEB exact-asset read when available;
- read-only PowerShell capability for strongest server witness;
- internal Autotask note capability;
- durable augmentation state.

Missing optional evidence reduces confidence; missing identity prevents a write.

## 14. Documentation Requirements

Note title:

`Jason - Offline Ticket Context`

Preferred body:
1. **STATUS** — site context.
2. **NEXT STEP** — technician focus; explicitly state Jason did not take ownership.
3. **KEY EVIDENCE** — target DRMM/DEB state plus bounded witness list.
4. **INTERPRETATION** — endpoint vs site/segment context.
5. **CHANGES MADE** — None; read-only augmentation only.

## 15. Failure Handling

A provider/read failure is not an outage conclusion. Fail closed, throttle the failed check, and allow a later reassessment.

## 16. Escalation Criteria

This augmentation playbook does not itself escalate or requeue. If it classifies `site_likely_down` or `partial_or_segment_outage_suspected`, the full Server/Site Offline playbook may independently admit the incident under its rapid-response clock.

## 17. Verification

Verification is deterministic evidence classification plus provider-verified internal-note creation.

## 18. Completion Criteria

One augmentation cycle completes after:
- exact identity;
- bounded evidence collection;
- classification;
- changed-note write/readback if needed;
- durable throttle state.

The source ticket remains in its existing queue/status/assignment.

## 19. Final Resolution Note

Not applicable. This is context augmentation, not incident ownership.

## 20. Required Capabilities

Reads:
- `service.configuration.read`
- `endpoint.device.read`
- `endpoint.device.search`
- `backup.endpoint.asset.search` when available
- `endpoint.powershell.read` for a fixed-server active witness

Action:
- `service.ticket.note.create`

No `service.ticket.update` and no `automation.component.execute` are required.

## 21. Acceptance Test

Prove:
1. technician-owned offline ticket can be augmented;
2. no queue/status/resource/work-type mutation occurs;
3. active-work-slot count is unaffected;
4. online roaming laptop does not prove site health;
5. live fixed-server read produces `site_confirmed_up`;
6. live fixed-server read plus multiple fixed-peer failures produces partial/segment classification;
7. multiple fixed offline peers with no online witness produces `site_likely_down`;
8. DRMM offline + DEB online is documented as target-provider conflict;
9. failed PC ping is never converted into confirmed/likely offline by this classifier;
10. unchanged worker cycles do not create duplicate notes or repeated active server probes inside the throttle window;
11. no note is written without exact durable owner promotion;
12. note creation is provider-readback verified.

## 22. Section Goal Closure

Close when:
- deterministic module/tests pass;
- runtime hook/tests pass;
- exact owner promotion is created for `offline_ticket_context_augmentation@0.1.0`;
- controlled production ticket proves augmentation without ownership mutation;
- Grafana/operational reporting exposes augmentation outcomes;
- remaining provider evidence gaps are documented.

## 23. Autonomous Execution Eligibility and Owner Review

Design approved by owner on 2026-09-30.

Approved branch:
- governed reads;
- one fixed-server read-only witness command;
- one duplicate-suppressed internal note.

Explicitly not approved by design:
- ownership/queue/status changes;
- endpoint/network remediation;
- client communication;
- disruption.

Source-controlled implementation must pass acceptance and receive exact durable promotion before unattended ticket-note writes occur.
