# Project Jason TODO and Future Ideas

This document is the governed backlog for ideas, enhancements, and capabilities that are valuable but may be premature, blocked, or intentionally deferred.

The purpose is to preserve good ideas without allowing them to become undocumented scope, hidden commitments, or accidental production features.

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

### TODO-CONN-001 — Production OpenClaw transport

- **Priority:** P0
- **Status:** Planned
- **Risk level:** High
- **Idea:** Implement authenticated transport between OpenClaw and Jason using signed requests or mutual TLS.
- **Why it matters:** Required for dependable identity, replay protection, authorization, and audit.
- **Why not now:** Foundation exists, but production identity and deployment design are incomplete.
- **Prerequisites:** certificate or key lifecycle, identity mapping, persistent replay store, health endpoint.
- **Decision owner:** Platform Owner
- **Review trigger:** Before production pilot.

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


### TODO-CONN-004 — Kyocera device data integration

- **Priority:** P1
- **Status:** Blocked
- **Risk level:** Moderate
- **Idea:** Add a governed Kyocera integration so Jason can retrieve copier/MFP operational data such as total meter counts, black-and-white and color copy/print counts, model and serial number, device status, toner/supply levels, fault/error conditions, and other useful device telemetry exposed by Kyocera.
- **Why it matters:** Gives Jason direct visibility into managed copier usage and health. This can support meter collection, billing validation, proactive service, supply management, device inventory reconciliation, and faster ticket troubleshooting without relying on manual meter reads.
- **Why not now:** The read-only KFS connector foundation is implemented, but live activation is blocked until AOT receives Kyocera's official dealer API header/operation contract and production credentials, provisions them through OpenBao, and completes a controlled read-only validation.
- **Prerequisites:**
  - identify the authoritative Kyocera data source available to AOT;
  - document authentication and tenant/client isolation requirements;
  - map devices to Autotask configuration items and client/site records;
  - define canonical meter fields for mono, color, total impressions, scan/fax where available;
  - determine polling cadence and stale-data rules;
  - define read-only capability first, then any governed write/actions separately;
  - test against multiple Kyocera models and firmware versions;
  - establish audit logging and error handling.
- **Expected initial capabilities:**
  1. Search for a Kyocera device by serial number, hostname, IP, client, or Autotask configuration item.
  2. Read current meter/copy/print counts.
  3. Read model, serial, firmware, online state, and basic device identity.
  4. Read toner/supply levels and active faults when available.
  5. Compare current meter values with prior readings and flag abnormal changes or missing readings.
  6. Make meter data available to billing/reconciliation workflows without automatically changing billing records until separately approved.
  7. Use device health data as evidence in copier service tickets and proactive monitoring workflows.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Evaluate when defining Jason copier/MFP workflows or when AOT wants to automate monthly meter collection and copier billing validation.

- **Implementation status:** Read-only KFS provider foundation implemented on `feature/kfs-readonly-connector-20260921`; live provider selection is fail-closed behind `JASON_KFS_ENABLED` until the dealer contract and credentials are installed.

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


### TODO-GOV-004 — Move Jason-owned tickets to the Jason queue

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** When Jason begins actively troubleshooting or remediating an Autotask ticket, automatically move that ticket to the dedicated **Jason** queue for the duration of Jason ownership. When Jason completes the work, hands it back to a technician, or stops work pending external input, update the queue/status appropriately so human technicians have a clear ownership signal.
- **Why it matters:** Prevents duplicate work, conflicting changes, wasted technician time, and situations where a technician unknowingly works the same ticket while Jason is actively making changes.
- **Why not now:** The operating convention is already being used manually, but it is not yet enforced as a deterministic ownership rule in the ticket workflow.
- **Prerequisites:** Reliable Autotask ticket read/update capability; canonical Jason queue ID; clear ownership lifecycle states; rules for handoff, waiting, escalation, and completion; audit logging for every queue transition.
- **Expected behavior:**
  1. Before Jason begins active work, confirm the ticket is open and not already owned by another active technician workflow.
  2. Move the ticket to the **Jason** queue and set an appropriate working status.
  3. Record an internal note that Jason has taken ownership.
  4. Keep the ticket in the Jason queue while Jason is actively investigating, remediating, waiting on a scheduled Jason follow-up, or verifying results.
  5. On completion, set the ticket to Complete when verified.
  6. On human handoff or escalation, move the ticket to the appropriate human queue/resource and document the handoff.
  7. Do not silently leave tickets in the Jason queue after Jason has relinquished ownership.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement before expanding autonomous multi-ticket troubleshooting so queue ownership is reliable across technicians and Jason.


### TODO-OPS-001 — Persistent deferred and scheduled work

- **Related implementation:** `implementation/autonomous_remediation/availability.py` and `07-Operations/Endpoint-Availability-Verification-Playbook.md`
- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Add a governed durable scheduled-work subsystem that persists one-time and recurring Jason follow-ups across sessions and service restarts. It must support deferred verification, recurring checks, escalation, reason codes, ticket updates, and operational visibility in Grafana.
- **Why it matters:** Offline endpoints, backup verification, patch confirmation, post-reboot checks, waiting-for-device workflows, aging escalations, and similar cases must not depend on a technician remembering to return later or on the original ChatGPT/OpenClaw session still existing.
- **Why not now:** JKD-009 provides durable append-only event history but explicitly excludes scheduled retries. The endpoint-availability gate can calculate and persist `next_recheck_at`, but production execution of future work still needs a separate governed scheduler and durable execution model.
- **Prerequisites:** canonical deferred-work contract; durable job store; one-time and recurring schedule model; deduplication/idempotency key; client/requester/ticket/device context binding; reason-code taxonomy; cancellation on terminal state; bounded retry and aging rules; audit events; recovery after service restart; governed Autotask update capability; Grafana data source.
- **Expected behavior:**
  1. Persist one-time and recurring follow-ups independently of the conversation/session that created them.
  2. Support examples such as daily offline checks, next-day backup verification, post-patch verification, post-reboot verification, Wednesday-morning follow-up, and escalation after a defined aging threshold.
  3. Retain durable identity, source/correlation data, ticket/device/client/playbook references, next-run time, recurrence, lifecycle state, creation source, and a reason code explaining why the work exists.
  4. Execute no earlier than the requested time and rehydrate authorized context rather than creating new authority.
  5. Re-apply current Jason governance at execution time. Scheduling an action must never bypass approval requirements that would apply if the action were initiated interactively.
  6. Suppress duplicate execution and duplicate provider mutations using deterministic idempotency controls.
  7. Permit governed ticket updates, escalation, deferral, completion, and cancellation as outcomes of scheduled work.
  8. Cancel or retire scheduled work automatically when the parent ticket/workflow reaches a terminal state or the follow-up is no longer applicable.
  9. Record creation, execution, retry, reschedule, deferral, cancellation, failure, escalation, and completion evidence.
  10. Add a **Grafana Scheduled Work** view showing pending work, next execution, recurring work, overdue work, failed work, escalated work, recent completion history, source ticket/device/client, reason code, and governance/approval state where relevant.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement before claiming end-to-end autonomous deferred ticket handling or closing playbooks that require future rechecks across sessions.

### TODO-GOV-005 — Successful resolution to governed playbook candidate

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** When Jason and a technician successfully resolve a ticket, prompt the technician to submit the resolution as a playbook candidate and, when accepted, create a governed draft linked to the source ticket and resolution evidence.
- **Why it matters:** Reusable operational knowledge should become institutional memory instead of being rediscovered ticket by ticket. Capturing proven resolutions also creates a controlled path from technician-assisted success to repeatable automation without silently granting autonomy.
- **Why not now:** The playbook lifecycle and approval model exist conceptually, but the successful-resolution capture workflow, evidence package, candidate state model, and approval handoff are not yet implemented end to end.
- **Prerequisites:** reliable ticket completion detection; source-ticket linkage; canonical playbook-candidate schema; evidence capture from diagnostics/remediation/verification; approval workflow; versioning; rejection/retirement handling; autonomy approval kept distinct from ordinary playbook approval.
- **Expected behavior:**
  1. On a verified successful ticket resolution involving Jason and a technician, prompt: "Would you like to submit this resolution as a playbook candidate?"
  2. If accepted, create a governed candidate draft rather than an approved playbook.
  3. Capture available evidence including source ticket, client/site, affected devices, trigger/symptoms, diagnostics, commands/components/capabilities used, relevant outputs, decision gates, remediation, verification, retries/failures, exceptions, technician approvals, communications/documentation steps, risks, dependencies, limitations, and suggested scope.
  4. Preserve the lifecycle: **Successful Resolution → Candidate → Draft/Review → Approved Playbook → optionally Approved for Autonomous Use**.
  5. Treat **Approved** and **Approved for Autonomous Use** as separate governance decisions. Approval as a playbook must never implicitly authorize autonomous execution.
  6. Preserve source evidence and approval history so reviewers can reconstruct why the candidate was created and what proved the original resolution successful.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement as part of the production playbook lifecycle before broad autonomous remediation is enabled.

### TODO-OBS-001 — Grafana playbook lifecycle and autonomy-status page

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Add a Grafana page that makes each playbook's lifecycle, provenance, review state, approval state, and autonomous-use authorization immediately visible.
- **Why it matters:** Technicians and governance reviewers need a single operational view showing how a real resolution became a candidate, whether it has been reviewed and approved, and whether it is explicitly authorized for autonomous execution. Stale candidates must also be visible so potentially valuable knowledge does not disappear indefinitely in review.
- **Why not now:** The underlying lifecycle records and successful-resolution candidate workflow must expose stable data before Grafana can present an authoritative view.
- **Prerequisites:** canonical candidate/playbook lifecycle schema; source-ticket linkage; reviewer/approver records; separate autonomy-approval fields; version history; evidence-completeness signal; aging/staleness thresholds; Grafana-readable metrics or query source.
- **Expected behavior:**
  1. Display the lifecycle chain **Source Ticket / Resolution → Playbook Candidate → Under Review → Approved → Approved for Autonomous Use**.
  2. Show candidate/playbook name and ID, source ticket, originating resolution, creation date, current lifecycle state, reviewer/approver, approval date, autonomy approval state/authority/date, most recent revision/version, evidence completeness, and age in current state.
  3. Provide clear views for stale/aging candidates, rejected candidates with reason, items awaiting review, approved playbooks not approved for autonomy, and playbooks explicitly approved for autonomous use.
  4. Make the difference between **Approved** and **Approved for Autonomous Use** visually unmistakable.
  5. Preserve enough provenance to navigate from the dashboard state back to the source ticket and governed evidence record.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement when the playbook-candidate lifecycle begins producing durable production records, and before autonomous-playbook coverage expands enough that status ambiguity becomes an operational risk.

### TODO-SEC-001 — "Dangerous Users" scheduled risk-pattern detection

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Add a governed scheduled process that periodically reviews available security and operational evidence for users showing repeated high-risk behavior patterns. The operator-facing concept may be called **Dangerous Users**, with findings expressed as evidence-based statements such as: **"Tara has had repeated malicious downloads."**
- **Why it matters:** Repeated risky events involving the same user can be easy to miss when each alert, ticket, download, phishing event, or endpoint incident is handled independently. Correlating those events over time can identify users who may need targeted security review, additional training, tighter controls, or investigation before another incident occurs.
- **Why not now:** This depends on durable scheduled work, reliable identity correlation across providers, normalized security-event evidence, thresholds, false-positive controls, and a governed human-review workflow.
- **Prerequisites:** TODO-OPS-001 persistent scheduled work; canonical user identity correlation; read access to relevant sources such as Datto EDR/AV, RMM, SaaS/security alerts, email-security events, Autotask tickets, and other approved evidence sources; event normalization; configurable lookback periods and thresholds; deduplication; privacy/access controls; audit history; human review and disposition workflow.
- **Expected behavior:**
  1. Run on a governed recurring schedule across all in-scope clients or an explicitly selected client population.
  2. Correlate security events to a canonical user identity across devices and provider systems where evidence supports the mapping.
  3. Detect repeated patterns such as malicious downloads, repeated malware/EDR detections, repeated phishing interaction, repeated unsafe attachment/link activity, repeated credential/security incidents, or other approved high-risk event classes.
  4. Produce concise evidence-backed findings, for example: **"Tara has had repeated malicious downloads: 4 confirmed detections across 3 dates in the last 60 days."**
  5. Include the supporting event dates, devices, source systems, ticket/alert references, and relevant disposition so a technician can verify the finding.
  6. Use configurable thresholds, lookback windows, severity weighting, and decay/aging rules rather than treating a single event as a permanent user classification.
  7. Distinguish confirmed malicious/high-risk events from blocked attempts, false positives, administrative tests, or otherwise explained activity.
  8. Avoid inferring intent or automatically declaring a person malicious. "Dangerous User" is an operational review category triggered by documented behavior evidence, not a character judgment.
  9. Route new or materially worsened findings for technician/security review and optionally create or update an Autotask ticket through governed workflows.
  10. Do not automatically impose disciplinary, employment, access-removal, account-disablement, or other user-disruptive actions solely from this classification. Any such action remains subject to the appropriate playbook and human governance.
  11. Record the detection rule/version, evidence set, generated finding, reviewer disposition, false-positive/explanation reason, and subsequent outcome for audit and future rule tuning.
  12. Add a Grafana view or panel showing current flagged users, evidence count, severity/trend, last event, review status, aging, and cleared/closed findings while respecting client and role-based access boundaries.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement after TODO-OPS-001 provides durable recurring execution and enough normalized security evidence sources are available to produce reliable cross-event correlation.

---


### TODO-CONN-005 — Reconcile IT Glue notification tickets to the authoritative client at intake

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Add deterministic client reconciliation for IT Glue notification emails so tickets created by the generic `notifications@itglue.com` sender are associated with the actual client identified by the IT Glue event rather than the sender contact's Catchall company.
- **Why it matters:** Generic vendor notification contacts are intentionally shared across clients. Using sender-contact ownership as the ticket company can misassociate client data, break tenant isolation assumptions, block correct CI/documentation correlation, and make autonomous handling unsafe.
- **Production example:** `T20260922.0017` was created under Catchall company `1162` while the notification body identified `Gromelski And Associates Inc.`; DRMM independently maps that client to Autotask company `597`.
- **Expected behavior:**
  1. Detect recognized IT Glue notification messages before client-scoped automation begins.
  2. Parse the authoritative organization/network identity from structured notification content or provider metadata.
  3. Resolve that identity to exactly one client using approved mappings such as IT Glue organization ID/name and DRMM site -> Autotask company mapping.
  4. If exactly one client is proven, create or reassign the ticket to that company and clear incompatible generic contact/location references.
  5. If no unique match exists, leave the ticket in a neutral intake/Catchall state, mark `identification_blocked`, and request human review.
  6. Record the source evidence and mapping decision in an internal note/audit record.
  7. Do not use fuzzy company-name similarity as sole authority.
  8. Apply the same pattern to other generic multi-client vendor senders where appropriate.
- **Prerequisites:** SUPPORT-CONN-006 ticket company/contact reassignment; canonical cross-provider organization mapping; IT Glue Network Discovery read capability or equivalent structured notification parser; duplicate-suppression/idempotency.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement before autonomous processing of IT Glue Network Discovery or other generic vendor-notification tickets.



### TODO-OBS-002 — Grafana client-specific playbook coverage page

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Low
- **Idea:** Add a Grafana page that shows client-specific Jason playbooks, their operational status, recent executions, exceptions, and coverage. Use **Gromelski And Associates Inc.** as the first production client-specific playbook case, beginning with the rule that every newly discovered network device must be investigated, documented, and either confirmed expected or escalated.
- **Why it matters:** Some clients have unique operating rules, network designs, approval expectations, or recurring workflows that should not be forced into a global playbook. Technicians need a visible way to see which client-specific rules exist and whether Jason is actually following them.
- **Expected behavior:**
  1. Provide a client selector/filter.
  2. Show all client-specific playbooks for the selected client.
  3. Display playbook name, lifecycle state, version, owner, last review date, last execution, next scheduled check when applicable, and whether autonomous use is approved.
  4. Show current active cases/tickets governed by each client-specific playbook.
  5. Show recent successful runs, escalations, blocked cases, failed diagnostics, and unresolved exceptions.
  6. Show capability gaps and dependencies that prevent full execution.
  7. Clearly distinguish global playbooks from client-specific overrides/additions.
  8. Link each playbook to its source document and relevant source tickets/evidence where available.
  9. Make client-specific autonomy explicit; a client-specific playbook being approved must not imply global autonomy.
  10. Include a **coverage gap** view showing recurring client conditions that do not yet have a client-specific or global playbook.
- **First production case:** Gromelski And Associates Inc. — New Network Device Discovery. Every newly detected/unmatched device must be reviewed; known-good status requires evidence or confirmation, and unexplained devices must remain open/escalated.
- **Prerequisites:** canonical client-specific playbook metadata; persisted playbook execution/state data; source-ticket linkage; TODO-OBS-001 lifecycle data where reusable; reliable client identity correlation; Grafana-readable metrics or query source.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement as client-specific playbooks begin entering production, starting with the Gromelski network-device discovery workflow.



### TODO-CONN-006 — Client-required primary-contact inclusion without replacing requester

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Add a governed Autotask ticket/contact mechanism that can include a client-designated primary stakeholder on every applicable ticket without replacing or losing the actual requester/end-user contact.
- **Why it matters:** Some clients require a designated technical/management contact to be included on all tickets. Autotask currently exposes a single primary ticket `contactID` through Jason, so blindly setting that field would overwrite the real requester on user-generated tickets.
- **First production case:** Gromelski And Associates Inc. requires **Chris Benton** (Autotask contact ID `30684489`, Network Security Director) to be included on all Gromelski tickets.
- **Expected behavior:**
  1. Resolve the designated client stakeholder from authoritative Autotask contact data at execution time.
  2. For system-generated tickets with no human requester, set the designated stakeholder as the ticket contact when appropriate.
  3. For user-generated tickets, preserve the actual requester and additionally include the designated stakeholder using a supported Autotask notification/additional-contact/watch-list mechanism.
  4. Do not duplicate recipients.
  5. Verify the resulting requester and stakeholder associations through authoritative readback where available.
  6. Allow this requirement to be defined per client in client-specific playbooks/policy metadata.
  7. Fail closed when the designated contact is inactive, moved to another company, ambiguous, or otherwise invalid.
  8. Record the association decision in the ticket audit trail without exposing unnecessary contact data.
- **Prerequisites:** authoritative Autotask contact metadata; supported additional-recipient/contact API or native Autotask workflow mechanism; client-specific playbook policy metadata; reliable ticket write verification.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement with the Gromelski client-specific ticket operations playbook before claiming full enforcement of its primary-contact rule.



### TODO-OPS-002 — Governed client user/contact lifecycle across Autotask, IT Glue, security, and training platforms

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Define and implement a governed end-to-end process for how client users are created, correlated, maintained, trained, validated, and retired across every platform where AOT needs a user/contact record. The process should establish one canonical user identity and then drive the required downstream records in systems such as Autotask, IT Glue, Microsoft 365/Entra where applicable, BullPhish ID, security-awareness/training platforms, and other client-specific systems.
- **Why it matters:** User records are currently spread across multiple platforms with different purposes, schemas, ownership, and lifecycle behavior. Manual entry creates missing users, duplicates, stale records, inconsistent email/name/company mappings, training gaps, contact-routing problems, and incomplete offboarding. Jason needs a deterministic lifecycle so a user is either fully represented where required or explicitly documented as intentionally excluded.
- **Core design principle:** Treat the **person/user** as the canonical governed object. Platform-specific contacts/accounts are derived representations of that object, not independent sources of truth.
- **Lifecycle states:** Suggested persisted states include:
  - `discovered`
  - `identity_validated`
  - `client_validated`
  - `required_platforms_resolved`
  - `provisioning`
  - `training_enrollment_pending`
  - `active`
  - `change_pending`
  - `offboarding`
  - `retired`
  - `exception`
  - `blocked`
- **Expected behavior:**
  1. Define the authoritative source(s) used to establish that a person exists, belongs to a specific client, and is active.
  2. Create a canonical identity record using stable identifiers where available, including client, legal/display name, primary email, alternate email where needed, job title/role, location, manager/supervisor where relevant, employment/status state, and source identifiers.
  3. Determine which downstream platforms are required for that user based on client policy, employment type, role, licensing, location, security requirements, and service bundle.
  4. Create or update the corresponding **Autotask contact** and associate it with the correct company/location.
  5. Create or update the corresponding **IT Glue contact** and link/document related configurations or client-specific metadata when appropriate.
  6. Create, validate, or correlate the user's Microsoft 365 / Entra identity when AOT manages that identity.
  7. Create, validate, or correlate the user in **BullPhish ID** or the current approved phishing/security-awareness platform when the client participates in training/phishing programs.
  8. Enroll the user in the correct required security-awareness/training curriculum based on client policy, role, regulatory framework, and onboarding date.
  9. Track training assignment, completion, failure/non-completion, overdue state, exemptions, and retraining requirements.
  10. Support additional client-specific platforms through policy-driven connectors rather than hard-coding a single platform list.
  11. Prevent duplicate users by matching deterministic identifiers before creating anything.
  12. Detect mismatches such as:
      - user exists in Entra but not Autotask;
      - Autotask contact exists but not IT Glue;
      - user should be in BullPhish/training but is missing;
      - user is disabled/offboarded in the authoritative source but remains active elsewhere;
      - email/domain/client association differs between systems;
      - duplicate or stale contacts exist.
  13. Perform periodic reconciliation across all governed platforms and generate an actionable exception list.
  14. For user changes such as name, email, role, location, manager, or client status, propagate only the fields each provider should own and preserve provider-specific metadata.
  15. On offboarding, identify every governed downstream representation and retire/disable/archive/remove it according to provider capability and policy rather than assuming deletion is appropriate everywhere.
  16. Preserve history and evidence so Jason can explain when a user was created, changed, enrolled in training, disabled, or retired and which source authorized that action.
  17. Do not create, modify, disable, or delete high-impact identity records solely because another system disagrees; use confidence rules, approval gates, and exception handling.
  18. Do not expose sensitive user/contact data to roles that are not authorized to view it.
  19. Make client-specific exceptions possible, including clients that use different training providers, require extra contacts, exclude certain worker types, or have regulatory requirements.
  20. Integrate with client onboarding/offboarding playbooks so user lifecycle is part of normal MSP operations rather than an isolated cleanup task.
- **Training requirements:**
  - define who must receive training;
  - determine training package/curriculum by client and role;
  - define onboarding training deadline;
  - define recurring/annual training cadence where applicable;
  - define phishing-simulation enrollment rules;
  - track completion and failures;
  - define overdue reminders/escalation;
  - preserve exemptions and their approving authority;
  - define retraining after failed phishing simulations or policy triggers where approved;
  - provide reporting suitable for compliance/customer review.
- **Reconciliation / assurance:** Add a scheduled **User Lifecycle Assurance** process that compares the canonical user population with downstream systems and produces:
  - missing records;
  - duplicates;
  - stale/disabled users still active elsewhere;
  - missing BullPhish/training enrollment;
  - incomplete/overdue training;
  - client/company mismatches;
  - unresolved identities;
  - unsupported provider/API gaps.
- **Governance requirements:**
  - client isolation is mandatory;
  - canonical identity resolution must be deterministic;
  - no cross-client matching based only on name;
  - user-disruptive actions such as disabling an account remain subject to the appropriate approval/playbook;
  - training enrollment and contact creation should have their own risk/authority classifications;
  - all provider writes require readback verification where supported;
  - provider failures must fail closed and become exceptions rather than silently leaving a user partially provisioned.
- **Required capability areas:**
  - Autotask contact search/read/create/update;
  - IT Glue contact search/read/create/update;
  - Microsoft 365 / Entra user read and governed lifecycle actions;
  - BullPhish ID user/group/campaign/training enrollment read/write;
  - security-awareness training status/completion read;
  - provider-specific group/policy assignment;
  - client policy / service-bundle lookup;
  - scheduled reconciliation;
  - persisted lifecycle state;
  - exception ticket creation/update;
  - Grafana/reporting telemetry.
- **Grafana / operational visibility:** Add a user-lifecycle view showing, by client:
  - total active canonical users;
  - users fully synchronized;
  - missing downstream records;
  - duplicate/conflicting identities;
  - BullPhish/training enrollment status;
  - overdue/incomplete training;
  - recent onboardings/offboardings;
  - blocked/failed provisioning;
  - stale downstream users;
  - unresolved exceptions and aging.
- **Initial acceptance test:** Select one controlled client and prove a new user can be identified, correlated, represented in all required platforms, enrolled in the correct training, documented, and subsequently reconciled. Then test a role/email change and a controlled offboarding/retirement path without creating duplicates or losing audit history.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement before claiming end-to-end autonomous client user onboarding/offboarding or compliance/training assurance.



### TODO-OPS-003 — VulScan non-Windows and network-device vulnerability workflow

- **Priority:** P1
- **Status:** Planned
- **Risk level:** High
- **Idea:** Build a separate VulScan workflow for routers, firewalls, switches, printers, phones, appliances, embedded systems, IoT devices, and other non-Windows/unmanaged targets. Do not reuse the managed-Windows patch-remediation logic for these assets.
- **Why it matters:** VulScan tickets may represent firmware, TLS/cipher, web-interface, EOL software, appliance configuration, or vendor-specific vulnerabilities where Windows patch tooling is irrelevant or unsafe.
- **Expected behavior:**
  1. Identify the device by client, site, IP, MAC, OUI, hostname, serial, IT Glue/Autotask asset, and network evidence.
  2. Classify device type/vendor/model/firmware where possible.
  3. Correlate the exact CVE/finding to vendor guidance and current firmware/software state.
  4. Distinguish false/stale findings from confirmed vulnerabilities.
  5. Determine whether remediation is firmware upgrade, configuration change, vendor replacement, compensating control, documented risk acceptance, or escalation.
  6. Never apply Windows endpoint components to appliance/network-device findings.
  7. Treat firmware/network changes as modifying or potentially disruptive and require the appropriate approval.
  8. Verify remediation through authoritative rescan when available.
- **Prerequisites:** governed VulScan finding/read/rescan capability; reliable IT Glue/Autotask network-asset correlation; vendor/model identification; client-specific network playbook integration.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement after the managed-Windows VulScan playbook is validated and before claiming broad autonomous VulScan remediation.



### TODO-CONN-007 — Governed VulScan finding read and rescan integration

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Add a governed VulScan integration so Jason can read the authoritative vulnerability finding, correlate it to a client/device, and request or observe a rescan after remediation.
- **Why it matters:** The Windows VulScan playbook can independently verify many findings locally, but it cannot currently prove from VulScan itself that a finding cleared. This weakens end-to-end verification and can leave stale vulnerability tickets open or cause premature closure.
- **Expected behavior:**
  1. Search findings by client/site/device/IP/MAC/hostname/CVE/KB/ticket reference.
  2. Read authoritative finding details including scanner target identity, finding name, CVE/KB, CVSS/severity, first seen, last seen, current state, evidence/plugin output where safely available, and remediation guidance.
  3. Correlate the finding to DRMM endpoint and Autotask CI without relying on IP alone.
  4. Request a bounded rescan of the exact device/target where the VulScan API supports it.
  5. Poll/read rescan status without redispatching duplicate scans.
  6. Verify the exact finding is cleared, still present, or changed after remediation.
  7. Preserve client isolation and `direct_provider_access=false`.
  8. Expose rescan as a separately governed action from read-only finding access.
  9. Record provider job/finding identifiers for ticket evidence and troubleshooting.
  10. Fail closed when target identity is ambiguous or the scanner cannot distinguish a recycled IP.
- **First production case:** `T20260918.0012` / `OWNSHOP412LT1` / missing `KB5121003`.
- **Prerequisites:** VulScan/RapidFire Tools API capability discovery; credential governance; canonical vulnerability finding schema; device/client correlation; scan rate/impact controls; audit logging.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement before declaring the VulScan Windows remediation playbook fully end-to-end or autonomous.



### TODO-CONN-008 — Read DRMM patch process/policy assignment and exact-KB effective approval

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Add governed Datto RMM read capabilities that expose the patch process/policy assigned to a specific endpoint and determine the effective approval state of an exact Windows update/KB for that device.
- **Why it matters:** AOT's Datto RMM patch process is the normal authority that determines whether a patch is approved for a device. Aggregate endpoint states such as `ApprovedPending` and counts of approved/not-approved patches are useful but do not prove the approval state of a specific KB.
- **Expected behavior:**
  1. Read the patch process/policy currently assigned to an exact DRMM endpoint.
  2. Read effective policy inheritance/assignment and confirm the device is actually receiving that process.
  3. Evaluate an exact patch/KB against the effective process and return a bounded state such as `approved`, `denied`, `deferred`, `excluded`, `not_applicable`, or `unknown`.
  4. Return relevant deployment window/schedule metadata needed to determine whether Jason should wait for the normal patch cycle.
  5. Correlate exact KB/update identity without relying only on display text.
  6. Expose device-level aggregate patch state as corroborating evidence, not as a substitute for exact-KB approval.
  7. Preserve client isolation and `direct_provider_access=false`.
  8. Fail closed when policy inheritance or patch identity is ambiguous.
  9. Provide stable evidence IDs/provider identifiers for ticket documentation and playbook verification.
- **First production case:** `T20260918.0012` / `OWNSHOP412LT1` / `KB5121003`.
- **Playbook dependency:** `Jason-VulScan-Managed-Windows-Endpoint-Vulnerability-Remediation.md`.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement before claiming the Windows VulScan playbook can authoritatively decide whether a specific patch is approved for a device.



### TODO-CONN-009 — Autotask Form Template read/apply support for canned ticket notes

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Add governed Autotask support for searching, reading, and applying **Form Templates** so Jason can use centrally maintained canned text for ticket notes instead of duplicating standard wording inside playbooks.
- **Why it matters:** AOT already uses standardized note language and repeatable service workflows. Keeping reusable note content in Autotask provides one operational source of truth, lets technicians maintain wording without code changes, and reduces drift between Jason playbooks and human technician workflows.
- **Expected behavior:**
  1. Search available Form Templates by exact or bounded name/category.
  2. Read the template's current text/content and metadata.
  3. Resolve supported variables/placeholders without exposing secrets.
  4. Apply a selected Form Template to an exact Autotask ticket as a note.
  5. Allow Jason to append case-specific evidence/results beneath the canned text when the playbook requires it.
  6. Preserve note type, publish/visibility setting, and any template-defined metadata where Autotask supports it.
  7. Prevent ambiguous template selection; fail closed if multiple templates match.
  8. Record which template/version/name was used in the audit trail.
  9. Verify the resulting ticket note through authoritative readback.
  10. Expose read-only template discovery separately from note-creation/apply authority.
- **Playbook use cases:**
  - VulScan remediation/recheck notes;
  - AV/EDR diagnostics and resolution notes;
  - onboarding/offboarding communications;
  - customer update templates;
  - waiting-for-customer / waiting-for-device notes;
  - standardized escalation and completion notes.
- **Governance requirements:**
  - preserve Autotask permissions and ticket visibility;
  - no arbitrary cross-client template substitution;
  - template application must not silently overwrite existing ticket data;
  - playbook logic remains authoritative for decisions; Form Templates provide reusable text, not execution authority.
- **Prerequisites:** Autotask API support for Form Templates or an equivalent supported provider endpoint; governed template search/read capability; governed apply/create-note action; readback verification.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Implement before embedding additional reusable ticket-note language directly into Jason playbooks.


### TODO-OPS-004 — Windows licensing monitor false-negative investigation and correction

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Investigate and correct the Datto RMM `Monitor Windows Licence/License Status [WIN]` logic when it reports `Unable to ascertain OS licence` even though Windows authoritatively reports a fully licensed state.
- **Why it matters:** False licensing alerts create stale Autotask tickets, technician noise, and can obscure real activation failures. Jason should be able to distinguish a genuine unlicensed endpoint from a monitor parsing/provider defect before any licensing action is considered.
- **First production case:** `T20260907.0008` / `HER-50717`. The DRMM monitor reported `Unable to ascertain OS licence`, while an approved read-only local query of `SoftwareLicensingProduct` returned Windows Professional, Retail channel, `LicenseStatus=1`, grace period `0`, and exit code `0`.
- **Expected behavior:** Review the monitor implementation and its assumptions; reproduce the failure safely; identify the exact parsing/WMI/CIM condition that yields the false negative; update or replace the monitor using authoritative local licensing state; preserve distinct states for licensed, notification/grace/unlicensed, query failure, and unsupported cases; verify against multiple Windows editions/channels before deployment.
- **Governance:** Diagnostic reads may be automated when classified safe. Activation, key installation/change, edition change, KMS configuration, or other licensing mutations remain separately governed and must never be triggered solely by a monitor result.
- **Prerequisites:** Access to the current DRMM monitor component source/logic; controlled test endpoints representing Retail/OEM/digital/KMS states; regression test cases; monitor deployment/change-control process.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Address before treating Windows licensing monitor tickets as autonomously actionable or building a licensing-remediation playbook.

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
