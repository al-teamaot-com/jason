# Project Jason TODO and Future Ideas

This document is the governed backlog for ideas, enhancements, integrations, and capabilities Jason is not yet expected to provide.

The purpose is to preserve good ideas without allowing them to become undocumented scope, hidden commitments, or accidental production features. If Jason should already be able to perform a workflow and cannot, or a blocker/defect is discovered during real troubleshooting, that belongs in `SUPPORT.md` instead of this backlog.

## How to use this document

Each item should include:

- **Idea** — what is being proposed.
- **Why it matters** — the business, security, compliance, reliability, or usability benefit.
- **Why not now** — dependency, maturity, risk, cost, or uncertainty that prevents immediate implementation.
- **Prerequisites** — foundations that must exist first.
- **Risk level** — low, moderate, high, or critical.
- **Decision owner** — the person or governance role responsible for approving advancement.
- **Review trigger** — the condition that should cause the item to be reconsidered.
- **Status** — proposed, researching, planned, blocked, rejected, implemented, or retired.

Items in this document are not approved capabilities and must not be enabled merely because they appear here.

**Active-roadmap rule:** Keep only independently actionable work with remaining scope here. Completed and superseded records move to the consolidation-history file, while legacy IDs remain mapped below. Reusable provider integrations remain separate when they serve multiple workflows.

### Governed engineering intake

Jason may use this backlog as an engineering intake source under the governed TODO Engineering Intake playbook.

- Only items whose Status begins with Planned or In progress are eligible for autonomous engineering intake.
- Proposed, Researching, Blocked, Rejected, Implemented, and Retired items are not automatic implementation authority.
- Support List defects remain higher priority than normal TODO work.
- An eligible TODO may create one bounded owner-approved development issue and reuse the existing development worker.
- Merge is not completion. The exact merged SHA must pass Jason Release Manager, isolated pre-production, production verification, and Release Manager closure.
- Protected-core production changes still require exact owner approval at the Release Manager gate.
- The TODO is changed to Implemented only after authoritative production verification and a documentation closure PR.


---

## Priority legend

- **P0** — foundational or required before production use.
- **P1** — important near-term capability.
- **P2** — useful after the core platform is stable.
- **P3** — future or experimental capability.

---

## Future reasoning and quality controls

### TODO-AI-001 — Reasoning quality, independent review, and confidence calibration

- **Priority:** P2
- **Status:** Proposed
- **Risk level:** High
- **Idea:** Provide one governed reasoning-quality program that independently reviews complex/high-impact outputs, adjudicates meaningful model disagreement, and calibrates model confidence against verified outcomes and technician feedback.
- **Why it matters:** Independent review, disagreement handling, and confidence calibration are sequential maturity stages of the same quality-control capability.
- **Program phases:** (1) independent second-model review of the primary draft and evidence package; (2) disagreement adjudication that fails closed for critical unresolved conflicts; (3) confidence calibration against verified outcomes and technician corrections.
- **Important rule:** Agreement between models is not proof of correctness. Deterministic controls, authoritative evidence, and human authority remain controlling.
- **Review triggers:** legal/compliance/financial/employment/security/privacy content; executive/public communication; destructive or high-impact recommendations; low confidence; conflicting evidence; large financial exposure; mass communication; novel work outside established playbooks.
- **Prerequisites:** provider-neutral reasoning interface; sensitivity/risk classification; deterministic policy checks; model/version logging; evidence-by-reference; structured review schema; feedback capture; reliable outcome labels; privacy/retention controls; cost/latency limits.
- **Legacy IDs consolidated here:** TODO-AI-002 and TODO-AI-003.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Begin after the production reasoning provider, audience policy, approval workflow, and full audit chain are stable.

## Operational learning and resolution reuse

### TODO-OPS-001 — Operational Resolution Memory and case-based troubleshooting reuse

- **Priority:** P1
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-04
- **Implementation state at approval:** In progress — governed search/reuse and confirmed-case ingestion are production-deployed; first verified-case capture and later reuse proof pending
- **Autonomous engineering readiness:** Approved
- **Authority basis:** Owner approval on 2026-10-04 authorizes autonomous engineering only within this exact TODO scope; existing Jason governance, client/provider boundaries, protected-core release approval, financial authority, and disruptive-action controls remain unchanged.
- **Risk level:** Moderate
- **Idea:** Build a governed Resolution Memory that captures structured outcomes from alerts, tickets, diagnostics, governed executions, technician corrections, and verified resolutions so Jason can find comparable historical cases and use what worked — and what failed — to choose better first diagnostic and remediation steps.
- **Why it matters:** Many MSP incidents recur with substantially the same symptoms, products, error codes, service states, versions, or environmental conditions. Reusing verified prior outcomes can reduce mean time to resolution, avoid repeating known dead ends, improve first-action quality, and turn AOT's accumulated operating experience into durable institutional knowledge.
- **Why not now:** The capability depends on trustworthy outcome labeling, reliable ticket/alert/device correlation, durable job/output evidence, client isolation, recency/staleness handling, and enough real production history to distinguish a repeatable pattern from a one-off success.
- **Prerequisites:**
  - REFLECT-001 governed reflection and continuous-improvement foundation;
  - normalized issue/incident signature model;
  - structured `ResolutionRecord` schema;
  - correlation between Autotask tickets, Datto RMM alerts/jobs/output, IT Glue documentation, and later approved email-derived evidence;
  - technician-confirmed outcome/root-cause capture;
  - tenant/client isolation and privacy/retention controls;
  - confidence, recency, contradiction, and deprecation handling;
  - search/ranking of similar historical cases;
  - governed playbook-promotion workflow and regression coverage.
- **Resolution record should preserve:** issue/alert signature; affected client/device/product/version; symptoms and error codes; relevant evidence; diagnostics attempted; PowerShell/components/actions attempted; success/failure result of each step; disruption/approval requirements; confirmed root cause; final resolution; correlation/source references; recency; and technician confirmation where available.
- **Expected lifecycle:** `observed -> repeated -> verified pattern -> playbook candidate -> promoted/deprecated`.
- **Expected behavior:**
  1. Normalize a new alert or ticket into an issue signature.
  2. Search Resolution Memory for materially similar prior cases.
  3. Rank prior cases by similarity, recency, evidence quality, and verified outcomes.
  4. Prefer high-confidence read-only diagnostics that historically differentiated or resolved the issue.
  5. Avoid repeatedly trying steps that consistently failed in comparable cases unless current evidence materially differs.
  6. Treat successful historical remediation as evidence, not execution authority; normal approval, disruption, client-scope, and data-access rules still apply.
  7. Record the new outcome so future ranking improves.
  8. Promote only repeated, verified patterns into durable playbooks after governed review.
- **Important safeguards:**
  - one successful case must not become organization-wide truth;
  - client-specific exceptions must not silently generalize to other clients;
  - failures and contradictory outcomes must reduce confidence rather than disappear;
  - current endpoint/ticket evidence must be checked before applying a historical pattern;
  - no historical record may broaden provider access, execution authority, approval scope, or disruption authority;
  - mutating/disruptive actions continue to require their normal approval even when historically successful.
- **Relationship to existing roadmap:** This extends `REFLECT-001` and GitHub issue #172. Reflection identifies reusable lessons; Resolution Memory makes verified troubleshooting outcomes searchable and reusable during future incident handling. It must not become a parallel self-modifying or execution-authority system.
- **Initial motivating example:** A recurring Datto EDR alert showing a stale EDR version plus stopped `EndpointProtectionService` can be correlated with prior diagnostics and outcomes. If previous comparable cases show that service-only intervention failed while an approved EDR reinstall succeeded, Jason can prioritize the proven read-only diagnostic path and present the historically successful remediation when appropriate, while still requiring any normal approval for the modifying action.
- **Implementation checkpoint (2026-09-18):** Resolution Memory is now registered in the live generic Investigation Broker as an evidence-only integration. The reasoning loop can discover/search same-client historical cases only when an authenticated current client scope exists and a grounded current incident signature is available. Unconfirmed observed cases are excluded from live troubleshooting guidance; deprecated/stale cases remain excluded; failures remain first-class evidence; all returned history continues to carry `grants_authority=false`. Organization-level aggregate health is available without exposing raw case content. Production MCP image `jason-mcp:resmem-ingest-1a5f2b2` is live. `operations.resolution.summary` succeeded after deployment with correlation `corr_mcp_56b21063bfc545ccb1f054f0c167b050`, reporting zero cases, `scope=organization_aggregate`, `raw_cases_exposed=false`, and `grants_authority=false`. Controlled fail-closed ingestion of technician-confirmed resolved work is implemented and deployed. Prometheus target `jason-resolution-memory` is `up`, aggregate store availability is `1`, and roadmap metric `RESMEM-001` is `active`. The next slice is to capture the first eligible verified resolution and prove same-client retrieval/reuse against a later materially similar case before this TODO can be declared complete.
- **First-case pre-acceptance (2026-09-27):** AVMAC-1096 / `T20260924.0043` was selected as the first reviewed candidate using authoritative ticket/company reads and the controlled Idle Log Off playbook acceptance. The candidate is scoped to organization `aot`, client `1179`, preserves the approved setter as approval-required/disruptive, and was validated with the real ingestion tool against a disposable SQLite store. It became `verified`, was retrievable from client `1179`, was invisible from another client, matched its reviewed same-client signature, and retained `grants_authority=false`; with one case, every step remains `insufficient_history`. No production Resolution Memory write was performed. Evidence: `docs/sessions/Resolution-Memory-First-Verified-Case-Preacceptance-2026-09-27.md`. Remaining acceptance is controlled production ingestion plus later materially-similar same-client reuse proof.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Begin design once governed ticket/alert reads, Datto job/output correlation, and reliable resolution outcomes are stable; implement before incident volume makes repeated rediscovery materially costly.

### TODO-OPS-002 — Governed BackupIQ ticket-processing playbook

- **Priority:** P1
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-04
- **Implementation state at approval:** Planned
- **Autonomous engineering readiness:** Approved
- **Authority basis:** Owner approval on 2026-10-04 authorizes autonomous engineering only within this exact TODO scope; existing Jason governance, client/provider boundaries, protected-core release approval, financial authority, and disruptive-action controls remain unchanged.
- **Risk level:** High
- **Idea:** Build and productionize an end-to-end governed Jason playbook for Autotask tickets titled `BackupIQ: Backup for asset is not available for AOT Office`, including asset resolution, availability gating, periodic rechecks, Endpoint Backup diagnostics, bounded remediation, dependency-ticket creation, full command/result documentation, and verified successful-backup closure.
- **Current blocker:** The playbook requires the Datto Endpoint Backup API details/credentials available at the Owner's desk so Jason can verify backup inventory/state and require an authoritative successful backup before ticket closure. Do not substitute DRMM agent state alone for backup-success evidence.
- **Review trigger:** Resume when the Owner is at a trusted workstation with the Endpoint Backup API information.
- **Why it matters:** BackupIQ tickets are repetitive, evidence-driven MSP work that Jason can materially process when the correct read, execution, ticket-write, scheduling, and verification capabilities are available. A deterministic playbook can reduce technician effort while preserving auditability, client isolation, and AOT approval rules.
- **Why not now:** A live test exposed specific missing capabilities and workflow gaps that prevent safe end-to-end completion today, including governed Autotask ticket creation, reliable DRMM component discovery/metadata reads, durable workflow state, and scheduled periodic rechecks.
- **Prerequisites:** governed Autotask ticket search/read and internal notes; narrowly scoped Autotask ticket creation; DRMM endpoint/software/service reads; DRMM component search/metadata read; governed component execution; job/result/StdOut reads; site-variable presence validation without secret disclosure; persisted playbook state; periodic recheck scheduling; duplicate suppression; and successful-backup verification.
- **Decision owner:** Jason Governance Authority / Jason Architecture Authority
- **Review trigger:** Implement as the next operational playbook after the required bounded capabilities are available and validate against the controlled AOT-50740 BackupIQ ticket workflow.

#### Architect prompt

```text
Build and productionize a governed Jason playbook for Autotask tickets with the title:

BackupIQ: Backup for asset is not available for AOT Office

SECTION GOAL

Jason must be able to take one of these BackupIQ tickets from initial triage through verified resolution or escalation, while fully documenting every step in the original Autotask ticket.

The playbook must follow Jason’s existing governance model, Central Orchestrator authority, exact grants, provider isolation, and direct_provider_access=false.

Do not weaken or bypass existing governance.

TEST FINDINGS THAT MUST BE ADDRESSED

We tested the proposed workflow against AOT endpoints and identified capability/workflow gaps that prevent the full playbook from completing today.

1. Jason can locate and read DRMM endpoints and determine:
   - hostname
   - site
   - online/offline state
   - last seen
   - last logged-in user
   - other endpoint facts

2. Jason can search/read Autotask tickets and can create internal ticket notes through the governed internal-note path.

3. Jason currently did not have a governed Autotask ticket-create capability available during the test.
   - This blocks the branch where a missing DRMM site variable requires Jason to create a configuration/dependency ticket.
   - Add a narrowly scoped governed ticket-create capability suitable for this playbook.

4. A governed endpoint/component discovery/read path was not available during part of the test (endpoint.component.search was not active).
   - Jason needs a reliable governed way to locate the exact DRMM component by name and validate its metadata/requirements before execution.
   - Do not require direct provider access.

5. The test also proved that Jason must not write BackupIQ troubleshooting notes into an unrelated ticket simply because it is for the same device.
   - Jason must identify the actual BackupIQ ticket first.

6. AOT-50282 demonstrated the importance of the two-hour gate: a recent reboot meant the endpoint had not yet completed a full backup cycle.
7. AOT-50740 demonstrated the offline branch: the device was offline, so remediation should not begin.

CORE PLAYBOOK

1. IDENTIFY THE BACKUPIQ TICKET AND ASSET

Read the BackupIQ ticket and extract:

- ticket ID/number
- organization
- asset/device name
- alert time
- BackupIQ/external identifier if present
- alert details

Resolve the asset to the exact DRMM endpoint.

Do not continue if the asset cannot be identified confidently.

Do not use an unrelated Autotask ticket for documentation.

2. MANDATORY INTERNAL DOCUMENTATION

Every meaningful playbook step must create an internal Autotask ticket note.

This includes:

- reads/checks
- commands
- DRMM components
- decisions
- failures
- blockers
- retries
- remediation
- verification

Every command/component execution must document:

- purpose
- exact command or component name
- target device
- job/correlation ID when available
- terminal status
- return/exit status when available
- relevant StdOut/StdErr
- Jason’s interpretation
- resulting next decision

Secrets, passwords, API keys, tokens, and site-variable values must never be written into Autotask notes.

Document only whether a required secret/variable was present and usable.

Use standardized note titles such as:

- Jason - BackupIQ - Asset Validation
- Jason - BackupIQ - Device Availability
- Jason - BackupIQ - Device Availability Recheck
- Jason - BackupIQ - Backup Agent Check
- Jason - BackupIQ - Site Variable Check
- Jason - BackupIQ - Remediation
- Jason - BackupIQ - Verification
- Jason - BackupIQ - Escalation
- Jason - BackupIQ - Resolution

3. DEVICE AVAILABILITY GATE

Check the current DRMM status first.

IF OFFLINE

Document:

- device is offline
- check timestamp
- last-seen timestamp
- duration offline
- exact governed read used and result

Do not attempt backup-agent repair while offline.

Enter state:

offline_waiting

Recheck the endpoint every hour while the BackupIQ ticket remains active.

Each recheck must be documented.

When the device becomes online:

- document the observation time
- begin the two-hour continuous-online qualification window
- transition to waiting_backup_cycle

If it goes offline during the qualification window, reset the two-hour window.

OFFLINE MORE THAN 10 DAYS

After the device has been offline for more than 10 days, stop treating this as a normal hourly-retry condition.

Investigate whether the endpoint is:

- retired
- replaced
- stale
- renamed/reimaged
- duplicated in DRMM/Autotask
- experiencing a larger connectivity or management issue

Document findings and either correct the monitoring/asset condition where authorized or escalate.

The playbook must prevent endless hourly retry loops after this threshold.

4. TWO-HOUR BACKUP-CYCLE GATE

AOT’s Datto Endpoint Backup cycle is approximately two hours.

Before diagnosing or reinstalling Endpoint Backup, Jason must establish that the endpoint has been continuously available long enough to complete a full two-hour backup cycle.

Prefer DRMM connectivity/check-in evidence.

System uptime alone may support the conclusion but does not prove continuous Internet/DRMM availability.

States:

waiting_backup_cycle -> diagnosing

If the endpoint has not completed the full two-hour window:

- document that fact
- do not reinstall Endpoint Backup
- continue periodic rechecks

5. ENDPOINT BACKUP DIAGNOSTICS

Once the two-hour gate is satisfied:

Check:

- whether Datto Endpoint Backup is installed
- relevant service/process state
- version where available
- obvious service/install abnormalities

Document each read/command and its result.

Do not assume the BackupIQ alert itself proves an agent failure.

6. REQUIRED DRMM SITE VARIABLE

The prescribed remediation component is:

Datto Endpoint Backup Agent v2 [WIN]

This component depends on a DRMM site variable.

Jason must determine the exact required site-variable name from authoritative component/provider metadata.

Do not hard-code or invent the variable name if it can be discovered authoritatively.

Do not guess, fabricate, or copy a value from another client/site.

IF THE SITE VARIABLE IS MISSING

Do not execute the component.

First search Autotask for an existing open ticket covering the missing variable for that same site.

If an appropriate open ticket exists:

- reference it in the BackupIQ ticket
- do not create a duplicate

If none exists:

create a governed Autotask configuration/dependency ticket containing:

- client/site
- affected device
- original BackupIQ ticket number
- required site-variable name
- statement that the value is missing
- dependent component: Datto Endpoint Backup Agent v2 [WIN]

Never include the secret value.

Cross-reference the dependency ticket in the original BackupIQ ticket.

The original BackupIQ ticket remains open/blocked.

7. REMEDIATION

If:

- endpoint has completed the two-hour online qualification
- required site variable exists and is usable

then execute:

Datto Endpoint Backup Agent v2 [WIN]

This is the defined playbook remediation/reinstall component.

Execution must remain governed.

For each attempt:

- record component name
- endpoint
- job ID
- execution status
- terminal result
- actual governed StdOut/StdErr
- interpretation

Do not treat job submitted as success.

Verify terminal completion and retrieve actual execution output.

8. RETRY POLICY

Allow no more than two full remediation attempts.

A full attempt includes:

- pre-check
- site-variable validation
- component execution
- terminal-result verification
- actual output retrieval
- post-install/service validation

If the first attempt fails, document the failure and perform one additional full attempt if appropriate.

If the second full attempt fails:

- stop automatic remediation
- transition to escalated
- create a comprehensive internal escalation note
- do not loop indefinitely

9. POST-REMEDIATION VERIFICATION

A successful component execution does not resolve the BackupIQ ticket by itself.

After remediation, verify:

- Endpoint Backup agent is installed
- required service/process state is healthy
- no relevant installation/service error remains

Then wait for and confirm an actual successful backup.

The ticket must not be completed until Jason has authoritative evidence that a successful backup occurred.

Where available, document:

- successful backup timestamp
- provider/BackupIQ status
- backup object/device identity

10. COMPLETION CRITERIA

The BackupIQ ticket may only be completed when:

1. the correct endpoint has been identified;
2. the endpoint has been sufficiently available;
3. any required remediation has succeeded;
4. the backup agent is healthy;
5. a successful backup has been confirmed;
6. all commands/actions/results are documented;
7. the final resolution note has been added.

Final resolution note should summarize:

- root cause
- device availability history relevant to the incident
- commands/components used
- remediation attempts
- results
- successful backup timestamp
- final verified state

STATE MODEL

Implement explicit persisted playbook state so Jason does not repeat completed work unnecessarily.

Suggested states:

identified
-> offline_waiting
-> waiting_backup_cycle
-> diagnosing
-> blocked_missing_variable
-> remediating
-> verifying
-> complete

or:

escalated

The state needs to survive periodic rechecks and conversation/session boundaries.

PERIODIC RECHECK REQUIREMENTS

Jason needs a governed mechanism to resume this playbook without relying on a human to repeatedly ask.

For offline devices:

- recheck hourly

For devices waiting to complete the two-hour window:

- recheck sufficiently often to establish the qualification window without excessive polling; hourly is acceptable

For remediation verification:

- recheck until a successful backup is observed or escalation criteria are reached

Do not create duplicate scheduled/recheck jobs for the same BackupIQ ticket.

Stop future rechecks when the ticket reaches complete, escalated, or another terminal state.

CAPABILITY WORK REQUIRED

Architect should determine the narrowest governed capabilities necessary to complete this workflow.

At minimum, verify or add:

- Autotask ticket search/read
- Autotask internal note create
- Autotask ticket create
- DRMM endpoint search/read
- DRMM software/service diagnostic capability
- DRMM component search/metadata read
- governed DRMM component execution
- DRMM component job-status read
- DRMM component StdOut/StdErr read
- DRMM site-variable existence/metadata read without exposing secret values
- persisted workflow/state support
- scheduled/periodic recheck support

Do not broaden capabilities beyond what this playbook requires.

GOVERNANCE

Preserve:

- direct_provider_access=false
- Central Orchestrator authority
- exact Jason grants
- requester identity
- provider isolation
- audit trail
- bounded retries
- existing role controls

This playbook must not authorize disruptive actions such as rebooting the endpoint.

The Endpoint Backup reinstall component should only execute if it is classified under AOT/Jason governance as an approved non-destructive component for the requester’s role. Do not silently weaken approval requirements.

ACCEPTANCE TEST

After implementation, use the existing BackupIQ ticket for:

AOT-50740

as the controlled end-to-end validation target where appropriate.

Current known condition from the initial test: the endpoint was offline when checked.

The acceptance test should demonstrate:

1. correct ticket/device association
2. offline detection
3. internal note creation
4. persisted hourly recheck state
5. transition when the device returns online
6. two-hour availability qualification
7. Endpoint Backup diagnostics
8. site-variable validation
9. dependency-ticket creation if variable is missing
10. component discovery and governed execution if variable exists
11. terminal job/result/StdOut retrieval
12. maximum two remediation attempts
13. successful-backup verification
14. final internal resolution note
15. stopping scheduled rechecks after completion/escalation

Do not modify unrelated production systems or tickets during development/testing.

When complete, document the implementation, tests, capability changes, and remaining limitations, and update the appropriate Project Jason/Grafana Section Goal status.
```


### TODO-OPS-003 — Evidence-backed cyber insurance and security questionnaire readiness

- **Priority:** P1
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-04
- **Implementation state at approval:** Planned
- **Autonomous engineering readiness:** Approved
- **Authority basis:** Owner approval on 2026-10-04 authorizes autonomous engineering only within this exact TODO scope; existing Jason governance, client/provider boundaries, protected-core release approval, financial authority, and disruptive-action controls remain unchanged.
- **Risk level:** Moderate
- **Idea:** Give Jason a governed, evidence-backed workflow for answering client cyber-insurance, PII/security, compliance, and vendor-security questionnaires using authoritative client-specific data instead of assumptions or generic AOT standards.
- **Why it matters:** AOT is regularly asked to complete technical portions of insurance/security forms. Jason should be able to collect current evidence across managed endpoints, Microsoft 365/Entra, email security, backup systems, DNS/security services, network/security appliances, security-awareness training, Autotask, and IT Glue; distinguish confirmed facts from client-owned business/legal questions; identify exceptions; and produce a traceable answer package.
- **Why not now:** The current catalog can verify some endpoint facts but lacks several read surfaces required for complete evidence-backed answers. Active blockers are tracked in SUPPORT-CAP-006 through SUPPORT-CAP-011.
- **Prerequisites:**
  - standing-safe diagnostic execution for non-destructive endpoint checks;
  - governed Microsoft 365 / Entra security-posture reads;
  - governed client backup-posture reads;
  - governed network/security-appliance posture reads;
  - governed DNSFilter client posture reads;
  - governed BullPhish/security-awareness posture reads;
  - authoritative client/company/asset correlation across Autotask, Datto RMM, and IT Glue;
  - evidence timestamps and source/correlation references;
  - a questionnaire answer schema that supports `confirmed`, `exception`, `needs client confirmation`, and `not applicable`;
  - explicit separation between technical evidence and business/legal/insurance attestations.
- **Expected behavior:** Jason should parse a questionnaire, map each technical question to available governed evidence, perform only approved read-only verification, report exceptions rather than hiding them, identify questions that belong to the client/legal/insurance representative, and generate a draft answer key with evidence references and unresolved items. Jason must not sign, certify, or make business/legal representations on behalf of the insured.
- **Learning behavior:** Any questionnaire item that cannot be verified because of a missing capability, provider read, or governance restriction should create or reference a Support List blocker rather than being guessed. Repeated questionnaire gaps should inform connector and documentation priorities.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Begin implementation after SUPPORT-CAP-006 through SUPPORT-CAP-011 have defined owners and the first required read surfaces are available.


### TODO-OPS-004 — Governed DRMM monitor suppression for known accepted conditions

- **Priority:** P1
- **Status:** Blocked — provider automation surface (`SUPPORT-CAP-015`)
- **Risk level:** High
- **Idea:** Add a governed capability for Jason to disable, suppress, mute, or otherwise prevent a specific Datto RMM monitor from generating repeated alerts/tickets when the underlying condition is known, understood, documented, and intentionally accepted until a larger corrective action is completed.
- **Why it matters:** Some alerts are technically accurate but cannot be permanently remediated immediately. In those cases, repeatedly generating Autotask tickets creates noise without improving service. Jason should be able to recognize a documented known condition, preserve the real root-cause/remediation plan, and suppress only the specific monitor scope that is producing duplicate operational work.
- **Initial motivating example:** Ticket `T20260828.0045` on `APD-HYPERV` reports Datto AV as Running & Not Up-to-Date. Troubleshooting indicates the durable fix is to upgrade/replace the legacy Microsoft Hyper-V Server 2012 host. Until that OS remediation occurs, repeatedly creating identical Datto AV monitor tickets is not useful. Jason currently can read and resolve DRMM alerts but cannot disable or suppress the underlying monitor for that device.
- **Required behavior:**
  1. Identify the exact monitor, device/site scope, and currently active alert/ticket.
  2. Confirm the condition is understood and that an authoritative root-cause or accepted remediation plan exists.
  3. Require explicit technician approval before suppressing or disabling monitoring unless a future narrowly defined standing exception policy explicitly permits it.
  4. Scope the change as narrowly as possible: prefer one monitor on one device over site-wide or policy-wide suppression.
  5. Record the reason, approving technician, related Autotask ticket/problem/change record, affected device/site, monitor identity, suppression method, start time, and intended review/expiration.
  6. Support temporary suppression with an expiration/review date whenever possible; do not create indefinite silent exceptions by default.
  7. Prevent duplicate tickets/alerts for the accepted condition while preserving visibility that an exception exists.
  8. Re-enable/reassess the monitor automatically or through a governed review when the underlying remediation is completed, the expiration date is reached, device/OS state changes materially, or the documented exception is no longer valid.
  9. Verify the monitor state after modification and document the result in Autotask.
- **Safeguards:**
  - Suppression must never be used merely to make an unresolved alert disappear.
  - Jason must not suppress a broader policy/site when a device-specific exception is sufficient.
  - Security, backup, availability, or other high-impact monitors require explicit evidence and approval before suppression.
  - An accepted exception must remain discoverable in Autotask/IT Glue or another authoritative system so future technicians understand why monitoring is suppressed.
  - Suppression authority must remain separate from alert-resolution authority; resolving one alert must not silently disable future monitoring.
  - If the underlying condition changes or a new materially different failure appears, Jason must surface it rather than treating it as covered by the old exception.
- **Prerequisites:** Governed DRMM monitor/policy read capability; exact monitor identity and assignment resolution; narrowly scoped monitor enable/disable or mute/unmute action; approval policy; exception-state persistence; Autotask/IT Glue linkage; expiration/review scheduling; readback verification; audit trail.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Implement when DRMM write capabilities are expanded beyond alert resolution, and validate first against a controlled known-condition case such as `APD-HYPERV`.
- **Implementation checkpoint (2026-09-18):** Datto RMM 15.1 product UI supports device-level monitor/policy enablement toggles, but the vendor-documented REST API v2 does not currently expose a supported exact per-device monitor enable/disable mutation. Jason will fail closed rather than use an undocumented/private web endpoint, broad policy suppression, maintenance mode, or direct-provider bypass. `SUPPORT-CAP-015` tracks the provider-interface blocker.

---

## Internal knowledge and documentation controls

### TODO-KNOW-001 — AOT-wide IT Glue internal knowledge scope

- **Priority:** P1
- **Status:** Proposed
- **Risk level:** Moderate
- **Idea:** Allow Jason to use AOT's existing IT Glue policies, SOPs, standards, procedures, and operational documentation as governed internal knowledge without requiring AOT to move or reorganize documents into a new folder.
- **Scope model:** Bind the capability to the exact AOT IT Glue organization ID. Within that organization, Jason may search and read non-restricted documents and approved document attachments for operational reasoning. Existing IT Glue folder/document organization remains unchanged.
- **Restriction model:** Restricted IT Glue documents remain unavailable by default unless the authenticated requester is already authorized under the existing mirrored IT Glue ACL model or a separately governed internal-knowledge rule is explicitly approved. Passwords, credential-vault resources, secrets, and credential-like fields remain excluded. Sensitive HR, legal, payroll, financial, ownership, or similarly restricted content must not become broadly searchable merely because it resides in the AOT organization.
- **Opt-out model:** Prefer preserving existing IT Glue structure. If AOT wants to exclude otherwise non-restricted areas from Jason, support an explicit denylist of exact folder/document/resource IDs rather than requiring document migration to an opt-in folder.
- **Client isolation:** AOT internal knowledge is a separate evidence scope from client documentation. Client IT Glue content remains exact-client scoped and must never become globally searchable through the AOT internal-knowledge capability.
- **Reasoning rule:** Internal AOT documentation may guide how AOT wants work handled, but it is evidence/content rather than execution authority. IT Glue text cannot grant permissions, override Jason governance, or authorize provider mutations. Prompt-injection and untrusted-content protections remain in force.
- **Vendor-evidence rule:** AOT documentation may guide diagnosis and client communication, but product-behavior claims intended for clients should still be verified against authoritative vendor documentation when reasonably available.
- **Automatic retrieval goal:** During ticket triage and Proposed Reply generation, allow Jason to search a small, relevant subset of AOT internal knowledge based on the current issue before asking the client for information or inventing a process. Retrieval should be bounded and relevance-driven rather than loading the full document corpus.
- **Attachments:** Permit bounded read-only access to attachments only when the parent document is authorized under this scope. Parent authorization must be proven before attachment content is released.
- **Initial acceptance test:** Perform a read-only inventory of document titles/categories visible within the exact AOT IT Glue organization, prove restricted documents and credential resources remain excluded, inspect representative policy/SOP documents and attachments, prove a denied/opt-out resource remains unavailable, and verify a sample ticket can retrieve relevant AOT guidance without exposing unrelated client documentation.
- **No write authority:** This capability is read-only. It grants no IT Glue create/update/delete authority.
- **Dependencies:** Existing governed IT Glue document/search/read and attachment capabilities; exact AOT IT Glue organization identity; current information-authorization and sensitivity controls; durable opt-out configuration if required; retrieval integration with Triage Intelligence / Proposed Reply Assist.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Implement before relying on IT Glue as a default institutional knowledge source for client-ticket reasoning or client-facing Proposed Reply generation.

---
## Communication and audience controls

### TODO-COMM-001 — Governed client communication framework

- **Priority:** P1
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-04
- **Implementation state at approval:** Planned — foundation pieces exist; draft-assist and controlled client-send acceptance remain
- **Autonomous engineering readiness:** Approved
- **Authority basis:** Owner approval on 2026-10-04 authorizes autonomous engineering only within this exact TODO scope; existing Jason governance, client/provider boundaries, protected-core release approval, financial authority, and disruptive-action controls remain unchanged.
- **Risk level:** High
- **Idea:** Maintain one governed communication framework for audience policy, deterministic templates, evidence-grounded Proposed Reply assistance, and eventual approved client delivery through supported channels.
- **Why it matters:** Audience filtering, templates, reply drafting, and Autotask client notification are stages of the same communication decision and delivery pipeline.
- **Work packages:** (1) audience and communication policy; (2) deterministic templates; (3) Proposed Reply Assist; (4) controlled client delivery with exact company/contact/recipient validation and post-send evidence.
- **Promotion model:** Draft Assist -> Human-Approved Send -> Class-Based Autonomous Send -> Playbook-Authorized Communication. Formulation authority and delivery authority remain separate.
- **Required controls:** exact recipient/company validation; no blind reply-all; evidence-before-assertion; stale-draft invalidation; internal/client information firewall; safe-link validation; duplicate suppression; no unsupported commitments; client-scope isolation; post-send evidence/readback.
- **Completed prerequisite:** legacy TODO-COMM-006 enabled and production-accepted bounded NotificationHistory reads.
- **Current controlled-send boundary:** client-facing mutation remains restricted to XYZ Test Company until separately promoted from TEST mode.
- **Legacy IDs consolidated here:** TODO-COMM-002, TODO-COMM-005, TODO-COMM-006, and TODO-COMM-007.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Implement Draft Assist first, then promote delivery classes only from measured production evidence.

### TODO-COMM-004 — Governed Teams interaction and owner operations

- **Priority:** P1
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-04
- **Implementation state at approval:** In progress — approval/information-request paths are production-proven; lifecycle-card source implementation completed 2026-10-04; production acceptance and typed-override acceptance remain
- **Autonomous engineering readiness:** Approved
- **Authority basis:** Owner approval on 2026-10-04 authorizes autonomous engineering only within this exact TODO scope; existing Jason governance, client/provider boundaries, protected-core release approval, financial authority, and disruptive-action controls remain unchanged.
- **Risk level:** High
- **Idea:** Make Microsoft Teams Jason's low-volume governed interaction surface for approvals, information requests, meaningful lifecycle notifications, exceptions, and owner/technician action-required events.
- **Current evidence:** Authenticated Adaptive Card Approve/Deny flow is production-proven with single-use decision handling and replay/conflict protection. Normal authenticated Teams conversation ingress is also production-proven. Source now extends the existing governed autonomous Teams channel with concise color/severity Adaptive Cards and credential-blind lifecycle event spooling from the owner-approved development and support-repair workers. Start and blocker events are deduplicated and runtime delivery requires a provider message ID before the notification is marked delivered. Focused notifier/worker regression: 50/50 PASS; runtime composition/deployment-contract regression: 26/26 PASS.
- **Remaining work:** complete protected CI/merge/release and one controlled production lifecycle test; complete the typed-override acceptance; add deterministic Acknowledge/Retry/View Evidence interactions only where the corresponding non-LLM action contract is defined. Support-repair verified closure now emits generic `work_completed`; binding a generic TODO's production-accepted state back to that event remains part of TODO-GOV-006.
- **Usage policy:** Teams is an exception-and-approval channel, not a telemetry stream. Routine scans, diagnostics, progress chatter, and raw logs do not generate notifications.
- **Authority rule:** Teams buttons use existing Jason governance and do not create a parallel approval system. Free-form Teams conversation remains a separate model-backed path.
- **Dependencies:** TODO-GOV-006 for lifecycle/readiness state; TODO-CONN-004 for residual Teams credential/OpenClaw hardening.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Complete typed-override acceptance and then standardize lifecycle cards/delivery evidence.

### TODO-COMM-003 — Secure client portal messaging

- **Priority:** P2
- **Status:** Proposed
- **Risk level:** High
- **Idea:** Add a secure portal channel for sensitive documents, approvals, incident communications, and compliance evidence requests.
- **Why it matters:** Email and SMS are not appropriate for all content.
- **Why not now:** Requires identity, portal, retention, and client-isolation foundations.
- **Prerequisites:** portal identity, MFA, secure storage, access logging, retention policy, notification fallback.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** When sensitive outbound communications become a regular use case.

---

## Connector and execution backlog

### TODO-CONN-004 — Direct Teams gateway credential and residual OpenClaw hardening

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Complete the post-cutover security cleanup by migrating the direct Teams gateway credential from the temporary mode-0600 host file into Jason's governed secret/federated identity architecture, defining rotation/revocation, and retiring the dormant OpenClaw inbound Teams listener when outbound/proactive dependencies permit.
- **Why it matters:** The current direct ingress is production-proven, but long-term operations should not depend on a transitional host-file client secret or leave an unnecessary alternative Teams listener configured indefinitely.
- **Why not now:** Disabling OpenClaw Teams immediately could disrupt approved outbound/proactive functions, and credential migration should be governed/tested rather than rushed after the successful cutover.
- **Prerequisites:** review of OpenClaw outbound/proactive dependencies; governed Microsoft credential target (OpenBao, certificate, or federated identity); rotation/revocation procedure; rollback plan; current System Registry update/verification process.
- **Decision owner:** Technology Steward / Jason Architecture Authority
- **Review trigger:** Begin during the next Teams/OpenClaw security-hardening window; complete before the dedicated gateway client secret reaches its first planned rotation/expiry boundary.


### TODO-CONN-005 — Microsoft 365 / Entra security-posture reads

- **Priority:** P1
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-04
- **Implementation state at approval:** In progress — governed Entra posture read code deployed; production acceptance blocked by current Microsoft app consent/profile
- **Autonomous engineering readiness:** Approved
- **Authority basis:** Owner approval on 2026-10-04 authorizes autonomous engineering only within this exact TODO scope; existing Jason governance, client/provider boundaries, protected-core release approval, financial authority, and disruptive-action controls remain unchanged.
- **Risk level:** High
- **Idea:** Add narrow governed read-only capabilities for MFA registration/enforcement, Conditional Access, privileged-account MFA, legacy-authentication restrictions, Exchange Online protection configuration, external-message tagging, quarantine, attachment/link protection, and related tenant security posture.
- **Implemented checkpoint (2026-09-19):** Deployed governed `identity.authentication.methods.read`, `identity.conditional.access.search`, `identity.directory.role.search`, and `identity.directory.role.members.search`. Existing `identity.user.search` remains healthy through the same tenant-bound Microsoft path. Live authentication-method and Conditional Access probes reached Microsoft Graph and failed with HTTP 403 under the existing narrow `directory-read` application consent. Directory-role enumeration reached Graph but returned HTTP 400 and remains pending provider-contract/permission validation. No tenant consent or credential authority was broadened.
- **Current blocker:** The production Microsoft boundary/application is still intentionally pinned to the narrow `directory-read` profile (`User.Read.All`). The source catalog's separate `identity-investigation-read` profile describes the additional read permissions needed for broader identity investigation, but activating/consenting those permissions is a provider administration change and must be performed as a controlled desk session.
- **Review trigger:** Owner at a trusted workstation for Microsoft application-permission/admin-consent review; then re-run each production read independently and keep only vendor-supported/consented surfaces active.
- **Why it matters:** Enables evidence-backed cyber-insurance and security-control reviews without manual tenant inspection.
- **Origin:** Reclassified from `SUPPORT-CAP-007` on 2026-09-18 because this is a new capability/integration, not a break/fix defect.
- **Prerequisites:** least-privilege Microsoft Graph/Exchange read scopes, tenant isolation, evidence normalization, and sanitized acceptance fixtures.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** When Microsoft 365 security-posture automation becomes an approved implementation priority.

### TODO-CONN-006 — Client backup-posture reads / Datto Endpoint Backup API

- **Priority:** P1
- **Status:** Read-only production foundation complete; full-access credential profile source-built; provider-supported write operations pending
- **Risk level:** High
- **Idea:** Maintain governed provider access for backup inventory, protection coverage, last successful backup, failures, recovery points, retention/plan metadata, encryption/separation metadata where available, and restore-test evidence. Datto Endpoint Backup / UniView Backup.net is the first production implementation.
- **Implemented checkpoint (2026-09-24):** Production-accepted `backup.endpoint.asset.search/read`, `backup.endpoint.backup.search`, and `backup.backupiq.alert.search` through the validated Autotask-company-to-Backup.net-customer boundary. Controlled DGV-50859 acceptance passed through Central Orchestrator with `direct_provider_access=false`.
- **Full-access credential checkpoint (2026-09-24):** Source adds isolated logical secret `backup_net.fullaccess`, dedicated KV path/AppRole/runtime artifacts, and explicit runtime profile selection via `JASON_BACKUP_NET_ACCESS_PROFILE=full_access`. The full-access provider credential uses the same documented OAuth/API hosts while OpenBao remains least-privilege to one secret.
- **Production hardening checkpoint (2026-09-24):** SUPPORT-CONN-020 was fixed in PR #252 / source `87f9ecd60676db46fff5b815857b62a42f6b8320`. Backup.net governed reads now accept the legitimate Autotask self-company ID `0`, BackupIQ general alert searches safely default an omitted `type` to `alert`, and exact customer boundaries may be validated for provider-confirmed zero-asset customers while retaining exact asset proof when assets exist. AOT company `0` is validated to Backup.net customer `08de23b9-9685-4cdf-8932-e2318bf4412a`; live AOT-50282 asset, BackupIQ alert, and backup-history reads all succeeded with authoritative empty collections and `direct_provider_access=false`.
- **Current provider limitation:** The published Backup.net Public API OpenAPI contract advertises GET operations only as of 2026-09-24. A full-access credential therefore does not create a documented mutation endpoint. No private/UI endpoint may be substituted and no Backup.net write capability may be registered from credential permission alone.
- **Later governed actions:** Add trigger/restore/configuration or other mutations only after a provider-supported write operation is documented. Each mutation must use exact capability authority, approval where required, execution-plan binding, target/payload validation, post-write readback, retry/recovery rules, and non-disruptive/disruptive action gates.
- **Origin:** Reclassified from `SUPPORT-CAP-008` on 2026-09-18 and expanded from preserved recovery-roadmap work on 2026-09-23.
- **Remaining prerequisites for writes:** provider-documented mutation operations and schemas; risk classification; rollback/recovery semantics; controlled test target; exact JKD-001 grants; acceptance evidence.
- **Decision owner:** Platform Owner / Backup Service Owner / Jason Governance Authority
- **Review trigger:** Re-check the official Public API contract when Kaseya publishes write operations or provides an explicitly supported write contract.

### TODO-CONN-007 — Network/security-appliance posture reads

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Add governed read-only access to network/security configuration sufficient to verify segmentation, perimeter firewall posture, IDS/IPS, DMZ use, and related controls.
- **Why it matters:** Endpoint evidence alone cannot establish network control posture.
- **Origin:** Reclassified from `SUPPORT-CAP-009` on 2026-09-18.
- **Prerequisites:** supported network-provider integrations, client/site correlation, secret isolation, and normalized control evidence.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** When network posture automation becomes an approved implementation priority.

### TODO-CONN-008 — DNSFilter posture integration

- **Priority:** P2
- **Status:** Read integration production-active and governed-read accepted; DNSFilter administrative write families remain separately gated/dormant outside bounded acceptance profiles
- **Risk level:** Moderate
- **Idea:** Add governed DNSFilter posture, investigation, reporting, and future administrative capabilities without bypassing Jason authority.
- **Implemented source foundation:** REST provides unattended posture reads for mapped organizations/sites/policies/agents. DNSFilter MCP adds provider-supported OAuth investigation/admin reads for query logs, decision explanation, blocked traffic, anomaly analysis, stale/version/duplicate agent checks, site-policy drift, category coverage, and unblock-request monitoring. Both planes reject caller-supplied organization/MSP scope and use the validated Autotask-company-to-DNSFilter-organization boundary.
- **MCP contract checkpoint (2026-09-24):** Public discovery identified DNSFilter MCP server `dnsfilter-public` v0.6.0 with 107 tools. Eleven organization-bounded read capabilities are implemented. All 25 provider tools that currently require `confirm: true` are represented as dormant BUILDING write contracts and are not runtime-registered. OAuth uses Authorization Code + PKCE with durable mode-0600 token storage and a Jason callback route.
- **Boundary decision:** REST direct network/policy/agent-by-ID reads remain unregistered where the provider request cannot independently preserve exact organization scope. MCP read tools are fixed in source and receive only the server-derived mapped organization ID; there is no generic arbitrary-tool capability.
- **Why it matters:** REST supplies deterministic background posture evidence while MCP supplies provider-supported DNS forensics and an eventual governed admin plane, avoiding private/UI automation.
- **Origin:** Reclassified from `SUPPORT-CAP-010` on 2026-09-18.
- **Production checkpoint (2026-09-24):** REST/MCP source, secrets, OAuth, exact AOT boundary, read authorities, and controlled production read acceptance were completed. Governed DNSFilter reads remain active in the live capability catalog, including organization, site, policy, agent, anomaly/query, blocked-traffic, stale/version/duplicate-agent, drift, category, and unblock-request evidence. Separate bounded policy-create/delete acceptances proved the mutation framework and were then cleaned up to dormant write posture; those tests did not create general DNSFilter write authority.
- **Remaining work:** preserve exact client/network isolation for non-AOT clients before native DNSFilter evidence becomes a normal cross-client playbook dependency; complete the separately governed missing-agent installer acceptance; review each administrative write family independently before any future activation. No generic DNSFilter provider write authority is implied.
- **Current runbook:** `docs/operations/DNSFilter-Dual-Plane-Integration-2026-09-24.md`.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Complete controlled production REST/MCP read acceptance, then review individual administrative write families separately.

### TODO-CONN-009 — BullPhish/security-awareness posture integration

- **Priority:** P2
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Add a governed read capability for client enrollment, covered users, phishing/training cadence, latest completion state, and exceptions.
- **Why it matters:** Enables evidence-backed awareness-training and phishing-control verification.
- **Origin:** Reclassified from `SUPPORT-CAP-011` on 2026-09-18.
- **Prerequisites:** BullPhish/API access, client/user correlation, least-privilege credentials, and normalized campaign/training evidence.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** When security-awareness integration becomes an approved implementation priority.

### TODO-OPS-007 — Invoice-to-catalog and purchase-order workflow

- **Priority:** P1 — implement before Duo Security API integration
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-04
- **Implementation state at approval:** In progress — governed PO mutations live; lifecycle orchestration foundation implemented
- **Autonomous engineering readiness:** Approved
- **Authority basis:** Owner approval on 2026-10-04 authorizes autonomous engineering only within this exact TODO scope; existing Jason governance, client/provider boundaries, protected-core release approval, financial authority, and disruptive-action controls remain unchanged.
- **Risk level:** High
- **Idea:** Give Jason a governed procurement workflow that can read vendor invoices from an approved mailbox, reconcile invoice line items against Autotask products, services, and other catalog/inventory records, propose any required catalog additions or updates, propose purchase-order additions, and create the approved Autotask records with authoritative readback.
- **Why it matters:** Vendor invoices routinely contain products, services, licensing, hardware, freight, and other billable or inventory-related items that must be represented consistently in Autotask before purchasing and billing workflows can be completed. Automating the comparison and proposal work can reduce repetitive finance/operations effort while preserving human approval for financial commitments and master-data changes.
- **Required capabilities:**
  - governed search/read of an approved invoice mailbox and attachments;
  - reliable invoice extraction for vendor, invoice number/date, PO reference, quantities, SKU/part number, description, unit cost, extended cost, tax/freight, and totals;
  - governed Autotask product/catalog search and read;
  - governed Autotask service/service-bundle and other applicable inventory/catalog-item search and read;
  - governed creation/update of products, services, and other approved catalog/inventory item types;
  - governed purchase-order search/read/create/update;
  - company/vendor and item identity resolution;
  - duplicate detection for invoices, products, services, SKUs, and POs;
  - proposal generation that clearly separates existing matches, ambiguous matches, proposed new catalog items, proposed PO lines, and exceptions;
  - explicit approval for financial commitments and master-data creation unless a future narrowly scoped standing policy is approved;
  - post-write readback, totals verification, and audit evidence.
- **Expected workflow:**
  1. Search the designated mailbox for a new or requested vendor invoice.
  2. Parse and normalize the invoice without exposing unnecessary sensitive content.
  3. Resolve the vendor and any referenced PO/customer/project context.
  4. Compare each invoice line to existing Autotask products, services, and other supported catalog/inventory records.
  5. Reuse an existing exact/approved match where appropriate.
  6. If no safe match exists, propose a new product/service/inventory record with normalized name, vendor/SKU, description, cost, and other required fields.
  7. Compare the invoice against existing PO lines and propose additions/adjustments where necessary.
  8. Present the proposed catalog changes and PO changes for approval with invoice evidence and totals.
  9. After approval, create only the approved records through Central Orchestrator.
  10. Read back every created/updated item and PO line and verify invoice quantity/cost/total reconciliation.
  11. Preserve the invoice-to-Autotask correlation for audit and future duplicate detection.
- **Safeguards:**
  - never create a financial commitment solely because an invoice exists;
  - never silently create duplicate products/services when an equivalent approved catalog item already exists;
  - fail closed on ambiguous vendor, SKU, unit-of-measure, tax/freight allocation, or PO matching;
  - do not infer customer billability, markup, GL treatment, or accounting classification without approved policy/evidence;
  - preserve `direct_provider_access=false`, least privilege, approval, idempotency, and post-mutation verification.
- **Implementation order:** This item is intentionally ahead of `TODO-CONN-011 — Duo Security API integration`. The Duo integration requires a new API credential; the invoice/catalog/PO work should be advanced first using the existing governed Autotask and approved mailbox architecture where possible.
- **Implementation checkpoint (2026-09-20):** Governed source support and a separate explicit `itglue-autotask-entra-procurement-catalog-v5` read profile now exist for Products, ProductVendors, Services, ServiceBundles, PurchaseOrders, and PurchaseOrderItems without broadening the production v4 profile. Live shadow acceptance through Jason identity/authority and Central Orchestrator proved Product, ProductVendor, ServiceBundle, PurchaseOrder, and PurchaseOrderItem reads. The dedicated read identity reports `userAccessForQuery=All` for those entities. `Services/entityInformation`, however, returns `canQuery=true` with `userAccessForQuery=None`, and three governed Services query variants all fail at Autotask with HTTP 500. Autotask's current Services REST documentation states that query has no restrictions, and the assigned custom API security level already has the available read permissions enabled. The Services blocker is therefore tracked as provider/API inconsistency `SUPPORT-CAP-017`, not as a known missing security-level checkbox. All tested procurement entities currently report create/update access `None` for the read identity. No production profile, Autotask permission, or provider mutation was changed. Financial/catalog writes must use a separate least-privilege write identity/profile and remain inactive until controlled acceptance.
- **Production activation checkpoint (2026-09-20):** Governed product, product-vendor, service, service-bundle, purchase-order, purchase-order-item, and purchase-order-receive actions are live in production through `execute_governed_capability`. All 13 procurement actions are exact-grant, owner-scoped, `approval_required=true`, single-attempt, provider-preflighted, and post-write readback verified. Production image `jason-mcp:procurement-write-25a92b8`; source commit `25a92b80cac8239a12fd48641f2a015a1037d340`. Purchase-order completion follows the provider-native lifecycle: create PO -> create items -> submit PO -> receive each item through `PurchaseOrderItemReceiving`; Autotask derives Received Partial/Full rather than allowing Jason to patch directly to Received Full.
- **Lifecycle orchestration checkpoint (2026-09-20):** Added canonical playbook `docs/playbooks/Jason-Procurement-PO-Lifecycle.md` and deterministic allocation/ticket-presentation foundation. The workflow requires ticket candidates to be shown as `ticket number — title`, treats ticket association separately from customer billing, and requires every ordered unit to have an explicit destination. Example acceptance invariant: `2 ordered = 1 customer/ticket + 1 AOT inventory`, with billable quantity `1`. Vendor email/ETA/shipping events are designed to flow through Teams approval before material PO changes. Missing mailbox-content reads and dedicated ticket-billing/charge capability are explicit dependencies rather than hidden assumptions.
- **Decision owner:** Jason Governance Authority / Finance/Operations Owner
- **Review trigger:** Begin immediately after the current support-list blockers being actively worked are stabilized enough for safe implementation.

### TODO-CONN-011 — Duo Security API integration

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Add a governed Duo Security integration so Jason can read Duo tenant posture and support Duo-related troubleshooting, deployment, enrollment, and verification workflows using authoritative Duo evidence.
- **Why it matters:** Endpoint installation alone does not prove a user/device is correctly enrolled, protected, or successfully authenticating.
- **Current evidence (2026-09-20):** Live Jason capability discovery exposes Entra MFA/authentication reads but no Duo provider capability.
- **Initial scope:** Read-only tenant/integration health, users, enrollment/device state, bypass/disabled state, and relevant authentication evidence. Future security-changing Duo actions require separate governance.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Begin after the read-only credential and tenant-binding design is approved.

### TODO-CONN-013 — Governed mailbox evidence and approved-mailbox lifecycle

- **Priority:** P1
- **Status:** Source-ready — blocked on the dedicated Microsoft mail-read application, Exchange Application RBAC assignment, and approved-mailbox allowlist activation
- **Risk level:** High
- **Idea:** Give Jason bounded Microsoft 365 mailbox/message evidence for explicitly approved AOT mailboxes and one safe, idempotent lifecycle for adding future approved mailboxes without broadening tenant-wide mail authority.
- **Why it matters:** Procurement, NDR/failure-report correlation, vendor ETA/shipping updates, invoices, and other operational workflows often depend on mailbox-only evidence. The mailbox-add helper is lifecycle management of the same capability.
- **Read behavior:** resolve the exact approved mailbox; search bounded windows/participants/subjects/identifiers; read only necessary content and attachment metadata; preserve message IDs/timestamps/digests; redact unnecessary sensitive content.
- **Approved-mailbox lifecycle:** validate mailbox existence; extend the existing Exchange Application RBAC resource scope and Jason allowlist without broadening unrelated scope; preserve the app/certificate/service-principal identity; prove the new mailbox is readable and a known unapproved mailbox remains denied.
- **Governance:** no tenant-wide arbitrary mailbox reads; do not use an organization-wide Entra Graph Mail.Read application grant when Exchange Application RBAC is the intended scope control; direct_provider_access=false.
- **Existing source foundation:** bounded message search/read and attachment metadata contracts plus a separate Microsoft mail client boundary and explicit mail-read permission profile.
- **Acceptance:** activate one controlled mailbox and correlate one bounded operational message; then add a second approved mailbox through the idempotent helper and re-prove allow/deny boundaries.
- **Legacy ID consolidated here:** TODO-CONN-014.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Resume when the dedicated scoped Microsoft mail-read identity/RBAC setup is ready for controlled activation.

### TODO-CONN-015 — Governed Autotask contract read/write capability

- **Priority:** P1
- **Status:** Read phase production-proven 2026-09-25 — write phase blocked by current Autotask update permission
- **Risk level:** High
- **Idea:** Add governed Autotask contract capabilities so Jason can search and read contracts and related contract-service/billing details, then support tightly controlled contract updates where the Autotask API permits them.
- **Why it matters:** Contract visibility is required for vendor-cost reconciliation, client profitability analysis, billing validation, service reconciliation, and accurate operational decisions that depend on what AOT is actually contracted to provide and bill.
- **Why not now:** The live Jason capability registry currently exposes no `service_contract` capability, and contract mutations require explicit schema validation, least-privilege authorization, approval controls, idempotency, audit evidence, and safe test coverage before production use.
- **2026-09-25 read-phase checkpoint:** Live Autotask `Contracts` entity metadata proves `canQuery=true` with `userAccessForQuery=All`; the current Jason read identity has `userAccessForCreate=None`, `userAccessForUpdate=None`, and `userAccessForDelete=None`. Contract fields include exact queryable `companyID`, `contractName`, `contractNumber`, `status`, `contractType`, `contractCategory`, `startDate`, and `endDate`. Source now defines provider-neutral `service.contract.search` and `service.contract.read` on the existing bounded generic Autotask entity adapter. Search requires exact `company_id`; exact read requires both `company_id` and `resource_id` and compiles to a bounded Contracts query containing both fields, preventing an ID-only cross-client read. Raw provider search expressions are rejected, page size is bounded, and durable-ID continuation is supported. Existing v5/v6 provider-read profiles are frozen to pre-contract authority; only the new explicit `itglue-autotask-entra-procurement-mail-contract-catalog-v7` profile activates the contract reads. Write capability design is intentionally deferred because the current identity has no update permission.

- **2026-09-25 activation hardening:** First v7 activation correctly exposed the contract capabilities but live MCP acceptance stopped with `client_context_required` for the organization-scoped Owner identity. Review then found a defense-in-depth gap: capability-level client isolation required a non-empty client context but did not yet prove the requested Autotask `company_id` matched that context. Production was immediately rolled back to v6 while retaining the merged source dormant. The follow-up fix binds contract `company_id` exactly to the governed client context before argument adaptation/provider invocation and allows an organization-scoped owner to derive temporary client context only after an exact governed `service.company.read` plus Jason authority evaluation for that same company ID. Caller-supplied arbitrary `client_id` remains unsupported.

- **2026-09-25 production acceptance:** Hardened v7 was redeployed on runtime and MCP from source revision `cb87d278fb9d9b828672e4158dad01c5d43d0ead`; both deployment health checks and MCP governance post-check passed. Normal MCP `service.contract.search` for Atomic Plumbing / Autotask company `333` returned three active contracts. Exact `service.contract.read` for company `333`, contract `29683369` returned exactly one Atomic contract. Repeating the exact same contract ID under company `311` returned zero items, proving the company-bound selector prevents cross-client disclosure. The accepted read surface remains read-only and client-isolated. No contract mutation capability is active because live Autotask metadata reports `userAccessForUpdate=None` for the current identity.

- **2026-09-25 owner-context refinement:** Provider-read authority is intentionally OBSERVE-only, so ADMINISTER cannot be used as a provider-read client-selection gate. The owner selector now reuses Jason's existing authenticated `approval_owner_identities()` allowlist. Only an organization-scoped owner may derive temporary contract client context; exact governed company verification and a normal OBSERVE authority decision for that same client/capability are still required. Non-owner organization-scoped identities fail closed before company resolution.

- **2026-09-25 scoped-context refinement:** JKD-001 grants are deliberately client-exact, so an organization-scoped OBSERVE grant cannot be reused directly with `client_id=333`. The production-safe owner path therefore derives no durable grant. After owner allowlist validation, exact governed company verification, and a successful organization-scoped OBSERVE authority decision for the exact contract capability, MCP persists a one-minute OBSERVE-only execution context narrowed to that company/capability. Central Orchestrator validates the derived context normally, and the provider-read adapter still independently enforces `request.client_id == arguments.company_id` before provider invocation.

- **2026-09-25 production acceptance:** v7 was deployed from merge `cb87d278fb9d9b828672e4158dad01c5d43d0ead` with MCP health, hardening, image promotion, and governance post-checks passing. A bounded live search for Atomic Plumbing & Drain Cleaning (`company_id=333`, active contracts only) succeeded through `service.contract.search` / Autotask and returned three active contracts; correlation `corr_contract_client_59cad15b3f8840aca2e6b53883f7e816`. An exact read of default MSA contract `29683369` using both `company_id=333` and `resource_id=29683369` then succeeded through `service.contract.read`; correlation `corr_contract_client_2f252990f14a45d99f01b63ac93ca087`. Direct provider access remained disabled and no mutation occurred. The baseline contract read phase is therefore production-proven. Contract create/update/delete remain intentionally unavailable because the current Autotask identity reports `userAccessForCreate=None`, `userAccessForUpdate=None`, and `userAccessForDelete=None`; no write capability should be introduced until least-privilege provider permission and mutation governance are separately approved and accepted.
- **Prerequisites:** confirm Autotask contract and contract-service API entities and field permissions; implement governed read/search first; validate client isolation and pagination; add sanitized contract fixtures and contract tests; define allowed write fields and preconditions; require explicit approval for mutations; add audit, rollback/reconciliation, and verification behavior.
- **Decision owner:** Platform Owner / Jason Governance Authority
- **Review trigger:** Start as a high-priority near-term connector enhancement; prioritize read capability first, then controlled write/update support after successful validation.

### TODO-CONN-016 — Expand governed Datto EDR response actions

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Critical
- **Idea:** Expand Jason's Datto EDR integration beyond read visibility and AV scan initiation to include governed endpoint isolation/revert and quarantine-response actions where the Datto API supports them.
- **Why it matters:** Jason can already investigate detections, quarantine state, policies, security status, and scan history. Adding tightly governed response actions would let approved playbooks contain active threats without requiring a technician to leave the workflow for routine EDR response steps.
- **Target capabilities, in priority order:** endpoint isolate; revert isolation; quarantine file/detection; restore quarantined file; delete quarantined file; terminate malicious process; later, narrowly controlled EDR/AV policy changes.
- **Important rule:** Before reverting isolation, Jason must identify which product imposed the isolation (Datto EDR, Datto RMM, RocketCyber, or another source) and must not attempt to release isolation through the wrong product.
- **Why not now:** Only Datto AV scan start is presently exposed as a governed security action. Each additional EDR mutation must first be confirmed against the supported Datto API and proven with safe test targets.
- **Prerequisites:** verify exact API endpoints and permissions; implement provider-native read-before-write checks; exact endpoint identity correlation; explicit per-action approval for isolation/release and destructive quarantine actions; idempotency and preconditions; client isolation; audit/evidence capture; rollback/recovery behavior; post-action verification; playbook-level autonomy gating.
- **Decision owner:** Security Owner / Jason Governance Authority
- **Review trigger:** Treat isolation/revert and quarantine management as the next high-priority Datto EDR API expansion after API capability verification.

### TODO-CONN-017 — Governed Datto RMM monitor-policy targeting updates

- **Priority:** P1
- **Status:** Proposed
- **Risk level:** Moderate
- **Idea:** Add a governed Jason capability to read and modify Datto RMM monitor/policy targeting so Jason can exclude Linux endpoints from Windows-only monitors and apply OS-appropriate monitoring safely.
- **Why it matters:** A Linux endpoint can inherit Windows-oriented AV/filesystem monitors, producing false alerts and failed Windows/PowerShell response attempts. Jason can diagnose and clear resulting alerts today, but cannot correct the monitor assignment through the governed action layer.
- **Why not now:** The current live capability registry exposes alert read/resolve and site-variable actions, but no monitor-policy mutation capability.
- **Prerequisites:** Datto RMM API support for monitor/policy assignment changes; capability registry contract; OS-targeting guardrails; approval and audit policy; readback verification; test coverage against Linux and Windows endpoints.
- **Decision owner:** Jason Governance Authority / MSP Operations
- **Review trigger:** Before relying on Jason to autonomously remediate recurring monitor-policy false positives.

### TODO-OPS-008 — Governed Autotask ticket billing/charge workflow

- **Priority:** P1
- **Status:** Implemented — live governed TicketCharges read/create/update; controlled split-allocation acceptance pending
- **Risk level:** High
- **Idea:** Add an explicit governed capability to add and verify the correct billable product/charge to an exact Autotask ticket after a procurement allocation is approved.
- **Why it matters:** AOT may order multiple units while only some are customer-billable. PO quantity must never be copied blindly to ticket billing.
- **Required behavior:** Resolve exact ticket and display `ticket number — title`; resolve approved product/service and selling price; check existing ticket charges for duplicates; accept an explicit billable quantity that may be lower than PO quantity; create the charge only after approval; read back quantity/price/product/ticket association; document the procurement linkage.
- **Safeguard:** Ticket association is not billing approval. AOT inventory allocations must never be customer billed. Unknown markup/selling price or ambiguous billing policy fails closed.
- **Production verification (2026-09-20):** Live capabilities `service.ticket.charge.search`, `service.ticket.charge.read`, `service.ticket.charge.create`, and `service.ticket.charge.update` are active. Create/update remain high-risk and `approval_required=true`. A harmless bounded `service.ticket.charge.search` against controlled test ticket ID `7680` succeeded through governance with correlation `corr_mcp_ceb63529e09740178e74c797bd3851b3`, returning three existing TicketCharges and proving duplicate-check evidence is available before any new charge is proposed. No charge mutation was performed.
- **Acceptance test:** Controlled test with quantity 2 ordered, quantity 1 allocated/billed to a test customer ticket, quantity 1 retained as AOT inventory; verify only one customer charge exists.
- **Decision owner:** Jason Governance Authority / Finance/Operations Owner
- **Review trigger:** Implement before declaring TODO-OPS-007 end-to-end complete.

### TODO-FIN-002 — QuickBooks Online integration with provider-native financial authorization

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Critical
- **Idea:** Implement QuickBooks Online as a governed financial-data provider. Human access must require all four gates: authorized Jason user, Microsoft Entra-authenticated requester identity, sufficient QuickBooks Online user permission for the requested data/action, and independent Jason governance approval/policy for the requested operation.
- **Authority rule:** Effective permission is the intersection of Jason access, verified Entra identity, QuickBooks Online permission, and Jason governance. Jason Admin/Owner roles must never implicitly elevate QBO permissions, and a shared/service QBO credential must never become the source of interactive human authority.
- **First acceptance test:** In the QBO sandbox, determine whether OAuth/API calls actually preserve and enforce the authorizing QBO user's native role/permissions. If native enforcement is absent or ambiguous, fail closed and use a synchronized permission projection/cache derived from QBO user permissions instead.
- **Initial scope:** Read-only financial data. Mutations such as invoice changes, vendor changes, payments, refunds, credits, voids, bank-account changes, or other movement-of-money actions require separate governed capabilities and stronger approval controls.
- **Acceptance criteria:** requester is an authorized Jason user; requester identity is Entra-verified; requester maps to a QBO user/company context; requested object/field/action is permitted by QBO-native permission or a fail-closed projection derived from it; Jason governance independently authorizes the operation; shared/service credentials do not broaden disclosure/action authority.
- **Decision owner:** Jason Governance Authority / Finance Owner
- **Review trigger:** Begin with sandbox authorization-behavior proof before any production credential or financial-data activation.


### TODO-FIN-003 — Continuous credit-card reconciliation with statement ingestion and Teams exception workflow

- **Priority:** P3 until QuickBooks Online production API access is available; review for P1/P2 immediately when `TODO-FIN-002` reaches usable production read access
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-06; pre-QBO work authorized; production accounting actions blocked on governed QBO capability
- **Risk level:** High
- **Idea:** Build a provider-neutral continuous credit-card reconciliation workflow so Jason correlates purchases and supporting evidence during the month, treats the issuer statement as the authoritative period-end control document, and routes only unresolved exceptions to the responsible reconciler or cardholder through the existing Microsoft Teams notification/card framework.
- **Operating model:** Chat or approved-mailbox statement ingestion starts/finalizes the statement cycle; Jason performs deterministic extraction, normalization, duplicate prevention, control-total verification, and evidence correlation; Teams handles bounded human questions and approvals; governed QuickBooks capabilities later perform/verify the accounting-side reconciliation.
- **Why it matters:** AOT's prior spreadsheet process compensated for the delay between purchase activity and month-end reconciliation. Jason should reduce that delay by correlating evidence continuously so statement close becomes verification rather than reconstruction.
- **Excel transition rule:** Lori's existing reconciliation spreadsheet is not a required architectural dependency or future system of record. During initial acceptance it may be used only as a comparison/reference source to prove Jason is not losing information. Retire it from the operational workflow after successful parallel validation.
- **Statement sources:** Support manual PDF upload in chat as the baseline. When `TODO-CONN-013` approved-mailbox evidence is available, support issuer statement delivery by email/attachment as an automatic trigger. Secure-link-only issuer notifications must fail closed unless a separately approved retrieval method exists.
- **Canonical statement record:** Preserve issuer, account/card identity using a non-sensitive stable identifier, statement period, closing date, payment due date where useful, previous balance, payments/credits, purchases/new charges, fees, interest, new balance, source fingerprint, ingestion timestamp, source provenance, and reconciliation state.
- **Canonical transaction record:** Preserve statement transaction date, posting date when present, merchant/description, amount, cardholder/card identifier, transaction type, source statement, evidence links, proposed accounting treatment, match confidence, resolution state, and human decisions with provenance.
- **Control-total invariant:** Extracted transaction classes must reconcile exactly to issuer statement totals before the statement can be marked structurally valid. Payments/credits, purchases, fees, and interest remain distinct accounting classes and must not be silently netted into expenses.
- **Continuous correlation inputs:** Reuse governed evidence from Autotask tickets, POs, ticket charges, quotes/procurement records, approved vendor invoices/mailbox evidence, vendor/API metadata, and other authoritative Jason sources. Future QBO/Smart Accounting Hub/ConnectBooster evidence may be added only through governed connectors and explicit provider contracts.
- **Teams exception workflow:** Reuse the existing Teams interaction framework rather than build a separate reconciliation UI. Present only unresolved/ambiguous items with merchant, date, amount, cardholder, proposed match/category, confidence, and supporting evidence. Supported dispositions should include approve proposal, choose alternate category/match, request receipt/evidence, ask cardholder, split transaction, mark non-business/personal where policy permits, or escalate for accounting review.
- **Cardholder routing:** When the missing fact belongs to the cardholder, Jason may route a tightly scoped Teams question directly to that person and return the answer/evidence to the reconciliation record; Lori or the assigned reconciler should not be forced to act as a messenger unless policy requires it.
- **Follow-up behavior:** Maintain one durable reconciliation/exception state per item, avoid duplicate notifications, update the existing Teams interaction where practical, and reuse the approved finance-exception reminder/escalation behavior rather than creating a separate nagging system.
- **Pre-QBO work authorized now:** Define schemas and state machine; implement/test statement PDF extraction and normalization; implement source fingerprinting/idempotency; build deterministic control-total checks; build continuous evidence-correlation interfaces; define Teams exception payloads and routing; create sanitized regression fixtures from representative statements; produce dry-run reconciliation reports; and wire approved-mailbox statement detection when the mailbox connector is available.
- **Pre-QBO prohibitions:** Do not perform QuickBooks writes, bank/card account changes, payments, refunds, credits, voids, or other movement-of-money actions; do not claim final accounting reconciliation without authoritative QBO evidence; do not broaden mailbox or provider access to obtain statements.
- **QBO activation phase:** After `TODO-FIN-002` proves governed production access, add QBO transaction/account matching, duplicate detection, proposed coding/matching, governed write capabilities only where separately approved, post-write readback, and final statement-to-QBO reconciliation verification.
- **Acceptance criteria:** (1) a representative statement PDF can be ingested twice without duplicate statement/transaction creation; (2) transaction totals exactly reconcile to statement control totals; (3) cardholder identity and transaction provenance survive normalization; (4) known evidence can clear high-confidence items without human interaction; (5) only exceptions reach Teams; (6) human responses resume the same reconciliation item rather than creating parallel state; (7) a sanitized regression fixture catches extraction/control-total regressions; (8) after QBO activation, final close requires authoritative QBO readback.
- **Decision owner:** Jason Governance Authority / Finance Owner
- **Authority basis:** Owner approval on 2026-10-06 authorizes autonomous engineering only within this TODO's pre-QBO scope and later QBO integration only through separately active governed QBO capabilities. Existing financial authority, identity, provider-boundary, approval, audit, and protected-production controls remain unchanged.
- **Review trigger:** Keep low priority before QBO production API readiness. Re-prioritize immediately when `TODO-FIN-002` reaches usable governed production read access or if finance operations requests an earlier dry-run pilot.

---

## Governance and operational maturity

### TODO-GOV-001 — Technology Steward review automation

- **Priority:** P2
- **Status:** Proposed
- **Risk level:** Low
- **Idea:** Periodically review dependent platforms for new capabilities, API changes, deprecations, and opportunities to retire custom Jason functionality.
- **Why it matters:** Supports the principle of integrating before innovating and prevents unnecessary custom-code accumulation.
- **Why not now:** Requires connector inventory, ownership, and review cadence.
- **Prerequisites:** dependency registry, vendor feed sources, review workflow, retirement criteria.
- **Decision owner:** Technology Steward
- **Review trigger:** After the first production connectors are operational.

### TODO-GOV-002 — Capability retirement and deprecation process

- **Priority:** P2
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-03
- **Risk level:** Moderate
- **Idea:** Define how capabilities are deprecated, replaced, migrated, and removed.
- **Why it matters:** Prevents undocumented drift and abandoned features.
- **Autonomous engineering readiness:** Approved
- **Approved scope:** Build the generic configuration/registry-driven capability and provider deprecation/retirement process, dependency and usage checks, replacement binding, migration-state tracking, CI/documentation enforcement, and deterministic retirement eligibility. Do not delete provider-side client data or broaden unrelated execution authority.
- **Authority basis:** Owner approval of this TODO authorizes the subordinate backend/configuration work required to implement the approved scope, subject to the Jason Constitution and existing policy. No separate approval is required for ordinary implementation plumbing that remains inside this scope.
- **Required capabilities:** Existing capability/provider lifecycle registries, System Registry dependency graph, audit/usage evidence where available, CI/release controls, and documentation control plane. Missing subordinate implementation primitives may be built under this TODO when they do not expand scope or violate policy.
- **Retirement rule:** Jason may autonomously retire a capability only when authoritative evidence proves **no active consumer/dependent still uses it** and a **replacement is already implemented, production-accepted, and tested**. If either condition is unknown, incomplete, ambiguous, or false, retirement fails closed and remains non-retired. Deprecation/migration preparation may proceed autonomously within the approved scope.
- **Acceptance test:** Use a bounded synthetic or non-production capability dependency fixture to prove: an in-use capability cannot retire; a capability with no replacement cannot retire; a replacement that exists but is not production-accepted/tested cannot authorize retirement; a capability with zero active consumers and an accepted/tested replacement can retire; the replacement relationship and retirement evidence are durable; and stale/retired references are rejected or migrated safely. Prove rollback/reinstatement behavior before applying the process to a material production capability.
- **Open questions:** None for initial implementation.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Review only if retirement would require provider-side destructive action, constitutional/policy change, materially broader authority, or a future proposal to retire capabilities without a proven replacement.

### TODO-GOV-003 — Formal risk taxonomy for requests and communications

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Establish deterministic low, moderate, high, and critical risk classifications with required controls.
- **Why it matters:** Approval, second-model review, human escalation, and channel restrictions depend on consistent risk classification.
- **Why not now:** Initial policy scaffolding exists but needs organization-specific validation.
- **Prerequisites:** stakeholder review, examples, test matrix, policy ownership.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Before any production write or external communication capability is enabled.

### TODO-GOV-004 — Independent credential and recovery backup

- **Priority:** P1
- **Status:** Proposed
- **Risk level:** High
- **Idea:** Establish an independently secured, off-host backup/recovery mechanism for critical Jason credential and trust material, including OpenBao recovery/backup material and other non-recreatable or operationally expensive identity material where appropriate. GitHub must continue to contain only non-secret configuration, references, and recovery instructions.
- **Why it matters:** A complete loss of the Jason host should not require undocumented local state. Even when external-provider credentials can be recreated, an independent recovery package reduces recovery time and preserves continuity without weakening the rule that secrets never belong in source control.
- **Why not now:** Current pilot credentials can be recreated from their external provider control planes if necessary, so this is not a blocker for the present pilot. The backup design should be implemented deliberately with appropriate encryption, custody, access control, rotation, and restore testing rather than copying secret material ad hoc.
- **Prerequisites:** approved off-host secure storage; encryption-at-rest and in-transit design; named custody/authority model; backup scope classification; secret-safe inventory/references in the System Registry; rotation/revocation handling; documented total-host-loss recovery procedure; periodic restore test; evidence that backup artifacts never enter GitHub, normal documentation, logs, or chat.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Before Jason becomes materially difficult to reconstruct by reissuing credentials, before multi-host/production expansion, or during the next formal disaster-recovery review.

### TODO-GOV-005 — Deterministic recurring constitutional and compliance certification

- **Priority:** P1
- **Status:** In progress — recurring deterministic runner, configurable 30-day cadence, material-change gating, dedicated observe-only provider canaries, and PASS-only snapshot integration are implemented in source; production scheduler acceptance remains pending
- **Risk level:** Moderate
- **Idea:** Build a deterministic, evidence-backed certification job that regularly verifies Jason remains compliant with the J-002 Constitution and other defined production compliance controls. The default scheduled cadence should be monthly, but the cadence must be configurable without code changes. Material governance, authority, identity, provider-boundary, recovery, or production-topology changes should also be able to trigger an out-of-cycle certification.
- **Why it matters:** Constitutional certification is state-dependent. A repeatable job reduces dependence on ad hoc human review, detects governance drift early, creates comparable evidence over time, and gives AOT a durable record that Jason's production controls remain intact.
- **Why not now:** The current 2026-09-26 constitutional certification and 2026-09-27 production-host reconciliation are complete, so this is not a present production blocker. The next step is to convert those proven checks into a reusable deterministic certification harness rather than repeatedly performing the review manually.
- **Required design:** deterministic checks must produce explicit `PASS`, `FAIL`, or `NOT PROVEN` outcomes; AI may summarize or evaluate only requirements that cannot safely be reduced to deterministic assertions; AI must never override a deterministic failure or missing-evidence result into `PASS`; every run must retain the authoritative source revision, runtime revision, evidence package, check results, exceptions, and final certification status.
- **Initial deterministic scope:** J-002 article evidence coverage; authoritative GitHub revision; System Registry consistency; Central Orchestrator authority; `direct_provider_access=false`; identity/authorization boundaries; approval and execution-plan protections; immutable production service paths; failed systemd units; Prometheus target health; provider-boundary governed read smokes; recovery/OpenBao/OpenClaw health; required regression/security tests; and any formally registered constitutional exceptions.
- **Cadence:** Monthly by default; configurable through governed configuration rather than source edits. Support explicit out-of-cycle runs after material constitutional architecture, authority, identity, provider-boundary, recovery, or production-topology changes.
- **Certified rollback snapshot:** After, and only after, a CCC run reaches a final `PASS`, automatically create or promote a secret-safe, restore-verified **Last Known Compliant** recovery point tied to the exact authoritative source revision and production runtime state. Reuse Jason's existing release/recovery/checkpoint machinery rather than inventing a parallel backup system. The snapshot should preserve the exact release identity, governed configuration/policy references, System Registry/evidence state required for reconstruction, container/image identities or equivalent immutable deployment artifacts, recovery-package checksums, and the CCC evidence/report. A `FAIL` or `NOT PROVEN` run must never replace the previous Last Known Compliant pointer. Restoration to that point remains a separately governed action and must preserve evidence generated after the snapshot rather than erasing audit history.
- **Prerequisites:** canonical J-002 article-to-check mapping; stable machine-readable certification result schema; governed configuration for cadence; evidence retention location; material-change trigger definition; production-safe provider smoke set; reporting/notification path; integration with the existing release/recovery pipeline and accepted-checkpoint format; deterministic Last Known Compliant pointer/manifest; restore verification; regression tests for the certification harness itself.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Begin implementation before the next scheduled constitutional recertification or sooner if a material production/governance change occurs.

### TODO-SEC-005 — Activate secure Grafana credential management

- **Priority:** P1
- **Status:** Planned — resume week of 2026-09-21
- **Risk level:** High
- **Idea:** Complete production activation of the secure Jason Credential Management dashboard and dedicated OpenBao credential-control service implemented in commit `bdb758d`.
- **Why it matters:** Provides a governed, secret-safe operator workflow for adding and rotating approved provider API credentials without placing secret values in chat, GitHub, Prometheus, dashboard JSON, or audit records.
- **Current blocker:** One-time interactive OpenBao administrative bootstrap must be performed while the Owner is at a trusted workstation. Jason's existing provider identities correctly cannot create or broaden the required policy/AppRole.
- **Remaining acceptance:** Run the OpenBao bootstrap interactively; deploy the credential-control service; create the Grafana secure datasource; verify secret-safe provider inventory; perform one controlled credential rotation/validation; prove the previous OpenBao KV version remains available for rollback; run secret-leak checks; complete documentation and Grafana evidence.
- **Prerequisites:** Owner available at a trusted workstation with OpenBao administrative credentials. Do not request or transmit the OpenBao admin password through chat.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Week of 2026-09-21 when the Owner is back at a trusted workstation.

### TODO-OPS-005 — Client Security/Posture Review

- **Priority:** P1
- **Status:** Production baseline implemented 2026-09-25 — mapped-client review/report and aggregate Grafana telemetry accepted
- **Risk level:** Moderate
- **Idea:** Periodically or on demand evaluate one authorized client against AOT's managed-security baseline using only authoritative governed evidence, then produce a gap report and improvement proposals without automatically changing client systems.
- **Classification:** Every control must be `confirmed_good`, `confirmed_gap`, `unknown`, `not_applicable`, or `evidence_unavailable`. Missing evidence never means healthy.
- **Initial controls:** BitLocker, managed AV/EDR, supported OS, DRMM monitoring, VulScan, DNSFilter, backup coverage/recent success, Microsoft MFA/Conditional Access, and documentation completeness.
- **Implemented checkpoint:** `implementation/orchestrator/client_security_posture.py` defines the deterministic baseline/evaluator. Tests prove missing evidence cannot become good, unavailable evidence remains distinct, mixed evidence fails to a gap, and confirmed gaps create proposals rather than automatic changes. Architecture contract: `docs/architecture/Jason-Client-Security-Posture-Review.md`.
- **Production checkpoint (2026-09-19):** Controlled `XYZ Test Company` resolved to exact Autotask company ID `1158`. Company-bound Autotask configuration evidence succeeded. Exact-name DRMM site discovery returned no site, and IT Glue organization evidence was denied by the information-release gate; both are correctly represented as `evidence_unavailable` rather than guessed or cross-client substituted. Client binding now requires exact Autotask identity and treats absent provider mappings as unavailable.
- **Production checkpoint (2026-09-19, mapped client):** Atomic Plumbing & Drain Cleaning is independently bound as Autotask company `333` ↔ DRMM site UID `a6af04fc-2e2a-4236-82ca-9d47ac616524`. Exact endpoint evidence on `Atomic-50291` proved current AV/EDR health and exact endpoint alert reads. The evaluator now requires complete client coverage before any healthy sample becomes `confirmed_good`; one authoritative unhealthy observation can still establish a gap. Account-level DRMM alert search was observed returning cross-site results despite a site selector and is excluded from posture evidence.
- **Production acceptance (2026-09-25):** Atomic Plumbing & Drain Cleaning is bound across Autotask company `333`, DRMM site `a6af04fc-2e2a-4236-82ca-9d47ac616524`, DNSFilter organization `1110483`, and Endpoint Backup customer `08dd6091-d9a8-499f-89aa-f9579896952f`. Complete DRMM discovery returned 29 resources / 25 Windows endpoints. The accepted deterministic review produced 2 confirmed gaps, 5 unknowns, 5 evidence-unavailable controls, and zero confirmed-good controls. Managed AV and OS support are confirmed gaps. Partial DNS/backup evidence remains unknown. Monitoring/VulScan/Microsoft/IT Glue controls remain unavailable where exact scope or provider evidence cannot be proven. A durable normalized report plus secret-safe Prometheus/Grafana aggregate view are implemented. No remediation authority is granted.
- **Ongoing coverage work:** prove Atomic's exact Microsoft tenant mapping; expose a client-scoped VulScan posture read/binding; obtain IT Glue organization evidence through the existing information-release approval path; fix/replace the DRMM account alert search path that ignores site scoping; define AOT's explicit backup-recency threshold before promoting backup recency from unknown to good/gap. These are evidence-coverage improvements, not blockers to the production baseline evaluator/report.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Continue immediately with client-bound evidence mapping.


### TODO-OPS-009 — Human-review handoff to Help Desk I

- **Priority:** P1
- **Status:** Implemented and merged in PR #368; controlled production acceptance still required
- **Risk level:** Moderate
- **Idea:** When Jason reaches a terminal or sticky state where the next meaningful action belongs to a human technician, automatically hand the Autotask ticket from the Jason queue to **Help Desk I**, set the ticket to **Human Review**, document the handoff, verify the queue/status change, and release Jason's active-work slot.
- **Why it matters:** A ticket awaiting human review should not remain in the Jason queue or consume Jason's active-work capacity. Standardized handoff makes responsibility visible to technicians and prevents stalled security/escalation tickets from being mistaken for autonomous work still in progress.
- **Current production example:** `T20260925.0050` / Atomic-50291 reached the Datto EDR/AV human-review gate after automated containment and verification. The intended live handoff write to Help Desk I was blocked before provider execution by the current safety/governance path, so the production acceptance is not yet complete.
- **Required behavior:** Create a concise internal handoff note; move the ticket to Help Desk I; set status Human Review; preserve Remote Support, device association, priority, and classification; require post-write readback; persist `handoff_reason=human_review`; release the active-work slot; prevent immediate auto-reclaim until the blocker changes or a technician explicitly returns the ticket to Jason.
- **Current blocker:** Implementation is merged and source-tested. Live governed Autotask metadata now proves Help Desk I queue `29682833` and Human Review status `37` are active. Production-equivalent MCP lifecycle coverage and focused autonomy/red-team suites pass. Only one controlled live handoff remains to prove the provider write/readback, internal note, slot release, field preservation, and anti-reclaim behavior.
- **Implementation checkpoint (2026-09-26):** human_review is the canonical handoff reason; legacy human_intervention_required is accepted as an alias. The server-controlled handoff resolves the destination to **Help Desk I + Human Review** while other handoff reasons retain trusted pre-claim restoration. Claim-store blocker fingerprints prevent immediate reclaim for an unchanged human-review blocker.
- **Remaining acceptance:** Run one controlled production handoff with provider write/readback evidence. Pre-acceptance evidence is recorded in `docs/sessions/Human-Review-Handoff-Preacceptance-2026-09-26.md`; no further source or provider-metadata blocker remains.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Run one controlled production handoff when the owner is available for the bounded acceptance window or when an equivalent pre-approved non-disruptive test ticket is designated.

### TODO-COMMS-004 — Microsoft Teams voice-call conversation with Jason

- **Priority:** P2
- **Status:** Proposed
- **Risk level:** Moderate
- **Idea:** Add a Teams calling/bot capability so an authorized AOT user can have a real-time two-way voice conversation with Jason inside Microsoft Teams.
- **Why it matters:** Voice would make Jason usable for hands-free operational discussion, live troubleshooting, ticket review, approvals, and quick status conversations without requiring chat-only interaction.
- **Scope:** Support inbound or explicitly initiated Teams calls with authenticated approved users; real-time speech-to-text, conversational reasoning, and text-to-speech; preserve Jason's normal governance, authority, audit, and client-boundary controls during the call.
- **Governance requirements:** No autonomous outbound calling by default; no adding participants without authorization; no recording/transcription retention beyond approved policy; disruptive or modifying actions discussed during a call still require the same playbook/approval rules as chat; voice identity must not be treated as sufficient authority without authenticated Teams identity/context.
- **Prerequisites:** Microsoft Teams calling/bot architecture, Graph/Teams calling permissions, media handling, speech pipeline, authenticated participant mapping, audit/event model, retention/privacy policy, and a controlled AOT-only acceptance test.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** When Teams communications work expands beyond chat/proactive messages or when a supported Teams real-time media path is selected.


### TODO-GOV-006 — Configuration-driven TODO engineering readiness

- **Priority:** P1
- **Status:** Approved design — implementation pending
- **Risk level:** Moderate
- **Idea:** Add a generic configuration/state-driven readiness and approval record that separates a proposed TODO from work Jason is authorized to implement autonomously.
- **Why it matters:** Jason needs a deterministic admission gate so autonomous engineering never invents missing requirements, broadens authority, or starts work before questions are answered.
- **Readiness requirements:** exact goal; included/excluded scope; required capabilities; dependencies; authority basis; safety class; human-approval boundaries; acceptance criteria; controlled test target; rollback/failure behavior; production path; documentation impact; open_questions=none.
- **Lifecycle:** Proposed -> Design Review -> Ready for Approval -> Approved for Autonomous Engineering -> In Development -> Validating -> Production Accepted -> Complete. Blocked work enters Blocked / Needs Decision without consuming the only engineering slot when independent approved work exists.
- **Configuration principle:** readiness schema, lifecycle states, thresholds, destination references, and approval fingerprints should be configuration/registry/state wherever practical. Material scope change invalidates the prior approval.
- **Authority boundary:** approval authorizes only the exact recorded TODO scope; it does not authorize constitutional changes, broader permissions, new secrets, client/provider expansion, disruptive actions, or absent material design decisions.
- **Owner visibility:** lifecycle state is emitted here; TODO-COMM-004 owns Teams rendering/delivery for start, blocker/action-required, and production-accepted events.
- **Acceptance:** approve one bounded TODO through the readiness record; prove automatic selection; force and clear one blocker; complete CI/merge/deployment; prove production acceptance; materially change scope and prove prior approval stale. Integrated acceptance must prove TODO-COMM-004 receives the lifecycle events.
- **Prerequisites:** canonical TODO schema/registry; isolated worktree/PR/CI/merge/release machinery; autonomous SUPPORT repair lane; TODO-COMM-004 for owner notification delivery.
- **Decision owner:** AOT Owner / Jason Governance Authority
- **Review trigger:** Implement before enabling general autonomous TODO engineering.

## Legacy ID aliases and consolidation map

These aliases preserve old PR, support, session, and conversation references. An alias never creates implementation authority.

| Legacy ID | Canonical destination | Disposition |
| --- | --- | --- |
| TODO-AI-002 | TODO-AI-001 | Disagreement/adjudication is phase 2 of reasoning quality. |
| TODO-AI-003 | TODO-AI-001 | Confidence calibration is phase 3. |
| TODO-COMM-002 | TODO-COMM-001 | Deterministic templates are a communication-framework work package. |
| TODO-COMM-005 | TODO-COMM-001 | Autotask client delivery is the controlled-send work package. |
| TODO-COMM-006 | TODO-COMM-001 | NotificationHistory prerequisite completed and archived. |
| TODO-COMM-007 | TODO-COMM-001 | Proposed Reply / Client Communication Policy is the draft-assist work package. |
| TODO-CONN-014 | TODO-CONN-013 | Approved-mailbox helper is mailbox lifecycle management. |
| legacy duplicate TODO-OPS-003 (Autotask work-start lifecycle) | archived completed record | Active TODO-OPS-003 remains cyber-insurance/security-questionnaire readiness. |
| TODO-OPS-006 | archived completed record | Datto EDR/AV threat-branch activation complete. |
| TODO-CONN-001 | archived completed record | Teams conversational ingress complete. |
| TODO-CONN-002 | archived completed record | Autotask read adapter/pagination foundation complete. |
| TODO-CONN-003 | archived completed record | Governed production-write foundation complete. |
| TODO-CONN-010 | archived completed record | DRMM site-variable capability complete. |
| TODO-CONN-012 | archived completed record | Autotask contact visibility complete. |
| TODO-CONN-018 | archived completed record | Governed endpoint PowerShell/read path complete. |
| TODO-CONN-019 | archived completed record | Autotask ticket attachment capability complete. |
| TODO-SEC-006 | archived completed record | Approval/execution-plan rollout complete. |
| TODO-SEC-007 | archived completed record | Security regression/red-team baseline complete. |

### Related programs intentionally kept separate

- TODO-OPS-003 and TODO-OPS-005 consume security-posture evidence, but Microsoft, network/security, DNSFilter, BullPhish, backup, and Duo connectors remain separate because they are reusable by troubleshooting and other workflows.
- TODO-COMM-004 owns Teams interaction/delivery; TODO-GOV-006 owns TODO readiness/lifecycle state; TODO-CONN-004 remains Teams credential/OpenClaw security hardening.
- TODO-OPS-009 remains active until controlled production acceptance completes; afterward it should fold into canonical Autotask ticket lifecycle documentation.

---

## New-item template

Copy this section when adding an idea:

```markdown
### TEMPLATE — TODO-AREA-### — Title

- **Priority:** P0 / P1 / P2 / P3
- **Status:** Proposed
- **Risk level:** Low / Moderate / High / Critical
- **Idea:**
- **Why it matters:**
- **Why not now:**
- **Prerequisites:**
- **Autonomous engineering readiness:** Not reviewed / Design Review / Ready for Approval / Approved
- **Approved scope:**
- **Authority basis:**
- **Required capabilities:**
- **Acceptance test:**
- **Open questions:**
- **Decision owner:**
- **Review trigger:**
```

---

## Maintenance rules

1. Review this document at least quarterly and at major architecture milestones.
2. Do not delete rejected or retired ideas without preserving the decision and rationale.
3. Move active engineering work into tracked issues or an implementation plan while leaving a reference here.
4. Every custom capability should retain its business justification, review interval, and retirement criteria.
5. The Technology Steward should identify items that can be replaced by improved vendor-native functionality.
6. No item in this document overrides the Jason Constitution, policy engine, approval requirements, or human authority.
---

## Completed / consolidated history

Completed and superseded TODO records are preserved verbatim in docs/roadmaps/Project-Jason-TODO-Consolidation-History.md. The active roadmap intentionally contains only work with remaining independent scope.

### Completed platform reliability reference

### OBS-001 — Grafana / Observability Configuration Assurance

- **Priority:** P1
- **Status:** Completed and production-proven 2026-09-27
- **Risk level:** Moderate
- **Why it mattered:** Production dashboards could depend on mutable worktrees or Grafana database-only state, which allowed dashboard pages or telemetry panels to disappear after redeploy, cleanup, or mount changes.
- **Implemented behavior:** All 21 production dashboards are now Git-authoritative and covered by the dashboard manifest; Grafana and Prometheus deploy from exact immutable observability release paths; a five-minute assurance control verifies source hashes, mount provenance, dashboard identities, datasource availability, and required Prometheus dependencies; the assurance exporter uses dedicated port `9474`; rollback restores the prior accepted release pointer if deployment acceptance fails.
- **Production evidence:** Source revision `f61ef43228d1f5072d425e11e5303ca3bb143079` is active. Independent readback verified 21/21 dashboard files, 21/21 Grafana dashboard identities, and 6/6 metric dependencies. Prometheus scrapes `jason-grafana-assurance` on `host.docker.internal:9474`; toner remains isolated on `9473`. OpenAI 24-hour, 7-day, and month-to-date cost metrics are present.
- **Recovery/alert proof:** Prometheus `promtool` synthetic rule tests proved the drift and unavailable/not-proven alert conditions. A disposable clean Grafana `12.2.1` instance recovered all 21 dashboards from immutable Git-backed sources after provisioning completed, then was removed.
- **Canonical documentation:** `docs/operations/Grafana-Observability-Configuration-Assurance.md` and `docs/sessions/Grafana-Observability-Configuration-Assurance-Production-Acceptance-2026-09-27.md`.
- **Remaining work:** None for this reliability baseline. Future dashboard changes must follow the existing manifest/CI/immutable-release/assurance process.

## Historical operational defaults
