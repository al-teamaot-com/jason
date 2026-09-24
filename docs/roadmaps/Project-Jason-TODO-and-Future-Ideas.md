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

---

## Priority legend

- **P0** — foundational or required before production use.
- **P1** — important near-term capability.
- **P2** — useful after the core platform is stable.
- **P3** — future or experimental capability.

---

## Future reasoning and quality controls

### TODO-AI-001 — Independent second-model review for complex or sensitive responses

- **Priority:** P2
- **Status:** Proposed
- **Risk level:** High
- **Idea:** Use a second AI model to independently review complex, sensitive, high-impact, or externally facing responses before they are released.
- **Why it matters:** A second perspective may identify factual errors, unsupported assumptions, inappropriate tone, policy violations, omitted risks, client-scope mistakes, or unsafe recommendations that the primary model missed.
- **Why not now:** The core orchestration, policy engine, provider abstraction, audit trail, audience controls, and approval workflows should be stable before adding multi-model review. A second model can create false confidence if both models share the same blind spots or are given the same incomplete evidence.
- **Prerequisites:**
  - provider-neutral reasoning interface;
  - formal sensitivity and complexity classification;
  - deterministic policy checks before AI review;
  - model identity and version logging;
  - evidence package passed by reference;
  - review-result schema;
  - disagreement handling;
  - cost and latency controls;
  - human approval path;
  - test cases for sensitive communications and recommendations.
- **Initial design:**
  1. Primary model produces a structured draft, cited evidence list, assumptions, confidence, and unresolved questions.
  2. The orchestrator determines whether independent review is required.
  3. A second model receives the evidence package and draft but does not communicate directly with the first model.
  4. The second model returns a structured review containing findings, severity, disagreement, missing evidence, and release recommendation.
  5. The orchestrator applies deterministic policy and decides whether to allow, revise, escalate, or require human approval.
- **Important rule:** Agreement between two models is not proof of correctness. Deterministic controls, source evidence, and human authority remain controlling.
- **Possible review triggers:**
  - legal, compliance, financial, employment, medical, security-incident, or privacy content;
  - executive or public-facing communication;
  - destructive or high-impact change recommendation;
  - low primary-model confidence;
  - conflicting evidence;
  - large financial exposure;
  - communication to many recipients;
  - client-impacting outage or breach response;
  - novel request outside established playbooks.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Reconsider after the first production reasoning provider, audience policy engine, approval workflow, and full audit chain are operational.

### TODO-AI-002 — Model disagreement and adjudication service

- **Priority:** P3
- **Status:** Proposed
- **Risk level:** High
- **Idea:** Define how Jason handles meaningful disagreement between independent AI reviews.
- **Why it matters:** A second model is useful only if disagreement leads to a safe, explainable outcome.
- **Why not now:** Depends on TODO-AI-001 and requires real pilot data.
- **Prerequisites:** structured review schema, severity scoring, evidence citations, human escalation workflow.
- **Expected behavior:** fail closed for critical disagreements, request more evidence for factual disagreements, and require human review for unresolved high-impact issues.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** After independent second-model review is piloted.

### TODO-AI-003 — Confidence calibration and outcome feedback

- **Priority:** P3
- **Status:** Proposed
- **Risk level:** Moderate
- **Idea:** Compare model confidence with actual outcomes and technician feedback.
- **Why it matters:** Raw model confidence is not inherently reliable. Calibration can identify overconfidence and weak reasoning domains.
- **Why not now:** Requires sufficient audited production history and reliable outcome labels.
- **Prerequisites:** feedback capture, resolution outcomes, evidence retention, privacy controls, reporting.
- **Decision owner:** Technology Steward
- **Review trigger:** After enough pilot cases exist for meaningful analysis.

---

## Operational learning and resolution reuse

### TODO-OPS-001 — Operational Resolution Memory and case-based troubleshooting reuse

- **Priority:** P1
- **Status:** In progress — governed search/reuse and confirmed-case ingestion are production-deployed; first verified-case capture and later reuse proof pending
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
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Begin design once governed ticket/alert reads, Datto job/output correlation, and reliable resolution outcomes are stable; implement before incident volume makes repeated rediscovery materially costly.

### TODO-OPS-002 — Governed BackupIQ ticket-processing playbook

- **Priority:** P1
- **Status:** Read evidence path production-active; operational write API still pending
- **Risk level:** High
- **Idea:** Build and productionize an end-to-end governed Jason playbook for Autotask tickets titled `BackupIQ: Backup for asset is not available for AOT Office`, including asset resolution, availability gating, periodic rechecks, Endpoint Backup diagnostics, bounded remediation, dependency-ticket creation, full command/result documentation, and verified successful-backup closure.
- **Current provider state:** The Endpoint Backup API credential blocker is resolved for reads. Production-accepted Backup.net capabilities `backup.endpoint.asset.search/read`, `backup.endpoint.backup.search`, and `backup.backupiq.alert.search` now provide provider-native evidence through the validated Autotask-company-to-Backup.net-customer boundary. Use those reads to establish backup state before remediation and to verify successful-backup closure; do not substitute DRMM agent state alone for backup-success evidence.
- **Current blocker:** No provider-supported public mutation contract has yet been identified for Endpoint Backup v2 backup-now, restore, restore cancellation, policy/retention, protection-state, or asset-management actions. Product UI capability is not API authority. Until Kaseya documents a supported write contract, remediation may use only separately governed supported paths (for example an already-authorized DRMM deployment/reinstall component), followed by Backup.net readback.
- **Why it matters:** BackupIQ tickets are repetitive, evidence-driven MSP work that Jason can materially process when the correct read, execution, ticket-write, scheduling, and verification capabilities are available. A deterministic playbook can reduce technician effort while preserving auditability, client isolation, and AOT approval rules.
- **Remaining workflow prerequisites:** persisted playbook state; scheduled periodic rechecks with duplicate suppression; exact ticket/device/client association; governed endpoint diagnostics/remediation where supported; and authoritative Backup.net successful-backup verification before closure. Provider-native Endpoint Backup writes remain a separate future capability.
- **Current API reference:** See `docs/operations/BackupNet-Endpoint-Backup-API-Current-State-2026-09-24.md`.
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
- **Status:** Planned
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

### TODO-OPS-006 — Complete Datto EDR/AV threat-branch activation

- **Priority:** P1
- **Status:** In progress — threat closure gate proven fail-closed; production activation pending
- **Risk level:** High
- **Idea:** Finish the `datto_edr_av` playbook by completing the controlled remediation/scan/recurrence acceptance path now that provider-native Datto AV scan execution is governed and accepted.
- **Why it matters:** The production backend can distinguish endpoint-security health, detections, policy, scan history, quarantine state, and can initiate an exact Quick/Full Datto AV scan. The remaining gap is proving the complete composite threat-response closure sequence, including post-scan detection verification, documentation, recurrence handling, and terminal disposition.
- **Current production proof:** Source revision `8776ac5dc56c4a22e0f86dceb780f0cff4fd70f9` is deployed. All six provider-neutral `endpoint.security.*` reads succeed through the authenticated Jason MCP path. Governed `endpoint.security.scan.start` is active with exact endpoint/agent binding and an owner execute grant that still requires approval. Controlled acceptance on AOT-50282 produced terminal Quick Scan history ID `ba2ad23d-8cb7-4ecf-ac2d-55af309406c3`, status `completed`. Grafana/Prometheus playbook observability remains live. The playbook remains `pilot`, `enabled=false`, with review status `scan_execute_accepted_full_threat_branch_pending`.
- **Required completion work:**
  - preserve exact endpoint/agent identity and provider isolation;
  - do not treat `ScanHistoryTracking.status=completed` as a clean result;
  - require completed scan evidence plus a clear post-scan governed detection search;
  - keep reboot actions explicit-approval-per-instance;
  - retain clean uninstall/recovery as policy-gated during supervised pilot;
  - run the complete controlled AOT-50282 / T20260918.0005 remediation/scan/recurrence acceptance path;
  - verify ticket documentation, telemetry, duplicate suppression, and terminal disposition.
- **Acceptance evidence:** `docs/sessions/Jason-Datto-EDR-AV-Governed-Read-Acceptance-2026-09-18.md` and `docs/sessions/Jason-Datto-EDR-AV-Scan-Execution-Acceptance-2026-09-18.md`.
- **2026-09-18 threat-branch acceptance checkpoint:** Runtime bindings now use the actual live `endpoint.security.scan.start` capability and exact status/detection/scan-history reads. Local focused suite passed 67 tests. Live AOT-50282 evidence proved the safety gate: EDR/AV protection was healthy, the originating artifact was quarantined/remediated, but provider `compromised=true` and an exact SHA-256 recurrence existed across 2026-09-11 and 2026-09-18. The playbook therefore must not close the threat branch. A Full AV scan was already in progress, so duplicate dispatch was suppressed. Evidence was written to Autotask internal note `30503131`. No endpoint mutation/disruptive action was performed.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Complete before setting the playbook registry `enabled=true` or declaring the full threat branch production-ready.

---
## Communication and audience controls

### TODO-COMM-001 — Connect audience policy engine to all outbound channels

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Require every email, SMS, Teams message, portal message, and voice script to pass through the Audience and Communication Policy Engine.
- **Why it matters:** Prevents inappropriate technical depth, internal-note disclosure, cross-client communication, sensitive-data leakage, and unsuitable tone.
- **Why not now:** Communication connectors are still foundations and not production-enabled.
- **Prerequisites:** recipient directory resolution, canonical communication record, channel adapters, approval service, policy configuration.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Before enabling any production outbound connector.

### TODO-COMM-002 — Audience-aware deterministic templates

- **Priority:** P2
- **Status:** Proposed
- **Risk level:** Moderate
- **Idea:** Maintain approved templates by audience, purpose, urgency, and channel.
- **Why it matters:** Reduces dependence on AI and improves consistency.
- **Why not now:** Audience taxonomy and communication purposes should first be validated during pilot use.
- **Prerequisites:** template registry, versioning, localization approach, exception process.
- **Decision owner:** Communications Owner
- **Review trigger:** After the audience engine is used in pilot workflows.

### TODO-COMM-004 — Complete Teams approval and information-request workflow

- **Priority:** P1
- **Status:** Blocked — external API credit balance
- **Risk level:** High
- **Idea:** Complete and production-verify Jason's governed Microsoft Teams approval and structured information-request workflow, including proactive Adaptive Cards, authenticated Approve/Deny responses, typed technician overrides, and correlation back to the originating Jason action/request.
- **Current evidence (2026-09-18):** Governed proactive Teams text delivery passed; Adaptive Card delivery passed; Microsoft Teams button interaction returned through the direct Teams gateway; Jason authenticated the Microsoft object ID and tenant correctly. Final decision processing was blocked when the conversation runtime received OpenAI API `429 insufficient_quota / credit_balance_exhausted`.
- **Already corrected during testing:** Jason's OpenAI reasoning effort was changed from unsupported `minimal` to supported `low` for `gpt-5.4-mini` (commit `811b3af`).
- **Remaining work:** Restore/confirm OpenAI API credit availability, repeat the same harmless approval-card test, prove that Approve and Deny are deterministically associated with the exact approval ID and authenticated technician, verify a typed override is treated as a modified instruction rather than implicit approval, and persist final audit evidence.
- **Acceptance test:** Send one harmless governed Teams approval card to the authenticated owner conversation; press Approve or Deny; verify Teams -> gateway -> Jason authenticated ingress -> approval correlation -> terminal decision succeeds without a provider/runtime error and without executing an unrelated operational action. Then separately verify one structured information request and one typed override response.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** As soon as Jason's OpenAI API balance is restored.

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

### TODO-CONN-001 — Production Teams conversational ingress

- **Priority:** P0
- **Status:** Implemented
- **Risk level:** High
- **Idea:** Provide authenticated, replay/idempotency-protected, auditable Microsoft Teams conversational ingress that reaches Jason before any independent interface model/agent path.
- **Why it matters:** Required for dependable identity, replay protection, authorization, audit, and exclusive Jason ownership of ordinary inbound Teams turns.
- **Implemented result:** On 2026-08-15 the dedicated `jason-teams-gateway` became the production owner of ordinary inbound Teams host port `3978`. The direct gateway authenticates through the Microsoft Agents SDK, constructs the existing signed Jason conversation envelope, and hands the request to `jason-runtime`. OpenClaw remains deployed for other approved functions but no longer owns externally reachable ordinary inbound Teams ingress.
- **Governed decision:** `docs/decisions/ADR-009-Direct-Microsoft-Teams-Ingress.md`.
- **Production proof:** `docs/sessions/Direct-Teams-Gateway-Production-Proof-2026-08-15.md`.
- **Decision owner:** Platform Owner / Jason Architecture Authority
- **Review trigger:** Revisit only if a supported replacement transport can prove equal or stronger identity, exclusive ownership, auditability, rollback, and Central Orchestrator enforcement.

### TODO-CONN-002 — Autotask read-only production adapter and contract tests

- **Priority:** P0
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Validate current Autotask endpoints, authentication, pagination, field mappings, and sanitized fixtures.
- **Why it matters:** This is the first production evidence source for Professional Ticket Investigation.
- **Why not now:** Requires read-only credentials and AOT-specific field mapping.
- **Prerequisites:** test tenant or approved production read access, fixture sanitization, rate-limit policy.
- **Decision owner:** Platform Owner
- **Review trigger:** When credentials are available.

### TODO-CONN-003 — Governed production write execution

- **Priority:** P1
- **Status:** Blocked
- **Risk level:** Critical
- **Idea:** Enable selected Autotask, Datto RMM, IT Glue, and n8n writes behind approval, idempotency, and precondition controls.
- **Why it matters:** Converts Jason from recommendation-only to controlled operational assistance.
- **Why not now:** The pilot is intentionally recommendation-first and read-only.
- **Prerequisites:** mature audit chain, approval service, rollback patterns, connector contract tests, least-privilege credentials, sandbox testing, incident response process.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Successful completion of the read-only shadow pilot and formal authorization to expand scope.

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
- **Status:** In progress — governed Entra posture read code deployed; production acceptance blocked by current Microsoft app consent/profile
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
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Add a governed DNSFilter read capability for client/site policy assignment, expected coverage, agent/device state, protective-DNS status, and exceptions.
- **Why it matters:** Provides authoritative DNS protection evidence rather than inferring posture from installed components.
- **Origin:** Reclassified from `SUPPORT-CAP-010` on 2026-09-18.
- **Prerequisites:** DNSFilter API/read contract, client/site mapping, least-privilege credentials, and acceptance fixtures.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** When DNSFilter becomes an approved Jason data source.

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

### TODO-CONN-010 — Governed Datto RMM site-variable reads

- **Priority:** P1
- **Status:** Planned — high priority
- **Risk level:** High
- **Idea:** Add a governed Datto RMM capability that can determine which site variables exist for an exact authorized site and whether a required variable is present and usable, without disclosing secret values unless an explicitly approved workflow requires the value.
- **Why it matters:** AOT components such as Duo deployment and Datto Endpoint Backup depend on site variables. Jason must be able to distinguish a missing site configuration dependency from an endpoint/component failure.
- **Current evidence (2026-09-20):** Live capability discovery exposes managed-site reads and component metadata but no dedicated site-variable/account-variable read capability. Existing endpoint UDF reads are not a substitute for Datto RMM site variables.
- **Required behavior:** Resolve the exact company/site first; enumerate variable names/metadata safely; report presence/absence and usability; redact sensitive values from chat, logs, tickets, and telemetry; allow approved playbooks to consume required values by reference; preserve `direct_provider_access=false`.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Treat as near-term work because multiple operational playbooks depend on site-variable presence validation.

### TODO-OPS-007 — Invoice-to-catalog and purchase-order workflow

- **Priority:** P1 — implement before Duo Security API integration
- **Status:** In progress — governed PO mutations live; lifecycle orchestration foundation implemented
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

### TODO-CONN-012 — Autotask contact visibility

- **Priority:** P1
- **Status:** Implemented — live verified 2026-09-20
- **Risk level:** Moderate
- **Idea:** Allow Jason to search and read Autotask contacts for an exact company so ticket workflows can resolve the correct user/contact and communication audience.
- **Implemented result:** Live capabilities `service.contact.search` and `service.contact.read` are active through governance. A bounded production search succeeded on 2026-09-20 with correlation `corr_mcp_8034be3c72224717bf09da49e6e3648a`.
- **Safeguards:** Company/client scoping, least-privilege reads, no cross-client inference, and normal audience/communication policy before outbound use.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Revisit only if contact writes or broader directory synchronization are proposed.

### TODO-CONN-013 — Governed requester/vendor mailbox content reads

- **Priority:** P1
- **Status:** Implemented source-ready — blocked on separate Microsoft mail-read app, Exchange Application RBAC assignment, and mailbox allowlist
- **Risk level:** High
- **Idea:** Give Jason a governed Microsoft 365 mailbox/message search and read capability for explicitly approved AOT mailboxes so procurement workflows can correlate vendor order confirmations, ETA changes, backorders, shipment notices, tracking updates, delivery notices, cancellations, invoices, NDRs, and other operational evidence.
- **Why it matters:** Procurement updates frequently arrive only by email to the person who requested the purchase. Without governed mailbox-content evidence, Jason cannot reliably maintain PO lifecycle state or generate timely approval proposals.
- **Required behavior:** Resolve the exact approved mailbox; search bounded time windows/participants/subjects/identifiers; read only necessary message content and attachment metadata; preserve message IDs/timestamps/digests for audit; correlate using PO/vendor order/invoice/SKU/customer/ticket evidence; redact unnecessary sensitive content; never treat email alone as physical receiving evidence.
- **Governance:** Mailbox scope must be explicit; no tenant-wide arbitrary mailbox reading; normal identity/authority/client boundaries apply; `direct_provider_access=false`.
- **Implementation checkpoint (2026-09-20):** Source now includes bounded `communication.mail.message.search`, `communication.mail.message.read`, and `communication.mail.attachment.search` foundations, an exact approved-mailbox allowlist, a separate `microsoft_graph_mail` client boundary, separate OpenBao AppRole/secret paths, logical secret `microsoft_graph.mail_read`, and explicit `mail-read` permission profile. Existing v4/v5 provider-read profiles remain mailbox-blind; only the new explicit v6 profile can activate mail reads. Focused regression proves v5 leaves all mail capabilities in PILOT and v6 activates them only after the separate authority is present. A live read-only probe with the current directory application returned HTTP 403 for `/messages`, confirming the current application does not have effective mailbox-read authority; Jason did not broaden that application. Microsoft guidance was then revalidated: resource-scoped access must use Exchange Online Application RBAC role `Application Mail.Read` with a custom resource scope. Do not add an organization-wide Microsoft Entra Graph `Mail.Read` application grant, because Entra and Exchange RBAC grants are additive and an unscoped Entra grant would defeat the intended mailbox restriction.
- **Production checkpoint (2026-09-20):** Source commit `e647e197e5056749b759f18bd67184dbaebba443` is live in image `jason-mcp:procurement-mail-foundation-e647e19` while production remains on `itglue-autotask-entra-procurement-catalog-v5`. Shadow and post-cutover checks confirm all three mail capabilities remain `PILOT`/unexposed, so production authority did not broaden. Rollback container: `jason-mcp-pilot-pre-mail-foundation-20260920T134141Z`.
- **Acceptance test:** In a controlled AOT mailbox, ingest one vendor ETA/shipping update tied to a test PO and prove exact message correlation without exposing unrelated mail.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Implement as the next procurement dependency after the PO lifecycle foundation.

### TODO-CONN-014 — Add approved mailbox helper workflow

- **Priority:** P2
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Create a small idempotent PowerShell helper such as `Add-Jason-Mailbox.ps1 -Mailbox user@teamaot.com` for adding future approved requester/purchasing mailboxes after the initial `Jason Mail Read` application is activated.
- **Why it matters:** AOT should not have to rerun the full Entra application/certificate/Exchange RBAC setup for every technician or requester mailbox.
- **Required behavior:** Validate the mailbox exists; add it to the existing Exchange Application RBAC resource scope without replacing or broadening unrelated scope; add it to Jason's exact approved-mailbox allowlist; preserve the existing app/certificate/service-principal identity; verify the new mailbox is in scope; verify a known unapproved mailbox remains denied; make no tenant-wide Graph permission changes.
- **Safeguards:** Fail closed on ambiguous/missing mailbox, unexpected existing RBAC configuration, scope drift, or inability to prove the deny test. Do not add Microsoft Graph `Mail.Read` under Entra API permissions.
- **Acceptance test:** Starting from the proven single-mailbox pilot, add one second controlled AOT mailbox with the helper, prove both approved mailboxes are readable through the scoped authority, prove an unapproved mailbox remains inaccessible, and verify `direct_provider_access=false`.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Implement after the initial Jason Mail Read pilot is activated and validated.

### TODO-CONN-015 — Governed Autotask contract read/write capability

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Add governed Autotask contract capabilities so Jason can search and read contracts and related contract-service/billing details, then support tightly controlled contract updates where the Autotask API permits them.
- **Why it matters:** Contract visibility is required for vendor-cost reconciliation, client profitability analysis, billing validation, service reconciliation, and accurate operational decisions that depend on what AOT is actually contracted to provide and bill.
- **Why not now:** The live Jason capability registry currently exposes no `service_contract` capability, and contract mutations require explicit schema validation, least-privilege authorization, approval controls, idempotency, audit evidence, and safe test coverage before production use.
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

### TODO-CONN-018 — Governed ad-hoc PowerShell on eligible Windows endpoints

- **Priority:** P1
- **Status:** Proposed
- **Risk level:** High
- **Idea:** Expand Jason's governed `Run Ad Hoc Command (PowerShell 2-5) [WIN]` execution path from the current single-device pilot scope to eligible Datto RMM-managed Windows endpoints, including workstations and servers, while preserving strict governance.
- **Why it matters:** Jason can often identify the exact read-only diagnostic command needed, but a hard-coded device scope forces manual technician intervention on other customer systems.
- **Why not now:** The current MCP/runtime execution contract pins the ad-hoc PowerShell runner to a single device identity and target class as part of the original pilot safety boundary.
- **Prerequisites:** replace single-device scope with governed endpoint resolution; validate OS and device identity before execution; support workstation/server target classes; preserve exact component UID binding; classify commands read-only vs mutating; require per-run technician approval for arbitrary commands; prohibit autonomous disruptive/destructive commands; enforce client isolation, audit evidence, bounded output, attempt limits, and job readback verification; add acceptance tests on representative Windows workstation and server targets.
- **Decision owner:** Jason Governance Authority / MSP Operations
- **Review trigger:** High priority; complete before Jason is expected to perform cross-client read-only diagnostics without technician-side command execution.

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
- **Status:** Proposed
- **Risk level:** Moderate
- **Idea:** Define how capabilities are deprecated, replaced, migrated, and removed.
- **Why it matters:** Prevents undocumented drift and abandoned features.
- **Why not now:** The capability registry is still early.
- **Prerequisites:** capability ownership, usage telemetry, versioning, migration notices.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Before the first breaking capability change.

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

### TODO-SEC-006 — Complete approval/execution-plan security rollout

- **Priority:** P0 — high priority
- **Status:** Production rollout and bounded XYZ acceptance complete; broader per-provider acceptance and unrelated baseline cleanup remain
- **Risk level:** Critical
- **Idea:** Complete production rollout of the dual-binding approval security model so every approval-governed mutation binds both the canonical semantic intent and the concrete provider execution plan after provider selection, symbolic resolution, normalization, defaulting, and exact target resolution.
- **Why it matters:** The 2026-09-23 security review proved two distinct issues: approval replay could create duplicate provider writes, and an unchanged approved semantic action could normalize into a materially different concrete provider mutation. Replay/idempotency is now production-fixed; execution-plan binding is source-implemented and isolated-test proven but not yet production-accepted.
- **Confirmed evidence:** Approval replay originally created duplicate Autotask notes `30506555` and `30506556`. After the replay fix, controlled production replay created only note `30506631`; the replay was `deduplicated` and did not invoke the provider again. Core execution-plan binding is `56b0e91fe376fb270ac521c5c1754bfa12aafdb5`; follow-on remediation on `fix/security-remediation-20260923` is checkpointed at `0ed6911`, `e41e572`, and shared-framework/recovery commit `bf072af`. The currently identified approval-governed action surface is adapted at source level, including Autotask ticket/create/note/procurement, Datto RMM component execution/site variables/alert resolution, Datto EDR scan execution, and Teams proactive send. Continuation/recovery approvals retain dual plan binding; one absolute provider deadline spans both preparations and invocation; recovery retries are durably one-time and require fresh JKD-001 authority. Consolidated security regression: 186/186 PASS. The complete orchestrator suite has three unchanged pre-existing IT Glue/provider-read failures that reproduce at baseline `10d1e9c`; no new broader-suite failures were introduced. Chronological record: `docs/sessions/2026-09-23.md`.
- **Current production boundary:** At the rollout safety check, production still reported source revision `5f89f3af82081e75e97d66e523222e5564648163` with deployment purpose `approval-replay-idempotency-fix`. The planned XYZ mutation was correctly stopped before approval/provider invocation. Production execution-plan acceptance is therefore pending, not failed.
- **High-priority work, in order:**
  1. **Preserve security regression coverage.** Adapter compatibility, total provider deadline budgeting, continuation/recovery dual binding, durable recovery retry consumption, secret commitments, replay/deduplication, and zero-write mismatch cases are source-tested. Keep these cases in CI and do not merge changes that weaken them.
  2. **Clean deployment/rebuild verification — COMPLETE.** Authoritative source `6e4e4c0` produced no-cache MCP/runtime candidate images; the earlier overlay-chain failure did not recur; exact live MCP/runtime rollback image IDs are pinned; isolated candidate/rollback contract checks and source-hash equivalence passed; live production containers were unchanged.
  3. **Production deployment — COMPLETE.** MCP/runtime source `6e4e4c0` is live, healthy, rollback-preserved, Central Orchestrator-bound, and `direct_provider_access=false`.
  4. **Bounded XYZ live acceptance — COMPLETE.** `T20211001.0014` / ID `29860` priority `2 -> 3` completed with one provider attempt, exact intent/plan fingerprints, provider/target/payload binding, no plan mismatch, connector verification, and governed post-read confirmation. The priority remains `3`; no second compensating write was performed during acceptance.
  5. **Track the unrelated baseline failures separately.** Do not fold the three pre-existing IT Glue/provider-read test failures into the security rollout or weaken security tests to obtain a green aggregate result.
- **Acceptance condition:** Production is on a clean/verified expected revision; all approval-governed mutation adapters are explicitly classified; adapted providers pass the execution-plan regression contract; blocked adapters fail closed; the bounded XYZ live test records exactly one provider write and matching provider readback; rollback remains proven.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Immediate; this is the next security-hardening production workstream.

### TODO-SEC-007 — Expand security regression/red-team coverage and observability

- **Priority:** P1 — medium priority after `TODO-SEC-006` production acceptance
- **Status:** Planned
- **Risk level:** High
- **Idea:** Turn the 2026-09-23 security findings into permanent multi-provider regression coverage and secret-safe operational visibility.
- **Medium-priority work:**
  1. **Expand red-team testing beyond Autotask:** DRMM/Datto mutation paths; future IT Glue writes; Entra/identity actions; Teams/message actions; KFS mutations if/when write support is enabled; backup/security-provider actions.
  2. **Cross-client isolation regression suite:** preserve explicit automated tests for missing/invalid client-provider bindings; missing evidence must remain `unknown` / `evidence_unavailable` rather than broadening provider/client scope.
  3. **Prompt-injection regression suite:** ticket notes, email-derived evidence, IT Glue documents, attachments, alert descriptions, user-provided diagnostic text, and other externally sourced content must remain evidence/content rather than execution authority.
  4. **Approval security regression suite:** maintain coverage for replay, changed canonical arguments, changed concrete provider mutation, provider substitution, target substitution, expired approval, wrong tenant/client, wrong principal, duplicate execution, and failed-execution retry semantics.
  5. **Security documentation and Grafana visibility:** surface useful secret-safe control state for approval failures, replay/deduplication, execution-plan mismatches, denied provider substitutions, denied target/payload changes, and fail-closed adapter gaps. Do not expose client-sensitive payloads, credentials, secret material, or raw authorization context.
- **Why it matters:** The review demonstrated that apparently independent controls can fail at different layers. Permanent multi-provider regression and observability reduce the chance that future adapter/provider changes reintroduce replay, client-scope, post-approval-normalization, or provider-substitution defects.
- **Prerequisites:** `TODO-SEC-006` production acceptance, provider adapter inventory, stable audit event schema, secret-safe metrics/export design.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Begin immediately after the bounded execution-plan production acceptance and adapter inventory.

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

### TODO-COMM-005 — Autotask notification-template communication capability

- **Priority:** P1
- **Status:** In progress — governed NotificationHistory read deployed; production read blocked by `SUPPORT-CAP-016`; ticket-note communication bridge investigation started 2026-09-20
- **Risk level:** High
- **Idea:** Let Jason discover AOT-approved Autotask notification templates and use them for governed end-user ticket communications with exact ticket/company/contact audience validation, preview, approval policy, send evidence, and post-send verification.
- **Provider constraint:** Autotask documents `NotificationHistory` as query-only and exposes `templateName`, but does not document Notification Templates as a queryable/executable REST resource or a named-template send operation. Jason must not scrape/private-call the Autotask UI.
- **Implemented checkpoint (2026-09-19):** Active `service.notification.history.search` is deployed through Central Orchestrator and requires explicit company scope. `service.entity.describe` proved the production API identity currently has `userAccessForQuery=None` on NotificationHistory; bounded live query failed closed and is tracked as `SUPPORT-CAP-016`.
- **Implementation checkpoint (2026-09-20):** Confirmed the documented `TicketNotes` REST entity supports create/update and has tenant-specific `publish` and `noteType` picklists. Started a governed `service.entity.fields.describe` read path to `/TicketNotes/entityInformation/fields` so Jason can resolve the live tenant meanings instead of hard-coding numeric picklist IDs. This is the prerequisite for a separate customer-visible ticket-note action and for validating the existing internal-note contract.
- **Remaining acceptance:** Deploy and prove `service.entity.fields.describe` for `TicketNotes`; resolve the exact active values corresponding to internal-only and customer-visible publication plus the intended ticket-note type; then implement a distinct governed customer-visible note capability with ticket/company/contact validation, preview/approval policy, one provider attempt, readback verification, and NotificationHistory or equivalent send evidence. Continue investigating whether an Autotask workflow rule can safely map that note event to an existing AOT notification template. Preserve `direct_provider_access=false` and do not hard-code tenant picklist IDs.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** After `SUPPORT-CAP-016` is resolved or a vendor-supported named-template invocation surface is identified.

### TODO-COMM-006 — Enable Autotask Notification History read permission

- **Priority:** P1
- **Status:** Planned — resume when Owner is at a trusted workstation
- **Risk level:** Moderate
- **Idea:** Enable the minimum Autotask security-level permission required for Jason's dedicated read-only API identity to query `NotificationHistory`, then complete live acceptance of `service.notification.history.search`.
- **Current evidence:** Live `service.entity.describe` shows `Resources` query access = `All` while `NotificationHistory` query access = `None`. This isolates the blocker to the read identity's Autotask security level, not Jason's governed read implementation.
- **Required provider change:** In Autotask, edit only the security level assigned to the dedicated Jason read-only API user and enable Notification History query/access under the applicable Application-wide / Shared Features administrative permission. Do **not** change the separate `Jason API - Ticket Mutation` security level or unrelated permissions.
- **Remaining acceptance:** Re-run a company-bounded `service.notification.history.search`; require successful readback of recent notification metadata including template name, recipient, sent time, and company/ticket association; inventory observed AOT notification-template names; continue `TODO-COMM-005`; preserve `direct_provider_access=false`.
- **Prerequisites:** Owner at a trusted workstation with Autotask administrative access.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Next desk session.

### TODO-OPS-005 — Client Security/Posture Review

- **Priority:** P1
- **Status:** In progress — deterministic evidence/classification foundation implemented 2026-09-19
- **Risk level:** Moderate
- **Idea:** Periodically or on demand evaluate one authorized client against AOT's managed-security baseline using only authoritative governed evidence, then produce a gap report and improvement proposals without automatically changing client systems.
- **Classification:** Every control must be `confirmed_good`, `confirmed_gap`, `unknown`, `not_applicable`, or `evidence_unavailable`. Missing evidence never means healthy.
- **Initial controls:** BitLocker, managed AV/EDR, supported OS, DRMM monitoring, VulScan, DNSFilter, backup coverage/recent success, Microsoft MFA/Conditional Access, and documentation completeness.
- **Implemented checkpoint:** `implementation/orchestrator/client_security_posture.py` defines the deterministic baseline/evaluator. Tests prove missing evidence cannot become good, unavailable evidence remains distinct, mixed evidence fails to a gap, and confirmed gaps create proposals rather than automatic changes. Architecture contract: `docs/architecture/Jason-Client-Security-Posture-Review.md`.
- **Production checkpoint (2026-09-19):** Controlled `XYZ Test Company` resolved to exact Autotask company ID `1158`. Company-bound Autotask configuration evidence succeeded. Exact-name DRMM site discovery returned no site, and IT Glue organization evidence was denied by the information-release gate; both are correctly represented as `evidence_unavailable` rather than guessed or cross-client substituted. Client binding now requires exact Autotask identity and treats absent provider mappings as unavailable.
- **Production checkpoint (2026-09-19, mapped client):** Atomic Plumbing & Drain Cleaning is independently bound as Autotask company `333` ↔ DRMM site UID `a6af04fc-2e2a-4236-82ca-9d47ac616524`. Exact endpoint evidence on `Atomic-50291` proved current AV/EDR health and exact endpoint alert reads. The evaluator now requires complete client coverage before any healthy sample becomes `confirmed_good`; one authoritative unhealthy observation can still establish a gap. Account-level DRMM alert search was observed returning cross-site results despite a site selector and is excluded from posture evidence.
- **Remaining acceptance:** Normalize complete DRMM inventory evidence across the bound client; obtain/authorize IT Glue organization evidence without bypassing its information-release gate; preserve unavailable status for Endpoint Backup and Microsoft controls until their desk-dependent integrations are completed; add report/Grafana evidence after live proof.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Continue immediately with client-bound evidence mapping.

---

## New-item template

Copy this section when adding an idea:

```markdown
### TODO-AREA-### — Title

- **Priority:** P0 / P1 / P2 / P3
- **Status:** Proposed
- **Risk level:** Low / Moderate / High / Critical
- **Idea:**
- **Why it matters:**
- **Why not now:**
- **Prerequisites:**
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

## Recently implemented operational defaults

### TODO-OPS-003 — Autotask ticket work-start lifecycle

- **Priority:** P1
- **Status:** Implemented 2026-09-18
- **Risk level:** Moderate
- **Idea:** When Jason begins substantive work on an existing Autotask ticket, automatically claim the ticket into the Jason queue, set the active working status, set the standard remote-support work type, associate a deterministically proven device/configuration item when available, and normalize Ticket Type / Issue Type / Sub-Issue Type when supported by ticket/playbook evidence.
- **Implemented behavior:** Queue **Jason**; status **In Progress**; Work Type **Remote Support**; preserve existing configuration association; otherwise require exact DRMM UID to active Autotask configuration correlation before writing `configurationItemID`; preserve existing classification unless exact supported labels are available; resolve all mutable labels from live Autotask metadata and require post-write readback. Refined lifecycle rule: triage/eligibility reads do not claim the ticket; claim occurs immediately before the first substantive diagnostic/remediation/verification action. Endpoint tickets require an authoritative governed DRMM read proving the device is online. The pre-claim queue/status are persisted as trusted state. When Jason must hand work to a human/provider/client, the governed handoff restores that recorded queue/status and records a blocker fingerprint; unchanged blockers cannot immediately reclaim the ticket.
- **Governance:** Standing Owner-approved administrative start-work transition only. It does not broaden arbitrary ticket-update authority or disruptive-action authority.
- **Production evidence:** Revision `5854cf670e33df473a37890ad9c28b7069510b3e`; controlled acceptance on `T20260914.0026` / ticket ID `140439` verified Jason queue, In Progress status, and Remote Support work type.
- **Canonical documentation:** `docs/operations/Jason-Autotask-Ticket-Work-Lifecycle.md`.
- **Decision owner:** Jason Governance Authority / AOT Owner
