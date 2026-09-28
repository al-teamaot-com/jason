# Jason Playbook: VulScan Network / Embedded Vulnerability Investigation

## 1. Section Goal

**Goal:** Diagnose and classify VulScan findings against network, embedded, appliance, printer/MFP, web-interface, Linux-appliance, or otherwise non-standard endpoint assets without performing remediation.

**Success means:**
- Jason identifies the likely physical/logical asset behind the IP/MAC finding;
- correlates the finding to available Autotask, DRMM, IT Glue/documentation, KFS/print, and network evidence;
- classifies the vulnerability into a meaningful remediation category;
- suppresses duplicate investigation work;
- documents a technician-ready next step;
- performs **no autonomous remediation**.

## 2. Trigger

Apply when a VulScan ticket/finding:
- targets an IP/MAC with no reliable managed Windows endpoint;
- identifies jQuery, HTTPS/TLS, weak cipher, BREACH, embedded web server, firmware, web UI, or similar service-stack vulnerability;
- targets printers/MFPs, switches, firewalls, controllers, appliances, Linux/embedded systems, or unknown network devices.

Examples from the current Monitoring Alert queue include jQuery and TLS findings on `192.168.10.93` and multiple `192.168.12.x` assets.

## 3. Scope and Boundaries

### In Scope
- Autotask ticket ownership/notes/CI association when identity is reliable;
- IP/MAC/site/client correlation;
- DRMM and Autotask CI lookup;
- IT Glue/documentation lookup;
- KFS/managed-print correlation where applicable;
- passive/read-only service and asset evidence available through governed capabilities;
- finding classification;
- duplicate grouping/correlation;
- technician recommendation.

### Out of Scope
- firmware updates;
- TLS/cipher changes;
- web-server configuration changes;
- switch/firewall/printer changes;
- package/application updates on appliances;
- credentialed device administration;
- reboots;
- service restarts;
- direct provider access;
- any remediation action.

Preserve all Jason governance invariants and `direct_provider_access=false`.

## 4. Initial Identification

1. Read the ticket and extract client, IP, MAC, hostname if present, CVE/finding list, scanner timestamp, and ports/services when available.
2. Determine whether the asset maps to a normal managed endpoint. If yes, route to the appropriate endpoint/application/Windows playbook.
3. Search same-company Autotask configuration items by IP/MAC/name/serial evidence.
4. Search DRMM for matching IP/MAC/hostname where available.
5. Search IT Glue/documentation for network, printer, server, application, or appliance records.
6. Search KFS/print inventory when printer/MFP evidence is plausible.
7. Associate the ticket to a CI only when exactly one authoritative same-company match is established.
8. Claim the ticket through the global ticket-work-start lifecycle only after the target/site is sufficiently identified for safe read-only investigation.
9. Search for duplicate open findings against the same asset/service.

If no reliable asset identity can be established, set `state=identification_blocked` but still document all known evidence.

## 5. Expected State

This is a diagnostic-only playbook. Healthy state is not restored by Jason.

The expected output is a validated investigation package containing:
- best-known asset identity;
- confidence level and evidence;
- affected service/application/firmware family when determinable;
- vulnerability class;
- duplicate/related findings;
- likely remediation owner/path;
- explicit statement that no remediation was performed.

## 6. State Model

`identified -> correlate_asset -> classify_service -> assess_duplicates -> document_recommendation -> diagnostic_complete`

Branches:
- `endpoint_route`
- `identification_blocked`
- `vendor_dependency`
- `escalated`

Persist:
- ticket ID;
- company/site;
- IP/MAC/hostname;
- candidate CI/device/document IDs;
- confidence and selected identity;
- CVE/finding list;
- open ports/services when available;
- duplicate ticket IDs;
- current state;
- last evidence fingerprint.

## 7. Diagnostic Workflow

### Step 1: Determine asset class

Use IP/MAC/OUI, Autotask CI, DRMM, IT Glue/documentation, and KFS/print evidence.

Classify as one of:
- printer/MFP;
- network switch/router/firewall;
- server/appliance;
- embedded controller/IoT;
- Linux/Unix host;
- unknown web-enabled device;
- normal managed endpoint (route elsewhere).

Do not infer vendor/model from MAC alone when stronger evidence is absent.

### Step 2: Correlate service/finding

For each finding, record:
- CVE/plugin text;
- affected port/protocol if available;
- whether it appears to be web UI, TLS stack, bundled jQuery/library, firmware, or general OS/package exposure;
- whether multiple findings likely share one root component.

### Step 3: Search existing documentation and history

Look for:
- asset vendor/model/firmware;
- management URL/documented role;
- prior tickets with same device/finding;
- known replacement/EOL status;
- current support/vendor relationship;
- existing remediation/project ticket.

### Step 4: Determine likely remediation category

Classify, without executing:
- vendor firmware/update likely required;
- application/web UI update likely required;
- TLS/cipher configuration likely required;
- unsupported/EOL asset likely requires replacement planning;
- scanner false-positive/stale evidence possible;
- unknown/manual investigation required.

### Step 5: Duplicate/site correlation

Group repeat findings for the same model/site/service when evidence supports a common cause. Do not create repetitive notes/tickets for identical unchanged evidence.

## 8. Decision Gates

No remediation gate exists because remediation is prohibited.

Before any diagnostic action beyond provider reads:
- correct client/site must be established;
- action must be read-only;
- no credentialed configuration change may occur;
- no active scanning beyond already-approved read/diagnostic capabilities may be launched unless separately authorized.

## 9. Remediation

**Not applicable — diagnostic-only.**

Jason must not:
- update firmware;
- change cipher suites/TLS;
- alter web server configuration;
- install packages;
- change printer/network settings;
- reboot/restart devices or services;
- suppress/close a genuine finding merely to clear the queue.

Any proposed remediation becomes a separate technician action or future dedicated playbook with its own acceptance test and owner approval.

## 10. Retry Policy

- Read/correlation operations may retry once for transient provider failure.
- Do not repeatedly probe an unidentified device.
- No remediation retries exist.
- Persistent provider/data ambiguity -> `state=identification_blocked` or `escalated`.

## 11. Periodic Rechecks

Normally none.

A bounded recheck may be scheduled only when waiting for:
- documentation synchronization;
- a known scanner refresh;
- a linked technician/vendor remediation ticket.

Unchanged rechecks do not create duplicate notes.

## 12. Aging / Stale Condition

If an unidentified or unresolved network/embedded finding persists:
- check for retired/replaced/stale asset records;
- check whether IP reassignment has occurred;
- check for duplicate CIs;
- correlate scanner timestamp with current inventory;
- escalate if identity remains unresolved beyond the normal operational review window.

## 13. Dependency Handling

Potential dependencies:
- missing IT Glue/network documentation;
- missing CI;
- inaccessible vendor/model/firmware data;
- no authorized network read capability;
- vendor support case;
- replacement/project work.

Confirm a dependency is actually missing, search for an existing ticket, suppress duplicates, and cross-reference rather than inventing data.

## 14. Documentation Requirements

Document:
- IP/MAC/hostname/site/client;
- CVE/finding text;
- candidate assets and why they were accepted/rejected;
- selected asset identity and confidence;
- CI/document/KFS/DRMM references;
- service/port/category evidence;
- duplicates/related tickets;
- likely remediation category;
- explicit statement: **Diagnostic only — no remediation performed**;
- recommended technician/vendor next step.

## 15. Failure Handling

Document:
- ambiguous IP/MAC ownership;
- no matching CI/documentation;
- conflicting asset records;
- stale IP mapping;
- provider read failure;
- multiple equally plausible devices;
- insufficient service/version data.

Do not convert uncertainty into a confident device identification.

## 16. Escalation Criteria

Escalate when:
- asset identity is uncertain;
- finding involves an internet-facing or security-critical appliance;
- unsupported/EOL hardware is indicated;
- vendor credentials/configuration access is required;
- firmware/configuration changes are needed;
- scanner evidence conflicts with current asset state;
- a severe finding requires technician validation beyond available read-only evidence.

## 17. Verification

Because no remediation occurs, verification means:
- the investigation evidence is internally consistent;
- selected identity is supported by authoritative data;
- vulnerability classification is documented;
- duplicate relationships are recorded;
- recommended next action is actionable;
- no unauthorized write/remediation occurred.

## 18. Completion Criteria

The diagnostic task may complete when:
- all reasonable governed read-only correlation has been performed;
- asset identity is resolved or explicitly marked unresolved;
- finding category is established;
- duplicate/related tickets are linked;
- technician/vendor next step is documented;
- ticket disposition is set to the appropriate human-review queue/status and verified by readback.

Do **not** mark the vulnerability itself resolved unless authoritative external evidence shows it has actually cleared.

## 19. Final Resolution Note

Use a diagnostic handoff note containing:
- finding summary;
- asset identity/confidence;
- correlated records;
- affected service/component;
- likely remediation category;
- duplicate/related tickets;
- unresolved questions;
- recommended technician/vendor action;
- statement that Jason performed no remediation.

## 20. Required Capabilities

- Autotask ticket read/search/update/note
- Autotask CI search/read
- DRMM endpoint/device search/read
- IT Glue/documentation configuration/flexible-asset/document search/read
- KFS/print device/alert reads when applicable
- operational-resolution memory search
- persisted state
- optional bounded read-only network/service evidence when separately available and approved

No mutation capability beyond ticket lifecycle/documentation is required.

## 21. Acceptance Test

Use one current IP/MAC-oriented VulScan ticket such as `T20260919.0003` or an equivalent controlled case.

Prove:
1. trigger routes the case away from Windows/application remediation;
2. IP/MAC/client extraction;
3. CI/DRMM/documentation/KFS correlation;
4. multiple-candidate ambiguity handling;
5. finding/service classification;
6. duplicate grouping;
7. no remediation/component execution;
8. technician-ready handoff note;
9. human-review queue/status write and readback;
10. persisted state and duplicate-note suppression.

## 22. Section Goal Closure

Close when:
- playbook is implemented and registered;
- at least one controlled diagnostic case completes successfully;
- no-remediation enforcement is tested;
- any missing correlation capability is captured as a TODO/support item;
- Grafana/Project Jason status is updated.

## 23. Autonomous Execution Eligibility and Owner Review

`autonomous_allowed: diagnostic_only`

Allowed autonomous scope:
- ticket/asset identification;
- governed read-only correlation;
- duplicate analysis;
- diagnostic note creation;
- routing to human review.

Explicitly prohibited:
- any endpoint/network/appliance remediation;
- firmware/configuration/package changes;
- reboot/restart;
- vulnerability suppression/closure without authoritative resolution evidence.

Material changes require new owner review.
