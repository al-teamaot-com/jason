# Project Jason — TODO category index

> **Read-only organizational view — staged on a documentation branch.** The [canonical governed TODO backlog](./Project-Jason-TODO-and-Future-Ideas.md), its protected-main content, `SUPPORT.md`, and the existing GitHub issues remain authoritative. This index is not an intake source, an approval, or permission to begin work.

**Catalog snapshot:** 2026-10-17 · **Items categorized:** 38 · **Categories:** 8 · **Scope:** the current canonical TODO roadmap only. Items are listed **once**, by primary category; cross-cutting topics can use secondary tags in a future metadata-only enhancement.

## Category priority order — proposed scheduling policy

**This is a default ranking for comparable, eligible TODO work, not an absolute priority or new implementation authority.** A real P0 security incident, critical outage, client-impacting production defect, or explicit Owner commitment overrides category order; otherwise prioritize higher-impact work over cosmetic work.

| Default rank | Category | Main consideration |
| ---: | --- | --- |
| 1 | [Production & Reliability](#production--reliability) | Operational availability, outage recovery, release integrity |
| 2 | [Security & Governance](#security--governance) | Data protection, access control, compliance, authorization |
| 3 | [MSP Operations & Playbooks](#msp-operations--playbooks) | Client service delivery, recurring operational failures |
| 4 | [Finance & Procurement](#finance--procurement) | Billing accuracy, revenue, procurement and finance workflows |
| 5 | [Infrastructure & Engineering](#infrastructure--engineering) | Worker capacity, delivery architecture, maintainability |
| 6 | [Integrations & Connectors](#integrations--connectors) | External APIs, provider capabilities and coverage |
| 7 | [New Features & User Experience](#new-features--user-experience) | Enhancements, user-facing experiences and interfaces |
| 8 | [Research, Knowledge & Improvement](#research-knowledge--improvement) | Discovery, planning, knowledge improvements |

**Cosmetic/UI polish** (font, color, spacing, title styling) is a low-impact subtype of `New Features & User Experience`, scheduled after functional, security, reliability and customer-critical work unless the Owner explicitly elevates it.

### Scheduler decision order (future design; **not active**)

1. **Immediate safety and live operational impact:** response to active incidents, security exposure, data loss, outages, critical regulatory/contractual deadlines, and existing P0 production repair under the current Support-first and owner priority rules.
2. **Eligibility and authority:** choose only work approved and ready under existing authorization, client/tenant boundaries, capacity, dependencies and release gates. Blocked/research/proposed tasks cannot be admitted because they have a high category rank.
3. **Explicit item priority and consequences:** retain existing P0-P3, Owner sequencing, actual severity, affected customers, financial/security impact and deadlines. P0 always dominates routine P2/P3 work irrespective of category.
4. **Category preference within comparable eligible items:** use rank 1-8 above as a deterministic tie-breaker, giving security/governance and production reliability preference over cosmetic UI changes.
5. **Dependency leverage and fairness:** account for foundational work that unblocks other tasks, bounded effort/aging, and avoid indefinite starvation while preserving support-first rules. Record why the next work item was chosen.

**Example:** A critical tenant-isolation flaw outranks a title-color change. Conversely, a confirmed customer production outage outranks a low-impact security-documentation tidy-up. Neither decision should depend on assigning an item an inflated category.

**Implementation gate:** To apply this policy to actual Jason engineering admission, add a separate test-backed change to the **existing** TODO engineering intake/scheduler; compare proposed selection versus existing order on a realistic read-only backlog snapshot and confirm active P0 jobs, worker claims, approvals, and dependencies remain unchanged. This index alone does **not** update live scheduling. Do not enable until the appropriate production/Teams stabilization and release authorization gates are satisfied.

## Quick navigation (ranked)

1. [Production & Reliability](#production--reliability) (3)
2. [Security & Governance](#security--governance) (4)
3. [MSP Operations & Playbooks](#msp-operations--playbooks) (5)
4. [Finance & Procurement](#finance--procurement) (4)
5. [Infrastructure & Engineering](#infrastructure--engineering) (3)
6. [Integrations & Connectors](#integrations--connectors) (9)
7. [New Features & User Experience](#new-features--user-experience) (7)
8. [Research, Knowledge & Improvement](#research-knowledge--improvement) (3)

## Production & Reliability

System integrity, security of core operations, and recovery resilience.

| TODO | Work item | Priority |
| --- | --- | --- |
| [TODO-CONN-004](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-004--direct-teams-gateway-credential-and-residual-openclaw-hardening) | Direct Teams gateway credential and residual OpenClaw hardening | P1 |
| [TODO-GOV-004](./Project-Jason-TODO-and-Future-Ideas.md#todo-gov-004--independent-credential-and-recovery-backup) | Independent credential and recovery backup | P1 |
| [TODO-SEC-005](./Project-Jason-TODO-and-Future-Ideas.md#todo-sec-005--activate-secure-grafana-credential-management) | Activate secure Grafana credential management | P1 |

## Security & Governance

Compliance, policies, authorization, and controlled capability retirement.

 Cross-cutting shared implementation/adoption review: [TODO-ARCH-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-arch-001--cross-workflow-shared-services-adoption-and-usage-led-migration) (counted only under Infrastructure & Engineering).

| TODO | Work item | Priority |
| --- | --- | --- |
| [TODO-OPS-003](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-003--evidence-backed-cyber-insurance-and-security-questionnaire-readiness) | Evidence-backed cyber insurance and security questionnaire readiness | P1 |
| [TODO-GOV-002](./Project-Jason-TODO-and-Future-Ideas.md#todo-gov-002--capability-retirement-and-deprecation-process) | Capability retirement and deprecation process | P2 |
| [TODO-GOV-003](./Project-Jason-TODO-and-Future-Ideas.md#todo-gov-003--formal-risk-taxonomy-for-requests-and-communications) | Formal risk taxonomy for requests and communications | P1 |
| [TODO-GOV-005](./Project-Jason-TODO-and-Future-Ideas.md#todo-gov-005--deterministic-recurring-constitutional-and-compliance-certification) | Deterministic recurring constitutional and compliance certification | P1 |

## MSP Operations & Playbooks

Technician assistance, client support, ticket processing, and operational playbooks.

 Shared ticket/playbook workflow adoption is coordinated under [TODO-ARCH-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-arch-001--cross-workflow-shared-services-adoption-and-usage-led-migration); original domain items remain independently governed.

| TODO | Work item | Priority |
| --- | --- | --- |
| [TODO-OPS-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-001--operational-resolution-memory-and-case-based-troubleshooting-reuse) | Operational Resolution Memory and case-based troubleshooting reuse | P1 |
| [TODO-OPS-002](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-002--governed-backupiq-ticket-processing-playbook) | Governed BackupIQ ticket-processing playbook | P1 |
| [TODO-OPS-004](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-004--governed-drmm-monitor-suppression-for-known-accepted-conditions) | Governed DRMM monitor suppression for known accepted conditions | P1 |
| [TODO-OPS-005](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-005--client-securityposture-review) | Client Security/Posture Review | P1 |
| [TODO-OPS-009](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-009--human-review-handoff-to-help-desk-i) | Human-review handoff to Help Desk I | P1 |

## Finance & Procurement

Quotes, purchasing, invoicing, accounting, contracts, and billing.

 Universal approval and notification consumers participate through [TODO-ARCH-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-arch-001--cross-workflow-shared-services-adoption-and-usage-led-migration) after existing finance gates.

| TODO | Work item | Priority |
| --- | --- | --- |
| [TODO-OPS-007](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-007--invoice-to-catalog-and-purchase-order-workflow) | Invoice-to-catalog and purchase-order workflow | P1 — implement before Duo Security API integration |
| [TODO-OPS-008](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-008--governed-autotask-ticket-billingcharge-workflow) | Governed Autotask ticket billing/charge workflow | P1 |
| [TODO-FIN-002](./Project-Jason-TODO-and-Future-Ideas.md#todo-fin-002--quickbooks-online-integration-with-provider-native-financial-authorization) | QuickBooks Online integration with provider-native financial authorization | P1 |
| [TODO-CONN-015](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-015--governed-autotask-contract-readwrite-capability) | Governed Autotask contract read/write capability | P1 |

## Infrastructure & Engineering

Worker systems, delivery architecture, and engineering readiness.

| TODO | Work item | Priority |
| --- | --- | --- |
| [TODO-OPS-013](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-013--approved-device-provisioning-and-service-offload) | Approved device provisioning and service offload | P1 |
| [TODO-GOV-006](./Project-Jason-TODO-and-Future-Ideas.md#todo-gov-006--configuration-driven-todo-engineering-readiness) | Configuration-driven TODO engineering readiness | P1 |
| [TODO-ARCH-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-arch-001--cross-workflow-shared-services-adoption-and-usage-led-migration) | Cross-workflow shared-services adoption and usage-led migration | P1 — blocked / planning only |

## Integrations & Connectors

External platforms, provider APIs, and governed data/action surfaces.

 Evidence and capability-cache adoption is cross-referenced from [TODO-ARCH-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-arch-001--cross-workflow-shared-services-adoption-and-usage-led-migration) without changing connector authority.

| TODO | Work item | Priority |
| --- | --- | --- |
| [TODO-CONN-005](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-005--microsoft-365--entra-security-posture-reads) | Microsoft 365 / Entra security-posture reads | P1 |
| [TODO-CONN-006](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-006--client-backup-posture-reads--datto-endpoint-backup-api) | Client backup-posture reads / Datto Endpoint Backup API | P1 |
| [TODO-CONN-007](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-007--networksecurity-appliance-posture-reads) | Network/security-appliance posture reads | P1 |
| [TODO-CONN-008](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-008--dnsfilter-posture-integration) | DNSFilter posture integration | P2 |
| [TODO-CONN-009](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-009--bullphishsecurity-awareness-posture-integration) | BullPhish/security-awareness posture integration | P2 |
| [TODO-CONN-011](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-011--duo-security-api-integration) | Duo Security API integration | P1 |
| [TODO-CONN-013](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-013--governed-mailbox-evidence-and-approved-mailbox-lifecycle) | Governed mailbox evidence and approved-mailbox lifecycle | P1 |
| [TODO-CONN-016](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-016--expand-governed-datto-edr-response-actions) | Expand governed Datto EDR response actions | P1 |
| [TODO-CONN-017](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-017--governed-datto-rmm-monitor-policy-targeting-updates) | Governed Datto RMM monitor-policy targeting updates | P1 |

## New Features & User Experience

New interfaces, user-facing workflows, control panels, and assistant experiences.

 Channel-neutral session and delivery reuse is cross-referenced from [TODO-ARCH-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-arch-001--cross-workflow-shared-services-adoption-and-usage-led-migration); new voice/portal features remain deferred.

| TODO | Work item | Priority |
| --- | --- | --- |
| [TODO-COMM-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-comm-001--governed-client-communication-framework) | Governed client communication framework | P1 |
| [TODO-COMM-004](./Project-Jason-TODO-and-Future-Ideas.md#todo-comm-004--governed-teams-interaction-and-owner-operations) | Governed Teams interaction and owner operations | P1 |
| [TODO-COMM-003](./Project-Jason-TODO-and-Future-Ideas.md#todo-comm-003--secure-client-portal-messaging) | Secure client portal messaging | P2 |
| [TODO-OPS-010](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-010--jason-operator-control-panel--command-center-v2) | Jason Operator Control Panel / Command Center v2 | P1 |
| [TODO-OPS-011](./Project-Jason-TODO-and-Future-Ideas.md#todo-ops-011--gpt-insights-self-service-before-technician-guidance) | GPT Insights self-service-before-technician guidance | P1 |
| [TODO-CONN-018](./Project-Jason-TODO-and-Future-Ideas.md#todo-conn-018--internet-accessible-jason-control-panel-through-the-aot-aws-endpoint) | Internet-accessible Jason Control Panel through the AOT AWS endpoint | P2 |
| [TODO-COMMS-004](./Project-Jason-TODO-and-Future-Ideas.md#todo-comms-004--microsoft-teams-voice-call-conversation-with-jason) | Microsoft Teams voice-call conversation with Jason | P2 |

## Research, Knowledge & Improvement

Research quality, organizational knowledge, and evidence-based continuous improvement.

| TODO | Work item | Priority |
| --- | --- | --- |
| [TODO-AI-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-ai-001--reasoning-quality-independent-review-and-confidence-calibration) | Reasoning quality, independent review, and confidence calibration | P2 |
| [TODO-KNOW-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-know-001--aot-wide-it-glue-internal-knowledge-scope) | AOT-wide IT Glue internal knowledge scope | P1 |
| [TODO-GOV-001](./Project-Jason-TODO-and-Future-Ideas.md#todo-gov-001--technology-steward-review-automation) | Technology Steward review automation | P2 |

## Active operational controls — separate from the TODO catalog

These are cross-cutting **GitHub operational/support workstreams**, not additional TODO entries. Their actual status and urgency come from their linked issue and Jason's live state; this index does not change admission or priority.

| Area | Authoritative tracking |
| --- | --- |
| Production Manager / version compatibility | [#1078](https://github.com/al-teamaot-com/jason/issues/1078) |
| Automatic engineering progression / production acceptance | [#1196](https://github.com/al-teamaot-com/jason/issues/1196) |
| Universal Teams approvals | [#1440](https://github.com/al-teamaot-com/jason/issues/1440) |
| Teams approval engineering transport failure | [#1493](https://github.com/al-teamaot-com/jason/issues/1493) |
| Capability retirement dependency gates | [#866](https://github.com/al-teamaot-com/jason/issues/866) |
| Read-only P0 reconciliation / shared root-cause verification | [Self-heal #635](https://github.com/al-teamaot-com/jason/issues/635) · [staged read-only audit](../operations/Jason-P0-Incident-Correlation-Read-Only-Audit-2026-10-17.md) · [shared-service TODO #1535](https://github.com/al-teamaot-com/jason/issues/1535) — no extra P0 or TODO item |

## Preservation and update rules

1. **One governed backlog:** Categories are a view, not separate queues. Do not duplicate TODOs or create a new admission engine. Existing Support-first precedence remains intact.
2. **No behavioral edits:** Do not change the canonical TODO headings, IDs, body text, priority, status, owner approvals, prerequisites, evidence, dependency gates, phase, or item ordering as part of categorization.
3. **No silent authority changes:** A label or category can never move an item into `Planned` or `In progress` or authorize provider writes, merges, releases, or production activity.
4. **Live status from source:** This navigation page intentionally does not copy mutable status values. Read each authoritative TODO entry, linked issue, and live production state before claiming work is complete/approved/blocked.
5. **Keep legacy/completed history:** No archival, deletion, merging or retitling of existing entries from this operation. Legacy ID mapping remains in the canonical document and the consolidation history.
6. **Future maintenance:** When the roadmap changes, refresh this view from the same protected source; validate every current `### TODO-...` entry appears exactly once, and reject missing/duplicate identifiers. Any automated category sync belongs to a future approved, independently tested docs-only change.
7. **Category rank has no execution authority:** Rankings are descriptive and must not silently rewrite P0-P3, alter item readiness, reshuffle an active worker, or activate a scheduler change. Changes to prioritization behavior require separate tests and governed admission.

## Agreed sequencing for version-lifecycle work (informational)

- **Phase 1:** Complete essential release-integrity protection within the current Production Manager P0 (#1078), without opening a competing workstream.
- **Phase 2:** Finish live autonomous engineering continuation (#1196) and Universal Teams Approver acceptance (#1440/#1493) with independently verified outcomes.
- **Phase 3:** Only after production stability **and** Teams approval acceptance have current evidence, review the larger automatic version-discovery, updating, migration and retirement architecture (e.g., #960/#866). A readiness review is not release authorization.

**Staging boundary:** The canonical backlog and protected main must remain unchanged until this index is intentionally reviewed and admitted through the normal documentation process. Do not merge or deploy as a side effect of producing this categorized view.
