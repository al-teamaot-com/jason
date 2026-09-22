# Jason Playbook: Gromelski And Associates Inc. — Client-Specific Ticket Operations

## 1. Section Goal

**Goal:**  
Apply Gromelski-specific operational rules to every Gromelski ticket before specialized troubleshooting begins, and enforce additional investigation for newly discovered network devices.

**Success means:**
- every ticket is deterministically associated with Gromelski And Associates Inc. before client-scoped work;
- Gromelski's designated primary contact, **Chris Benton** (Autotask contact ID `30684489`, Network Security Director), is associated/notified according to the contact rules below;
- the original requester/end-user context is preserved;
- every newly discovered network device is investigated, documented, and either confirmed expected or escalated;
- no unknown device ticket is silently closed because it appears benign;
- all decisions and evidence are recorded in the ticket.

Do not consider the Section Goal complete until the acceptance criteria have been demonstrated and documented.

---

## 2. Trigger

This client-specific playbook applies when any of the following are true:

- Autotask ticket company is **Gromelski And Associates Inc.**;
- DRMM site is **Gromelski And Associates Inc.** and maps authoritatively to Autotask company ID `597`;
- a recognized vendor/system notification body explicitly identifies **Gromelski And Associates Inc.** and client identity is independently corroborated;
- a specialized Gromelski playbook invokes this client-level playbook.

Additional network-device-discovery branch triggers when:
- ticket title or body indicates a newly discovered, unmatched, unknown, or changed network device;
- IT Glue / network discovery reports a new IP/MAC/device;
- PiAlert or equivalent discovery source reports a new device.

Jason must confirm the trigger before starting.

---

## 3. Scope and Boundaries

### In Scope
- Autotask tickets for Gromelski And Associates Inc.;
- Gromelski DRMM site and managed endpoints;
- IT Glue configurations, flexible assets, network documentation, and discovery evidence where exposed;
- read-only network identification from an authorized managed endpoint;
- contact/ticket hygiene;
- client-specific rules and specialized playbook dispatch.

### Out of Scope
- unrelated clients;
- changing network segmentation, switch configuration, VLANs, firewall rules, or endpoint configuration without a separately approved playbook/action;
- reboot/shutdown/logoff/service interruption without explicit technician approval;
- direct provider access outside Jason governance;
- guessing client identity, device ownership, or authorization.

Preserve:
- `direct_provider_access=false`;
- Central Orchestrator authority;
- exact requester grants;
- provider/client isolation;
- audit trail;
- existing approval rules.

---

## 4. Initial Identification

Before troubleshooting:

1. Identify the exact Autotask ticket.
2. Confirm the authoritative client is **Gromelski And Associates Inc. / Autotask company ID 597**.
3. If the ticket is misassociated (for example, Catchall), resolve client identity using authoritative evidence such as DRMM site -> Autotask company mapping.
4. Attempt governed reassociation only if the capability exists and verification is available.
5. If reassociation is unavailable, document the authoritative client and set:
   `state = client_reassociation_blocked`
   for any client-scoped write that depends on ticket company context.
6. Determine the actual requester/end user if one exists.
7. Resolve Gromelski's designated primary contact:
   - **Chris Benton**
   - Autotask contact ID `30684489`
   - role/title: Network Security Director
   - must be active and still belong to company ID `597`.
8. Apply the contact rule:
   - system-generated ticket with no human requester: Chris Benton should be the ticket contact;
   - user-generated ticket: preserve the actual requester and ensure Chris is additionally associated/notified where supported;
   - if the platform only permits a single ticket contact and cannot additionally associate Chris, preserve the actual requester, document the limitation, and use the approved notification/additional-recipient mechanism when available.
9. Identify the affected device/user/site/object.
10. Record relevant timestamps and external IDs.

If client, requester, contact, or affected object cannot be identified confidently:

`state = identification_blocked`

Do not guess.

---

## 5. Expected State

Healthy client-ticket state:

- ticket is associated with company ID `597`;
- actual requester is preserved when applicable;
- Chris Benton is associated/notified according to the contact rule;
- ticket has the correct configuration item when an affected managed asset can be identified;
- client-specific playbook/rules are visible in ticket notes/audit evidence;
- specialized playbook is selected when a known trigger exists.

For network-device discovery:
- every discovered device is classified as:
  - `known_expected`,
  - `new_expected_confirmed`,
  - `unknown_requires_review`,
  - `unexpected_or_suspicious`,
  - or `stale_false_discovery`;
- classification is evidence-backed;
- unknown/unexpected devices remain open or escalated until disposition is established.

---

## 6. State Model

Base states:

`identified -> client_validated -> contact_validated -> diagnosing -> verifying -> complete`

Additional states:

- `client_reassociation_blocked`
- `contact_association_blocked`
- `device_discovery_review`
- `waiting_for_client_confirmation`
- `known_expected`
- `unexpected_or_suspicious`
- `blocked`
- `escalated`

Persist state so Jason can resume without repeating completed work.

---

## 7. Diagnostic Workflow

### Step 1: Validate Client Association

**Purpose:**  
Prevent cross-client work and Catchall misassociation.

**Evidence source:**  
Autotask + DRMM.

**Read:**  
- Autotask ticket/company;
- DRMM site mapping.

**Expected result:**  
Client resolves uniquely to Gromelski / company ID `597`.

### Decision

If correct:  
-> continue.

If misassociated but authoritative mapping is clear:  
-> attempt governed reassociation if supported; otherwise document and mark `client_reassociation_blocked`.

If ambiguous:  
-> `identification_blocked`.

---

### Step 2: Validate Primary Contact Rule

**Purpose:**  
Ensure Gromelski's primary contact is included on every ticket without losing the real requester.

**Evidence source:**  
Autotask contacts.

**Expected contact:**  
Chris Benton, contact ID `30684489`, active, company ID `597`.

### Decision

If system-generated/no human requester:  
-> set/retain Chris as ticket contact when write capability permits.

If human requester exists:  
-> preserve requester and add/include Chris through supported additional-contact/notification mechanism.

If no supported mechanism exists:  
-> document `contact_association_blocked` and continue only when safe.

---

### Step 3: Resolve Affected Asset

**Purpose:**  
Associate the ticket to the correct CI/device when available.

**Evidence source:**  
Autotask CI, DRMM, IT Glue.

**Expected result:**  
One authoritative asset match.

If no managed asset exists, document why.

---

### Step 4: Network Device Discovery Branch

When a new network device is reported:

1. Capture IP, MAC, discovery source, network/site, and first-seen time.
2. Check Autotask CI inventory.
3. Check IT Glue configurations/flexible assets/documentation.
4. Check DRMM site inventory.
5. Resolve MAC OUI/vendor.
6. From an authorized managed endpoint on the same network, perform bounded read-only identification as needed:
   - ICMP reachability;
   - ARP/neighbor MAC confirmation;
   - reverse DNS;
   - limited service/port fingerprinting;
   - non-authenticated HTTP/HTTPS identity headers/pages where reasonable.
7. Compare against known client network design.
8. If still unknown, obtain client/on-site confirmation.
9. Do not alter or isolate the device merely because it is new.

### Classification

**Known expected:** authoritative documentation or prior accepted evidence matches.

**New expected confirmed:** client/authorized contact confirms the device and evidence is consistent.

**Unknown requires review:** evidence identifies class/vendor but not ownership/purpose.

**Unexpected or suspicious:** evidence conflicts with client design, authorized inventory, or expected device class.

---

## 8. Decision Gates

Before any modifying action:

- client identity must be authoritative;
- affected device/object must be unambiguous;
- contact/requester handling must be understood;
- specialized playbook must authorize the action;
- requester must have authority;
- disruptive actions require explicit technician approval for that instance.

For new network devices:
- discovery alone never authorizes remediation or isolation.

---

## 9. Remediation

### Ticket Hygiene

**Action:** Correct company/contact/CI fields where the governed capability supports them.

**Approval classification:** non-destructive/modifying.

**Verification required:** authoritative Autotask readback.

### Network Device Discovery

No automatic remediation by default.

Permitted non-destructive outcome:
- document classification;
- associate known CI/documentation;
- request/record confirmation;
- escalate unknown/unexpected device.

Any network change requires a separate authorized workflow.

---

## 10. Retry Policy

- Maximum ticket association mutation attempts: `1` unless new evidence changes the request.
- Maximum diagnostic network probe attempts per method: `2`.
- Do not blindly repeat failed connector calls.
- Preserve provider job IDs and poll the same job.
- After retry limit:
  `state = escalated`.

---

## 11. Periodic Rechecks

For a device waiting on client confirmation:

**Default recheck:** next business day or according to ticket SLA/workflow.

Recheck:
- whether client confirmation was received;
- whether device remains present;
- whether documentation/CI was added;
- whether another technician resolved the identity.

Stop when:
- disposition is established;
- ticket closes;
- escalation threshold is reached;
- device is proven stale/no longer present.

---

## 12. Aging / Stale Condition

If a newly discovered device remains unidentified beyond the normal review period:

- verify the discovery is still current;
- check whether DHCP/IP assignment changed;
- search for duplicate/stale CI/documentation;
- revalidate MAC/device evidence;
- escalate to the designated Gromelski contact/technician.

Do not let unknown-device tickets age indefinitely without explicit state and owner.

---

## 13. Dependency Handling

Dependencies may include:

- missing Autotask company/contact reassignment capability;
- missing additional-contact/notification capability;
- missing IT Glue Network Discovery read capability;
- unavailable client network documentation;
- no suitable online managed endpoint for local read-only probing.

Search Support/TODO first. Do not create duplicates.

Known current dependencies:
- `SUPPORT-CONN-006` — Autotask ticket company/contact reassignment unavailable;
- `TODO-CONN-005` — IT Glue notification client reconciliation at intake;
- `TODO-OBS-002` — Grafana client-specific playbook coverage page.

---

## 14. Documentation Requirements

Every meaningful step must be documented.

For all Gromelski tickets document:
- authoritative client validation;
- requester/contact validation;
- Chris Benton association/notification state where relevant;
- CI/device association;
- selected specialized playbook or reason none applies.

For network discoveries document:
- IP/MAC;
- OUI/vendor;
- reachability;
- relevant fingerprints;
- documentation/CI searches;
- client confirmation;
- classification;
- final disposition.

Never document secrets.

---

## 15. Failure Handling

Document:
- ticket reassignment failures;
- contact-association failures;
- connector failures;
- ambiguous client identity;
- missing IT Glue discovery access;
- failed DRMM diagnostics;
- contradictory device evidence.

A failed step must not be silently skipped.

---

## 16. Escalation Criteria

Escalate when:

- client identity is ambiguous;
- actual requester/primary-contact requirements conflict and no safe association path exists;
- newly discovered device cannot be identified;
- client says the device is not expected;
- evidence suggests unauthorized or suspicious equipment;
- a modifying/disruptive action is required;
- required connector/capability is unavailable;
- retry limit is reached.

Escalation note must summarize evidence and recommended next action.

---

## 17. Verification

Ticket hygiene is verified only by Autotask readback.

Network-device disposition is verified by one or more authoritative sources:
- documented CI/configuration;
- trusted client confirmation;
- DRMM/IT Glue correlation;
- repeatable network identity evidence.

Do not close solely because a ping succeeds or a vendor OUI looks familiar.

---

## 18. Completion Criteria

A Gromelski ticket may complete only when:

1. client identity is confirmed;
2. requester/primary-contact handling is documented;
3. affected asset is associated where available;
4. required specialized diagnostics are complete;
5. all client-specific rules were applied;
6. all actions/results are documented;
7. final resolution/disposition is present.

A network-device discovery may complete only when the device is classified and its disposition is documented.

---

## 19. Final Resolution Note

Include:
- ticket/client identity;
- requester and primary-contact handling;
- affected device/CI;
- trigger/symptom;
- diagnostics performed;
- device classification where applicable;
- client confirmation where applicable;
- remediation, if any;
- final verification;
- final disposition.

---

## 20. Required Capabilities

Minimum required:

- Autotask ticket read/search/update;
- Autotask contact read/search;
- Autotask internal note create;
- Autotask configuration search/read;
- DRMM site search;
- DRMM endpoint search/read;
- DRMM component execution for approved read-only diagnostics;
- automation job status/output;
- IT Glue configuration/flexible asset/document reads;
- persisted playbook state;
- scheduled/deferred recheck support.

Needed improvements:
- governed Autotask company/contact reassignment;
- supported additional-contact/notification association for client primary contacts;
- IT Glue Network Discovery object read;
- client-specific playbook telemetry for Grafana.

---

## 21. Acceptance Test

**Initial test target:**  
`T20260922.0017 — Network Device Discovery Gromelski And Associates Inc.`

Prove:

1. detect that Catchall association is incorrect;
2. resolve Gromelski authoritatively to Autotask company ID `597`;
3. resolve Chris Benton as current primary contact ID `30684489`;
4. preserve/document original system-generated requester context;
5. identify discovered device `192.168.10.93 / 64:16:7F:E3:8A:D9`;
6. correlate MAC vendor and network evidence;
7. obtain/record client confirmation;
8. classify device;
9. document connector/capability blockers;
10. verify final ticket disposition;
11. surface the playbook in the planned client-specific Grafana view.

Do not modify the discovered network device during the acceptance test.

---

## 22. Section Goal Closure

When acceptance testing succeeds:

- record implementation commit/version;
- document contact-rule behavior;
- document Gromelski network-device-discovery results;
- record unresolved connector gaps;
- add telemetry to the client-specific Grafana view when available;
- confirm no other Gromelski-specific rules remain undocumented;
- mark this Section Goal complete.

Future Gromelski-specific workflows should reference this umbrella playbook rather than duplicating client identity/contact rules.
