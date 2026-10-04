# Project Jason TODO Consolidation History

This file preserves verbatim TODO records removed or superseded during the 2026-10-04 roadmap consolidation. It is historical evidence, not implementation authority. The active decision surface is Project-Jason-TODO-and-Future-Ideas.md.

## Consolidation principles

- No historical TODO text is deleted merely because work completed or merged into a parent capability.
- Legacy IDs remain resolvable through the active roadmap alias map.
- Completed records do not compete with unfinished work for autonomous engineering intake.
- Consolidation does not broaden authority, approval, provider scope, or production permissions.

---

### TODO-OPS-006 — Complete Datto EDR/AV threat-branch activation

- **Priority:** P1
- **Status:** Implemented 2026-09-24 — production-enabled v1.3 with terminal escalation acceptance
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
- **2026-09-24 completion checkpoint:** Live AOT-50282 / T20260918.0005 revalidation confirmed the Full scan from 2026-09-19 completed, later Quick scans through 2026-09-24 completed, and no detection newer than the originating 2026-09-18 high-severity quarantined artifact was present. The identical SHA-256 recurred across prior weekly detections and provider detail still reports `compromised=true`, so the correct terminal outcome is security escalation rather than closure. v1.3 makes `escalation_required` terminal/sticky so later healthy product state, clean scan evidence, or recurrence bookkeeping cannot downgrade an established escalation. The production registry is enabled only under existing Central Orchestrator, approval, provider-isolation, and disruption controls.
- **Review trigger:** Revisit when Datto threat semantics/capabilities change or operational evidence identifies a needed branch refinement.

---


---

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


---

### TODO-CONN-002 — Autotask read-only production adapter and contract tests

- **Priority:** P0
- **Status:** Implemented and production-proven — governed Autotask read adapter, pagination, identity/boundary controls, and contract coverage are active
- **Risk level:** Moderate
- **Idea:** Validate current Autotask endpoints, authentication, pagination, field mappings, and sanitized fixtures.
- **Why it matters:** This is the first production evidence source for Professional Ticket Investigation.
- **Production evidence:** Governed Autotask company/ticket/note/entity metadata reads are active through Central Orchestrator under the dedicated read identity and Jason-managed requester authorization. Repeated ticket read/search/count acceptance, client-boundary regression coverage, pagination fixes, and the latest full production diagnostic all succeeded with `direct_provider_access=false`. Autotask requester-read failures and thread-affinity regressions are closed in the Support List.
- **Ongoing rule:** Preserve least-privilege read identity, client isolation, bounded pagination, sanitization, information-release authorization, and provider-contract regression coverage. New Autotask entities require their own documented/provider-supported read contract rather than inheriting authority from this foundation.
- **Decision owner:** Platform Owner
- **Review trigger:** When credentials are available.


---

### TODO-CONN-003 — Governed production write execution

- **Priority:** P1
- **Status:** Implemented as a governed execution foundation — selected write providers are production-active under exact capability authority; individual write families remain separately gated
- **Risk level:** Critical
- **Idea:** Enable selected provider writes behind approval, idempotency, exact target resolution, execution-plan binding, precondition controls, and post-mutation verification.
- **Why it matters:** Converts Jason from recommendation-only to controlled operational assistance while preserving human and policy authority.
- **Production evidence:** Central Orchestrator governed execution is live with `direct_provider_access=false`; approval replay/deduplication and concrete execution-plan binding are production-proven. Bounded write/readback acceptance exists for Autotask ticket notes/updates/create/procurement/attachments/charges, Datto alert/component/site-variable/EDR scan actions, DNSFilter bounded acceptance profiles, and Teams messaging. Provider attempts, approvals, target/payload bindings, and readback evidence are audited. Unsupported or dormant write families fail closed.
- **Ongoing rule:** This foundation is not blanket provider write authority. Every new mutation family requires an explicit capability/provider contract, exact authority, least-privilege credential, approval/autonomy posture, provider preflight, bounded execution, verification, rollback/failure handling, and security regression coverage before activation.
- **Decision owner:** Jason Governance Authority
- **Review trigger:** Successful completion of the read-only shadow pilot and formal authorization to expand scope.


---

### TODO-CONN-010 — Governed Datto RMM site-variable reads

- **Priority:** P1
- **Status:** Implemented and production-proven — governed list/create/update active; secret values remain protected
- **Risk level:** High
- **Idea:** Add a governed Datto RMM capability that can determine which site variables exist for an exact authorized site and whether a required variable is present and usable, without disclosing secret values unless an explicitly approved workflow requires the value.
- **Why it matters:** AOT components such as Duo deployment and Datto Endpoint Backup depend on site variables. Jason must be able to distinguish a missing site configuration dependency from an endpoint/component failure.
- **Production evidence:** `management.site.variable.list`, `management.site.variable.create`, and `management.site.variable.update` are active governed capabilities. Controlled production create of `AOT_OnboardingVariableBaseline` on the AOT-owned Managed site succeeded through the governed create path and authoritative readback verified the variable existed exactly once with its value masked. Site-variable values remain sensitive configuration and are not disclosed to non-administrative requesters.
- **Required behavior:** Resolve the exact company/site first; enumerate variable names/metadata safely; report presence/absence and usability; redact sensitive values from chat, logs, tickets, and telemetry; allow approved playbooks to consume required values by reference; preserve `direct_provider_access=false`.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Reopen only for a new site-variable operation, provider contract change, secret-handling regression, or playbook-specific usability defect.


---

### TODO-CONN-012 — Autotask contact visibility

- **Priority:** P1
- **Status:** Implemented — live verified 2026-09-20
- **Risk level:** Moderate
- **Idea:** Allow Jason to search and read Autotask contacts for an exact company so ticket workflows can resolve the correct user/contact and communication audience.
- **Implemented result:** Live capabilities `service.contact.search` and `service.contact.read` are active through governance. A bounded production search succeeded on 2026-09-20 with correlation `corr_mcp_8034be3c72224717bf09da49e6e3648a`.
- **Safeguards:** Company/client scoping, least-privilege reads, no cross-client inference, and normal audience/communication policy before outbound use.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Revisit only if contact writes or broader directory synchronization are proposed.


---

### TODO-CONN-018 — Governed ad-hoc PowerShell on eligible Windows endpoints

- **Priority:** P1
- **Status:** Implemented and production-proven — generalized governed Datto execution and dedicated provider-neutral `endpoint.powershell.read` are accepted on representative workstation/server targets
- **Risk level:** High
- **Idea:** Expand Jason's governed read-only PowerShell path across eligible Datto RMM-managed Windows endpoints, including workstations and servers, while preserving strict governance.
- **Why it matters:** Jason can often identify the exact read-only diagnostic command needed, but a hard-coded device scope forces manual technician intervention on other customer systems.
- **Production evidence:** The original single-device target restriction was removed through governed target canonicalization. Production acceptance on VZ-50618 proved non-pilot exact endpoint/component resolution, exactly one Datto execution, terminal job readback, governed StdOut, and no cross-company resource use. Dedicated `endpoint.powershell.read` acceptance on 2026-09-27 then proved the provider-neutral path on workstation AOT-50282 and server VZ-SERVER-00 using exact device UIDs, fixed component identity, classifier-approved read-only commands, bounded asynchronous job execution, and governed terminal output readback. The server acceptance also proved PowerShell-2-compatible diagnostics on Windows Server 2008 R2. PR #396 hardened classifier-denial transparency and fails closed when completed jobs contain PowerShell stderr. Evidence: `docs/sessions/Dedicated-Read-Only-PowerShell-Production-Acceptance-2026-09-27.md`.
- **Prerequisites:** replace single-device scope with governed endpoint resolution; validate OS and device identity before execution; support workstation/server target classes; preserve exact component UID binding; classify commands read-only vs mutating; require per-run technician approval for arbitrary commands; prohibit autonomous disruptive/destructive commands; enforce client isolation, audit evidence, bounded output, attempt limits, and job readback verification; add acceptance tests on representative Windows workstation and server targets.
- **Decision owner:** Jason Governance Authority / MSP Operations
- **Review trigger:** Reopen if the Datto diagnostic component identity changes, the read-only classifier boundary changes, a representative Windows target class regresses, or provider output/status semantics change.


---

### TODO-CONN-019 — Governed Autotask ticket attachment read/add capability

- **Priority:** P1
- **Status:** Production-accepted 2026-09-25 — read/search/content-read active on v8; bounded create accepted with approval-required exact authority
- **Risk level:** High
- **Idea:** Let Jason list/read bounded Autotask ticket attachments and add one approved file attachment to one exact verified ticket without exposing raw file bytes in durable governance records.
- **Read design:** `service.ticket.attachment.search`, `service.ticket.attachment.read`, and `service.ticket.attachment.content.read` are client-isolated and require exact `company_id` + `ticket_id`; exact metadata/content reads also require attachment ID. Metadata reads strip provider `data`; content read is explicit and bounded to 6,000,000 decoded bytes. The connector pre-reads the ticket and requires `ticket.companyID == company_id` before any attachment request. Attachment content remains untrusted evidence.
- **Write design:** `service.ticket.attachment.create` uses the dedicated owner-only Autotask action profile, existing `autotask.write` credential, provider-native requester impersonation, exact ticket/company verification, live `TicketAttachments.userAccessForCreate` preflight, exact Internal Users Only publish resolution (`publish=2`), one provider POST, and exact post-write attachment readback. The execution plan stores only company/ticket, filename/title/visibility, publish value, SHA-256 and byte size; raw base64 remains transient and is not written to durable execution-plan JSON. No delete/update capability is included.
- **Authority:** Exact grant accepted for `person-al` / `aot` / `service.ticket.attachment.create` / `execute` with `approval_required=true`. This is not autonomous authority; each create still requires approval.
- **Production acceptance (2026-09-25):** Controlled test against XYZ Test Company, company `1158`, ticket `8870` / `T20191013.0001`. Exactly one governed provider execution occurred (`provider_attempts=1`). Attachment `22167` (`jason-attachment-acceptance-20260925.txt`, `text/plain`, 44 bytes) was created as Internal Users Only (`publish=2`). `service.ticket.attachment.search` found exactly the new attachment and `service.ticket.attachment.read` independently confirmed ID, filename, title, size, ticket ID, and visibility. Post-test ticket read matched the pre-test ticket state for status, queue, priority, assignment, title, company, CI, and other checked ticket fields; no separate ticket mutation occurred. Governed mutation correlation ID: `corr_mcp_action_36deecf2380c4ea7986b5237e5e86a76`.
- **Activation:** v8 provider-read profile is active for attachment reads. `owner-ticket-attachment-v1` is active for governed create. Central Orchestrator remains enforced and direct provider access remains disabled.
- **Ongoing rule:** Attachment content remains untrusted evidence. Keep create approval-required unless a future separately approved playbook/autonomy decision explicitly changes that posture.
- **Decision owner:** Jason Governance Authority / AOT Owner


---

### TODO-SEC-006 — Complete approval/execution-plan security rollout

- **Priority:** P0 — high priority
- **Status:** Implemented — production rollout, adapter classification, bounded XYZ acceptance, replay protection, execution-plan binding, and canonicalization acceptance complete
- **Risk level:** Critical
- **Idea:** Complete production rollout of the dual-binding approval security model so every approval-governed mutation binds both the canonical semantic intent and the concrete provider execution plan after provider selection, symbolic resolution, normalization, defaulting, and exact target resolution.
- **Why it matters:** The 2026-09-23 security review proved two distinct issues: approval replay could create duplicate provider writes, and an unchanged approved semantic action could normalize into a materially different concrete provider mutation. Replay/idempotency and execution-plan binding are now production-fixed and bounded-live accepted. SUPPORT-CAP-019 subsequently proved that model-facing canonicalization must also occur before approval binding so technician-friendly aliases cannot reach execution-plan preparation in an under-specified provider shape.
- **Confirmed evidence:** Approval replay originally created duplicate Autotask notes `30506555` and `30506556`. After the replay fix, controlled production replay created only note `30506631`; the replay was `deduplicated` and did not invoke the provider again. Core execution-plan binding is `56b0e91fe376fb270ac521c5c1754bfa12aafdb5`; follow-on remediation on `fix/security-remediation-20260923` is checkpointed at `0ed6911`, `e41e572`, and shared-framework/recovery commit `bf072af`. The currently identified approval-governed action surface is adapted at source level, including Autotask ticket/create/note/procurement, Datto RMM component execution/site variables/alert resolution, Datto EDR scan execution, and Teams proactive send. Continuation/recovery approvals retain dual plan binding; one absolute provider deadline spans both preparations and invocation; recovery retries are durably one-time and require fresh JKD-001 authority. Consolidated security regression: 186/186 PASS. The historical three IT Glue/provider-read baseline failures no longer reproduce after ADR-011 requester-authorization remediation. A 2026-09-26 full orchestrator run on current main collected 1,075 tests and passed 1,075/1,075 with zero failures. Chronological record: `docs/sessions/2026-09-23.md`.
- **Current production boundary:** The dual-binding execution-plan model is production-accepted. A later follow-on compatibility defect, SUPPORT-CAP-019, showed that ordinary technician-friendly `service.ticket.update` inputs could bypass MCP canonicalization and fail during plan preparation before provider invocation. That generic boundary is now production-fixed in MCP source `5244e9e41ac86a366fc475b37be0559919fdc968`: direct ticket selectors are authoritatively resolved and structured before approval/intent binding, symbolic resolution remains execution-plan-bound, and OWNI7JAN25 acceptance proved exactly one completion write with successful readback and no direct-provider bypass. Durable proof: `docs/sessions/Jason-Direct-Ticket-Update-Canonicalization-Production-Acceptance-2026-09-24.md`.
- **High-priority work, in order:**
  1. **Preserve security regression coverage.** Adapter compatibility, total provider deadline budgeting, continuation/recovery dual binding, durable recovery retry consumption, secret commitments, replay/deduplication, and zero-write mismatch cases are source-tested. Keep these cases in CI and do not merge changes that weaken them.
  2. **Clean deployment/rebuild verification — COMPLETE.** Authoritative source `6e4e4c0` produced no-cache MCP/runtime candidate images; the earlier overlay-chain failure did not recur; exact live MCP/runtime rollback image IDs are pinned; isolated candidate/rollback contract checks and source-hash equivalence passed; live production containers were unchanged.
  3. **Production deployment — COMPLETE.** MCP/runtime source `6e4e4c0` is live, healthy, rollback-preserved, Central Orchestrator-bound, and `direct_provider_access=false`.
  4. **Bounded XYZ live acceptance — COMPLETE.** `T20211001.0014` / ID `29860` priority `2 -> 3` completed with one provider attempt, exact intent/plan fingerprints, provider/target/payload binding, no plan mismatch, connector verification, and governed post-read confirmation. The priority remains `3`; no second compensating write was performed during acceptance.
  5. **Preserve the now-green broader baseline.** The historical IT Glue/provider-read failures are cleared on current main; continue treating any future recurrence as a regression rather than weakening tests to obtain a green aggregate result.
- **Acceptance condition:** Production is on a clean/verified expected revision; all approval-governed mutation adapters are explicitly classified; adapted providers pass the execution-plan regression contract; blocked adapters fail closed; the bounded XYZ live test records exactly one provider write and matching provider readback; rollback remains proven.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Reopen only if a new approval-governed mutation adapter is introduced, a security regression fails, or production evidence shows replay/execution-plan/canonicalization drift.


---

### TODO-SEC-007 — Expand security regression/red-team coverage and observability

- **Priority:** P1 — medium priority after `TODO-SEC-006` production acceptance
- **Status:** Implemented 2026-09-24 — permanent security regression, prompt-injection, observability, and alerting baseline active; 2026-09-26 full orchestrator revalidation 1,075/1,075 PASS
- **Risk level:** High
- **Idea:** Turn the 2026-09-23 security findings into permanent multi-provider regression coverage and secret-safe operational visibility.
- **Medium-priority work:**
  1. **Expand red-team testing beyond Autotask:** DRMM/Datto mutation paths; future IT Glue writes; Entra/identity actions; Teams/message actions; KFS mutations if/when write support is enabled; backup/security-provider actions.
  2. **Cross-client isolation regression suite:** preserve explicit automated tests for missing/invalid client-provider bindings; missing evidence must remain `unknown` / `evidence_unavailable` rather than broadening provider/client scope.
  3. **Prompt-injection regression suite:** ticket notes, email-derived evidence, IT Glue documents, attachments, alert descriptions, user-provided diagnostic text, and other externally sourced content must remain evidence/content rather than execution authority.
  4. **Approval security regression suite:** maintain coverage for replay, changed canonical arguments, changed concrete provider mutation, provider substitution, target substitution, expired approval, wrong tenant/client, wrong principal, duplicate execution, and failed-execution retry semantics.
  5. **Security documentation and Grafana visibility:** surface useful secret-safe control state for approval failures, replay/deduplication, execution-plan mismatches, denied provider substitutions, denied target/payload changes, and fail-closed adapter gaps. Do not expose client-sensitive payloads, credentials, secret material, or raw authorization context.
- **Why it matters:** The review demonstrated that apparently independent controls can fail at different layers. Permanent multi-provider regression and observability reduce the chance that future adapter/provider changes reintroduce replay, client-scope, post-approval-normalization, or provider-substitution defects.
- **2026-09-24 checkpoint:** Added dedicated `SEC-007 Security Regressions` CI coverage for client-boundary persistence, governed approval replay/recovery, execution-plan binding, Teams approval ingress/delivery, and the active Autotask, Datto RMM/EDR, DNSFilter, and Teams write adapters. Provider-neutral execution-plan tests explicitly require fail-closed zero-provider-write behavior for principal, organization, client, canonical capability, provider, target, symbolic mapping, and normalized payload substitution. Prompt-injection regressions now prove malicious ticket/provider text remains untrusted evidence and is serialized as model user/evidence content rather than system authority. Secret-safe security observability now exports only aggregate control counters from the durable orchestration audit store: execution-plan denials, blocked provider invocations, replay/deduplication, authority-context denials, approval consumption, and an allowlisted set of fail-closed termination reasons. No client IDs, principals, ticket IDs, fingerprints, arbitrary audit messages, secrets, or provider payloads are exposed as metrics. The `Jason Security & Learning` dashboard includes these controls. Multi-source prompt-injection fixtures now cover mail content, IT Glue document content, attachment metadata, and Datto alert descriptions through the common evidence-reasoning boundary. Security alerting thresholds now cover telemetry loss, authority-context denial, execution-plan denial bursts, client-context failure bursts, and provider-eligibility failure bursts. Remaining SEC-007 work is limited to future-provider coverage as new write surfaces are introduced and tuning thresholds from operational history.
- **Prerequisites:** `TODO-SEC-006` production acceptance, provider adapter inventory, stable audit event schema, secret-safe metrics/export design.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Production completion (2026-09-24):** The SEC-007 baseline is complete. Required CI now permanently exercises cross-client isolation, execution-plan substitution, approval replay/recovery, approval transport, active write-provider adapters, and multi-source prompt-injection containment. Prometheus/Grafana now expose aggregate secret-safe security-control metrics and live alert rules for exporter loss, authority-context denial, execution-plan denial bursts, client-context failure bursts, and provider-eligibility failure bursts. Live acceptance after merge `f0af05303928c9ed7a8dc1a09d0c05bc54c04102` confirmed Prometheus healthy, all six security rules loaded, and no security/governance alert firing under the current production state. Future write providers and new evidence sources must be added to these regression/observability gates as part of their own production admission; that maintenance does not keep this baseline TODO open.
- **Review trigger:** Extend the permanent SEC-007 suites whenever a new write provider, approval transport, evidence source, or authority boundary is admitted to production.


---

### TODO-COMM-006 — Enable Autotask Notification History read permission

- **Priority:** P1
- **Status:** Implemented — minimum NotificationHistory read permission enabled and bounded production read accepted 2026-09-25
- **Risk level:** Moderate
- **Idea:** Enable the minimum Autotask security-level permission required for Jason's dedicated read-only API identity to query `NotificationHistory`, then complete live acceptance of `service.notification.history.search`.
- **Production evidence:** The dedicated Jason read-only API security level was updated with the minimum required Notification History query access. Live entity metadata reports `canQuery=true` and `userAccessForQuery=All` while create/update/delete remain `None`. A bounded governed `service.notification.history.search` for company 311 succeeded and returned recent notification metadata including template name, recipient, sent time, and ticket/company association. The separate `Jason API - Ticket Mutation` profile was not broadened and `direct_provider_access=false` remained enforced.
- **Remaining work:** None for the permission/read-enablement item itself. Continue `TODO-COMM-005` separately for client-facing notification delivery/template workflow behavior.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Reopen only if NotificationHistory read permission regresses or the dedicated read identity changes.


---

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


---

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


---

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


---

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


---

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


---

### TODO-COMM-004 — Complete Teams approval and information-request workflow

- **Priority:** P1
- **Status:** In progress — API credit/runtime blocker cleared; approval and information-request paths production-proven; typed-override acceptance pending
- **Risk level:** High
- **Idea:** Complete and production-verify Jason's governed Microsoft Teams approval and structured information-request workflow, including proactive Adaptive Cards, authenticated Approve/Deny responses, typed technician overrides, and correlation back to the originating Jason action/request.
- **Current evidence (2026-09-25):** The former OpenAI API credit/runtime blocker is no longer active. Production approval-card interaction now reaches the conversation runtime and returns completed decisions. Controlled test `teams-card-test-4-20260925` completed an authenticated Approve turn, persisted the exact decision, and a later conflicting Deny was blocked before runtime; SUPPORT-CONN-022 is production-closed. The direct Teams conversation also contains authenticated owner-originated operational information requests that Jason processed through the conversation runtime, demonstrating the information-request ingress path. Ordinary non-card Teams messaging remains healthy after the approval-gateway changes.
- **Already corrected during testing:** Jason's OpenAI reasoning effort was changed from unsupported `minimal` to supported `low` for `gpt-5.4-mini` (commit `811b3af`). Adaptive Card result handling and single-use decision claims were subsequently hardened in PRs #344 and #342.
- **Remaining work:** Source/runtime pre-acceptance is complete: focused Teams conversation/approval/request-factory/continuation tests pass and prove typed approval-like text routes only to the normal authenticated conversation flow while the dedicated approval flow is untouched. One live authenticated owner typed override remains; then persist final acceptance evidence and mark the workflow production-complete.
- **Acceptance test:** A harmless typed-override fixture `teams-typed-override-test-20260925-1` has been delivered to the authenticated owner conversation. The owner must reply in the Jason bot chat with a modified instruction rather than clicking Approve/Deny. Acceptance requires the typed message to enter as a normal authenticated conversation turn, the original approval ID to remain undecided/unconsumed, no provider mutation to occur, and Jason to treat the text as a changed instruction requiring fresh planning/approval rather than implicit authorization.
- **Decision owner:** Jason Governance Authority / Technology Steward
- **Review trigger:** Complete immediately after the typed-override acceptance reply is observed. Pre-acceptance evidence is recorded in `docs/sessions/Teams-Typed-Override-Preacceptance-2026-09-26.md`.


---

### TODO-COMM-005 — Autotask notification-template communication capability

- **Priority:** P1
- **Status:** In progress — governed NotificationHistory read is production-proven; client-notification TEST-mode mutation acceptance remains
- **Risk level:** High
- **Idea:** Let Jason discover AOT-approved Autotask notification templates and use them for governed end-user ticket communications with exact ticket/company/contact audience validation, preview, approval policy, send evidence, and post-send verification.
- **Provider constraint:** Autotask documents `NotificationHistory` as query-only and exposes `templateName`, but does not document Notification Templates as a queryable/executable REST resource or a named-template send operation. Jason must not scrape/private-call the Autotask UI.
- **Production checkpoint (2026-09-25):** `SUPPORT-CAP-016` is resolved. The dedicated Jason read-only API security level now reports `NotificationHistory` `canQuery=true` / `userAccessForQuery=All` while create/update/delete remain unavailable. Governed `service.notification.history.search` succeeded for company 311 and returned bounded recent template name, recipient, sent time, ticket, and company metadata with `direct_provider_access=false`.
- **Implementation checkpoint (2026-09-20):** Confirmed the documented `TicketNotes` REST entity supports create/update and has tenant-specific `publish` and `noteType` picklists. Started a governed `service.entity.fields.describe` read path to `/TicketNotes/entityInformation/fields` so Jason can resolve the live tenant meanings instead of hard-coding numeric picklist IDs. This is the prerequisite for a separate customer-visible ticket-note action and for validating the existing internal-note contract.
- **Client-notification TEST mode decision (2026-09-26):** Client-facing notifications are restricted to **XYZ Test Company only** (Autotask company ID `1158`) until explicitly promoted out of test mode. Source now contains dormant capability `service.ticket.client.notification.create` plus a fail-closed test-scope guard. Before any future send mutation, the resolved ticket company and resolved contact company must both equal `1158`; the destination must come from the authoritative Autotask contact email; any caller-supplied recipient must exactly match that contact email; and the explicit test profile `xyz-test-company-client-notification-v1` must be enabled. All other companies fail closed before a send mutation. Focused guard/catalog tests: 9/9 PASS. The capability remains source-only/not registered in production pending the XYZ Gmail contact acceptance setup.
- **Remaining acceptance:** Bind the controlled XYZ Gmail address to the intended XYZ Autotask contact, implement/register the dedicated client-notification mutation provider without altering the internal-note contract, require explicit approval during TEST mode, perform one bounded send on an XYZ controlled ticket, verify exact recipient and message through NotificationHistory, and prove a non-XYZ target is denied before provider mutation. Preserve `direct_provider_access=false`.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Continue with the controlled XYZ client-notification TEST-mode acceptance or revisit if Autotask exposes a supported named-template invocation surface.


---

### TODO-COMM-007 — Client Communication Policy and Proposed Reply Assist

- **Priority:** P1
- **Status:** Proposed — initial authority must be internal draft assist only
- **Risk level:** High
- **Idea:** Build an AOT Client Communication Policy and a governed Jason workflow that detects tickets likely created by or containing substantive replies from real clients, regardless of ticket status, evaluates the actual issue before communicating, and creates a private Autotask internal note titled **Proposed Reply** containing the best evidence-grounded response for the technician. Initial implementation must never send the reply to the client.
- **Why it matters:** Client-created tickets often begin with an observation rather than a proven fault. Jason should help the technician distinguish expected behavior from a real problem, gather evidence before troubleshooting, identify the smallest unresolved ambiguity, and prepare a concise AOT-quality response that advances the technical case without unnecessary client effort.
- **Core intake rule:** Before remediation or client troubleshooting, determine whether the reported behavior is a confirmed technical problem, confirmed expected behavior, or still unconfirmed. Expected behavior must be proven rather than assumed. If evidence cannot distinguish the two, identify the exact ambiguity and generate the smallest possible client question or observation needed to resolve it.
- **Minimum-client-effort rule:** Never ask the client for information Jason can obtain authoritatively from Autotask, Datto RMM/EDR, Microsoft 365, IT Glue/documentation, provider evidence, prior tickets/resolution memory, or other approved read-only sources. Prefer one observation or one question over a checklist.
- **Structured decision record:** For every proposed reply, retain the ticket/evidence snapshot, client-origin confidence, current issue classification, known facts, unresolved ambiguity, information Jason can obtain internally, client input still required, communication class, risk class, proposed next action, and current communication authority. The client-facing prose is a separate artifact from this internal reasoning record.
- **Initial Proposed Reply behavior:** Create only a private internal Autotask note titled **Proposed Reply**. Maintain one current proposal per ticket; later proposals supersede stale ones. A proposal becomes stale and non-sendable after material ticket evidence changes, a technician/client message arrives, the alert/state changes, or another technician response makes the draft obsolete.
- **Client-reply processing:** Treat a client reply as new evidence, not automatic authority or an instruction to act. Bind it to the ambiguity/question that prompted the prior reply; classify the response as `ambiguity_resolved`, `partially_resolved`, `not_resolved`, or `new_issue_introduced`; independently verify the answer when possible; reclassify the technical issue; perform permitted internal evidence gathering; then generate the next smallest necessary Proposed Reply. Separate newly introduced symptoms from the original issue rather than silently expanding scope.
- **Evidence-link rule:** When telling a client that behavior is expected, supported/unsupported, required, or attributable to a documented vendor limitation or product behavior, include an authoritative vendor/standards/AOT-approved knowledge source when one reasonably exists. Prefer official vendor documentation and require that the source support the exact claim. Links must be validated and client-safe; never fabricate or attach a generic article merely because it concerns the same product.
- **Multi-step client tests:** A multi-step client procedure is not ordinary prose. It must be represented as its own governed diagnostic sub-procedure with entry/necessity gates, per-step purpose, risk classification, branching, stop conditions, rollback for configuration changes, bounded attempts, evidence capture, user-impact controls, and terminal escalation. Present only the next justified step where practical; stop as soon as the ambiguity is resolved.
- **Communication classes:** At minimum support `clarification.single_observation`, `expected_behavior.explanation`, `status_update`, `resolution_confirmation`, `simple_instruction`, `approval_request`, `multi_step_diagnostic`, `security_incident`, and restricted billing/legal/HR/policy classes. Authority is granted by communication class, not globally.
- **Promotion model:** Preserve the same reasoning/policy pipeline while allowing independently governed promotion of the final action: **Level 1 Draft Assist** -> **Level 2 Human-Approved Send** -> **Level 3 Class-Based Autonomous Send** -> **Level 4 Playbook-Authorized Communication**. Promotions must be policy-version/fingerprint bound, narrowly scoped, auditable, and reversible. The authority to formulate a response and the authority to deliver it remain separate capabilities.
- **Required communication controls:** Exact client/contact/recipient validation; no blind reply-all; ticket-state/evidence binding; technician/Jason collision prevention; evidence-before-assertion; no unsupported commitments or timelines; strict internal/client information firewall; safe-link validation; duplicate/superseded draft control; explicit closure rules; client-scope and cross-client isolation; audience-appropriate AOT tone; and post-send evidence/readback when sending is eventually enabled.
- **Authorization rule:** A client statement such as “go ahead,” “reboot it,” or similar language is evidence of intent, not automatically sufficient Jason execution authority. Identity, role/authority, exact action/target/time, and existing approval/governance controls still apply.
- **Quality-feedback loop:** During Draft Assist, record whether technicians used the Proposed Reply unchanged, edited it, rejected it, or responded differently. Use those outcomes and observed failure modes as evidence when considering promotion of a specific communication class; do not promote merely because drafts appear subjectively good.
- **Initial acceptance test:** Run against a bounded set of genuine client-originated or client-replied Autotask tickets across multiple statuses. Prove detection without relying only on queue/status, perform read-only triage, create only the private **Proposed Reply** note, verify no client notification/send occurred, prove stale-proposal invalidation after a material ticket change, prove one expected-behavior case with an exact authoritative vendor link, prove one insufficient-evidence case that asks only the minimum question, and prove a multi-step scenario routes into its separately governed procedure rather than emitting a checklist.
- **Dependencies:** Existing Triage Intelligence Engine; Audience and Communication Policy Engine; governed Autotask ticket/note reads and internal note creation; exact contact/company resolution; communication-class registry; evidence/source validation; durable proposal state; technician-response/client-response change detection; eventual client-notification capability only after separate promotion.
- **Decision owner:** Jason Governance Authority / AOT Owner
- **Review trigger:** Begin with Draft Assist only. Review promotion only after sufficient real-ticket Proposed Reply history demonstrates recipient accuracy, evidence quality, low edit/reject rates, no information leakage, correct stale-draft handling, and reliable communication-class decisions.


---

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


---

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


---

### TODO-GOV-006 — Configuration-driven TODO engineering readiness and owner lifecycle notifications

- **Priority:** P1
- **Status:** Approved design — implementation pending
- **Risk level:** Moderate
- **Idea:** Add a generic configuration/state-driven readiness and approval record that separates a proposed TODO from work Jason is authorized to implement autonomously. Once an item is approved for autonomous engineering, the engineering system may pick it up without another `proceed` message, but only within the approved scope and existing governance.
- **Why it matters:** The roadmap currently mixes ideas, partially specified work, blocked dependencies, and implementation-ready work. Jason needs a deterministic admission gate so autonomous engineering never invents missing requirements, broadens authority, or starts work before questions are answered. The owner also needs reliable visibility without manually asking for status.
- **Readiness requirements:** A TODO is not eligible for autonomous engineering until its machine-readable/configuration-backed readiness record confirms the exact goal, included/excluded scope, required capabilities, dependencies, authority basis, safety class, human-approval boundaries, acceptance criteria, controlled test target, rollback/failure behavior, production path, documentation impact, and `open_questions=none`. Material scope change invalidates the approval and returns the item to Design Review.
- **Lifecycle:** `Proposed -> Design Review -> Ready for Approval -> Approved for Autonomous Engineering -> In Development -> Validating -> Production Accepted -> Complete`. A blocked implementation enters `Blocked / Needs Decision` without consuming the only engineering slot when other approved independent work exists.
- **Owner notification contract:** For every TODO that enters autonomous engineering, send Al a governed Microsoft Teams update at (1) work start, (2) any blocker/Needs Decision state, and (3) production acceptance. Apply the same lifecycle visibility to autonomous Support List repairs: (1) repair started, (2) blocked/owner action required when applicable, and (3) production-verified complete. Start messages identify the TODO/support ID and approved/bounded scope. Block messages identify the exact blocker/question, completed evidence, and what is needed from the owner. Completion messages identify the deployed/accepted revision and acceptance result. Routine internal step-by-step noise is not required.
- **Delivery requirement:** A notification is not considered delivered until the canonical Teams owner path returns a durable message/correlation identifier and the exact message is verified by provider/readback evidence. Transient send/readback failure gets bounded retry with duplicate suppression. Persistent inability to verify delivery becomes an explicit support/health condition; it must not silently mark the owner as notified. `SUPPORT-CONN-037` tracks current Teams reliability.
- **Configuration principle:** Implement the readiness schema, lifecycle states, notification events, thresholds, and destination reference as configuration/registry/state wherever practical. New TODO approvals should be data/configuration changes, not new hard-coded branches. Code remains appropriate for generic engine primitives, provider adapters, safety invariants, validation, and genuinely new capability classes.
- **Authority boundary:** Approval authorizes implementation of the exact recorded TODO scope only. It does not authorize constitutional changes, broader permissions, new secrets, client/provider scope expansion, disruptive production actions, or material design decisions absent from the approved record. Any such condition moves the TODO to `Blocked / Needs Decision`.
- **Acceptance test:** Approve one bounded non-disruptive TODO through the readiness record; prove it is selected automatically; verify the start Teams message by readback; force one controlled blocker and verify the block message/readback without duplicate sends; clear the blocker; complete CI/merge/deployment through existing governed release lanes; verify the production-accepted Teams message/readback; then materially change the TODO scope and prove the prior approval becomes stale and the item is no longer eligible.
- **Prerequisites:** Canonical TODO schema/registry, owner identity and canonical Teams destination, governed Teams proactive send/readback, existing isolated worktree/PR/CI/merge/release machinery, and existing autonomous SUPPORT repair lane.
- **Decision owner:** AOT Owner / Jason Governance Authority
- **Review trigger:** Implement before enabling general autonomous TODO engineering.

---


---

### TODO-OPS-003 — Autotask ticket work-start lifecycle

- **Priority:** P1
- **Status:** Implemented 2026-09-18
- **Risk level:** Moderate
- **Idea:** When Jason begins substantive work on an existing Autotask ticket, automatically claim the ticket into the Jason queue, set the active working status, set the standard remote-support work type, associate a deterministically proven device/configuration item when available, and normalize Ticket Type / Issue Type / Sub-Issue Type when supported by ticket/playbook evidence.
- **Implemented behavior:** Queue **Jason**; status **In Progress**; Work Type **Remote Support**; preserve existing configuration association; otherwise require exact DRMM UID to active Autotask configuration correlation before writing `configurationItemID`; preserve existing classification unless exact supported labels are available; resolve all mutable labels from live Autotask metadata and require post-write readback. Refined lifecycle rule: triage/eligibility reads do not claim the ticket; claim occurs immediately before the first substantive diagnostic/remediation/verification action. Endpoint tickets require an authoritative governed DRMM read proving the device is online. Jason-owned endpoint tickets that are offline automatically move to **Waiting Device Access**, consume no active-work slot, remain in the Jason queue for read-only reconciliation, and automatically return to **In Progress** when the exact endpoint is online again. The pre-claim queue/status are persisted as trusted state. When Jason must hand work to a human/provider/client, the governed handoff restores that recorded queue/status and records a blocker fingerprint; unchanged blockers cannot immediately reclaim the ticket.
- **Production acceptance (2026-09-27):** Deployed on runtime + MCP revision `5e57a34ac2018bad032e3b4467c58f814023699f` with `/opt/jason/current` reconciled to the same immutable release. Live readback showed 8 Jason tickets in **Waiting Device Access** and 1 in **In Progress**; VZ-HYPER-V was the online in-progress device. Regression coverage proves one-time offline transition, no active-slot consumption, idempotent waiting state, and automatic return to **In Progress** when the exact endpoint is online. Workstream complete.
- **Governance:** Standing Owner-approved administrative start-work transition only. It does not broaden arbitrary ticket-update authority or disruptive-action authority.
- **Production evidence:** Revision `5854cf670e33df473a37890ad9c28b7069510b3e`; controlled acceptance on `T20260914.0026` / ticket ID `140439` verified Jason queue, In Progress status, and Remote Support work type.
- **Canonical documentation:** `docs/operations/Jason-Autotask-Ticket-Work-Lifecycle.md`.
- **Decision owner:** Jason Governance Authority / AOT Owner\n
