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
- **Status:** Planned
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
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Begin design once governed ticket/alert reads, Datto job/output correlation, and reliable resolution outcomes are stable; implement before incident volume makes repeated rediscovery materially costly.

### TODO-OPS-002 — Governed BackupIQ ticket-processing playbook

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Build and productionize an end-to-end governed Jason playbook for Autotask tickets titled `BackupIQ: Backup for asset is not available for AOT Office`, including asset resolution, availability gating, periodic rechecks, Endpoint Backup diagnostics, bounded remediation, dependency-ticket creation, full command/result documentation, and verified successful-backup closure.
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

---

### TODO-OPS-003 — Complete Datto EDR/AV threat-branch activation

- **Priority:** P1
- **Status:** In progress
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
- **Status:** Planned
- **Risk level:** High
- **Idea:** Add narrow governed read-only capabilities for MFA registration/enforcement, Conditional Access, privileged-account MFA, legacy-authentication restrictions, Exchange Online protection configuration, external-message tagging, quarantine, attachment/link protection, and related tenant security posture.
- **Why it matters:** Enables evidence-backed cyber-insurance and security-control reviews without manual tenant inspection.
- **Origin:** Reclassified from `SUPPORT-CAP-007` on 2026-09-18 because this is a new capability/integration, not a break/fix defect.
- **Prerequisites:** least-privilege Microsoft Graph/Exchange read scopes, tenant isolation, evidence normalization, and sanitized acceptance fixtures.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** When Microsoft 365 security-posture automation becomes an approved implementation priority.

### TODO-CONN-006 — Client backup-posture reads

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Add governed provider reads for backup inventory, protection coverage, last successful backup, encryption/separation metadata where available, and restore-test evidence.
- **Why it matters:** Lets Jason answer backup-control questions and identify protection gaps from authoritative evidence.
- **Origin:** Reclassified from `SUPPORT-CAP-008` on 2026-09-18.
- **Prerequisites:** provider selection, client-scoped read credentials, canonical backup model, and acceptance workflow.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** When backup-provider integration is selected for implementation.

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