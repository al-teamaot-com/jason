# J-122 — Canonical MSP Operations Model

**Status:** Accepted First-Pass Working Model  
**Artifact Type:** Canonical Model  
**Owner:** Jason Architecture Authority  
**Date:** 2026-09-13  

## 1. Purpose

Jason exists to help AOT deliver better, more consistent, scalable service to clients. This model provides the provider-independent vocabulary needed for Jason to observe, manage, improve, and automate MSP operations while remaining governed by human-established authority.

The purpose is intentionally practical rather than exhaustive.

This model must:

- give Jason stable MSP operational concepts independent of vendor APIs and product names;
- allow evidence from multiple providers to describe the same real-world client, person, device, service, ticket, incident, vendor, or financial event;
- support proactive management, pattern discovery, proposals, approvals, execution, verification, and monitoring;
- preserve human governance, deterministic authorization, explainability, evidence before assertion, separation of responsibilities, institutional memory, and vendor independence.

## 2. Provider Independence Rule

**Canonical concept first; provider object second.**

An Autotask ticket is an implementation of a Jason service case. A Datto RMM device is an implementation of a managed resource. An Autotask workflow rule is an implementation of a workflow.

Provider-specific fields may be retained as extensions, but they must not become the definition of the canonical concept.

### Native Platform First / Kaseya First at AOT

Jason should prefer native mechanisms in AOT's approved platforms over parallel custom implementations. Today that usually means Kaseya, Autotask, Datto RMM, and IT Glue.

This preference is operational, not architectural. Jason's canonical concepts, policy, authority, audit, and orchestration remain provider-independent.

## 3. Core Canonical Concepts

| Concept | Canonical meaning | Current implementation examples |
|---|---|---|
| **Client** | Organization receiving managed or project services from AOT. | Autotask Company; IT Glue Organization |
| **Site** | Physical or logical client location or operating unit. | Autotask/IT Glue site/location; RMM site |
| **Person** | Human associated with a client, AOT, vendor, or other party. | Autotask Contact; M365 user; technician |
| **Identity** | Account or credentialed digital identity used by a person or service. | Entra user; local/domain account; service account |
| **Technician** | AOT person performing or supervising service work. | Autotask resource; RMM operator |
| **Managed Resource** | Device, server, VM, network device, cloud resource, or other managed technology. | Datto RMM device; IT Glue configuration |
| **Service** | Business or technical service depended upon by a client. | Microsoft 365; ISP; LOB app; backup service |
| **Service Case** | Tracked unit of service work requiring ownership, state, and outcome. | Autotask ticket |
| **Incident** | Unplanned interruption, degradation, or failure affecting a service or resource. | Ticket classification; alert-correlated incident |
| **Problem** | Underlying cause or systemic condition responsible for one or more incidents. | Problem record or Jason-derived problem |
| **Alert** | Machine- or provider-generated signal indicating a condition requiring evaluation. | Datto monitor; backup alert; SaaS alert |
| **Task** | Discrete unit of work within a case, project, workflow, or plan. | Ticket task/checklist item; RMM job |
| **Change** | Planned modification to an environment, configuration, or operational process. | RMM/M365/workflow change |
| **Remediation** | Defined corrective action intended to resolve or reduce a known condition. | RMM component; scripted/native corrective action |
| **Workflow** | Reusable sequence or rules that route, notify, validate, or automate operational work. | Autotask workflow rule; Datto policy logic |
| **Communication Template** | Reusable governed message used in operational communication. | Autotask notification template |
| **Vendor** | External supplier or service provider used by AOT or a client. | Autotask vendor; IT Glue vendor documentation |
| **Agreement** | Commercial/service commitment defining scope, entitlement, or billing treatment. | Autotask contract/service agreement |
| **Invoice** | External financial claim requesting payment for supplied goods/services. | Vendor invoice; AP email/attachment |
| **Purchase Order** | Authorized purchasing record for goods/services. | Autotask PO |
| **Approval** | Recorded human authorization permitting a bounded action or plan. | Jason approval record; approval email/workflow |
| **Exception** | Documented deviation from normal policy, standard, authority, or desired state. | Client exception; temporary waiver |
| **Evidence** | Observed or authoritative information supporting a fact, decision, or conclusion. | Provider read; document; email; log; API response |
| **Decision** | Governed conclusion reached from policy, authority, and facts. | Allow; block; require approval; escalate |
| **Action** | Executed operation intended to change state. | Create PO; run component; update ticket; send message |
| **Verification** | Evidence that an action achieved the intended result and respected guardrails. | Post-read; health check; confirmation |
| **Proposal** | Structured recommendation for an operational improvement or change. | Jason automation/process proposal |
| **Knowledge Artifact** | Human-readable operational knowledge preserved for reuse. | IT Glue document; SOP; Canon; KB article |

## 4. Relationship Model

The model's value comes from relationships rather than isolated records.

| Subject | Relationship | Object |
|---|---|---|
| Client | has | Site / Person / Managed Resource / Service / Agreement / Service Case |
| Person | uses or owns | Identity / Managed Resource |
| Service Case | concerns | Client / Person / Managed Resource / Service |
| Alert | originates from | Managed Resource / Service / Identity |
| Alert | may create or correlate to | Service Case / Incident |
| Incident | may be caused by | Problem / Change / Vendor event |
| Problem | explains | one or more Incidents / Service Cases / Alerts |
| Remediation | targets | Problem / Incident / Managed Resource / Service |
| Workflow | routes or governs | Service Case / Task / Communication / Action |
| Agreement | governs entitlement for | Client / Service / Service Case |
| Invoice | is supplied by | Vendor |
| Invoice | may require | Purchase Order / Approval |
| Approval | authorizes | Proposal / Change / Action / Purchase Order |
| Exception | modifies or suspends | Policy / Standard / Authority / Desired State |
| Decision | is supported by | Evidence and policy/authority |
| Action | must be followed by | Verification and Audit |
| Proposal | may create or modify | Workflow / Remediation / Desired State / Standard |
| Knowledge Artifact | documents | Client / Resource / Service / Workflow / Problem / Decision |

Relationships should retain source provenance and confidence where the relationship is inferred rather than directly observed.

## 5. Operational Management Objects

### 5.1 Operational Improvement Proposal

A proposal is the standard object Jason creates when proactive observation identifies a repeatable improvement opportunity.

It should contain:

- observed pattern and evidence;
- affected clients, devices, users, services, tickets, or workflows;
- recurrence frequency and time window;
- likely root cause and confidence;
- proposed native-platform solution;
- alternative if native capability is insufficient;
- expected benefit;
- risk and excluded/destructive behavior;
- approval requirements;
- pilot scope;
- rollback plan;
- verification criteria;
- post-change monitoring period and success criteria.

### 5.2 Operational Authority Envelope

An authority envelope is the deterministic boundary within which Jason may act without obtaining a new approval.

It should identify:

- authorized capability/action;
- permitted clients, resources, providers, and object types;
- conditions and thresholds;
- excluded or destructive actions;
- financial or impact limits;
- start/end date or revocation condition when applicable;
- required verification and audit evidence.

### 5.3 Desired Operational State

Desired state describes how AOT intends an operational domain to be configured or managed.

Jason compares observed state with desired state and classifies differences as:

- compliant;
- expected exception;
- unknown;
- drift.

Examples include standard ticket-routing rules, notification sequences, required RMM policy assignments, backup expectations, and onboarding standards.

## 6. Initial Provider Mapping for AOT

| Provider | Provider object | Canonical interpretation |
|---|---|---|
| Autotask | Company | Client |
| Autotask | Contact / Resource | Person / Technician |
| Autotask | Ticket | Service Case; may represent Incident or Task by context |
| Autotask | Workflow Rule | Workflow |
| Autotask | Notification Template | Communication Template |
| Autotask | Contract / Service | Agreement / Service |
| Autotask | Purchase Order | Purchase Order |
| Datto RMM | Site / Device | Site / Managed Resource |
| Datto RMM | Monitor alert | Alert |
| Datto RMM | Component / Job | Remediation or Action |
| Datto RMM | Monitoring / Device Policy | Desired State / Workflow / Policy implementation |
| IT Glue | Organization / Configuration | Client / Managed Resource / provider-specific evidence |
| IT Glue | Document | Knowledge Artifact |
| Microsoft 365 / Entra | User / Group / Sign-in / Service Config | Identity / Person / Evidence / Service state |
| Email / Outlook | Message / Attachment | Communication / Evidence; may contain Invoice, approval, vendor response, or incident evidence |

This is a mapping, not an ontology. A future PSA, RMM, documentation platform, or email provider should map into the same canonical concepts without changing Jason's management logic.

## 7. Reference Flows

### 7.1 Low Disk Space

**Alert → Managed Resource → Service Case → Evidence collection → Cause classification → Decision → Remediation/Action → Verification → Service Case update → Recurrence evaluation**

If the cause is safely remediable under an approved authority envelope, Jason may act and verify.

If the condition is unexplained, involves user/business data, recurs beyond tolerance, or indicates undersized storage, Jason escalates or creates an improvement proposal instead of repeatedly treating the symptom.

### 7.2 Invoice to Purchase Order

**Invoice → Vendor + Client correlation → Agreement/quote/order evidence → Duplicate/tolerance checks → Decision/Approval → Purchase Order Action → Verification → Audit + source linkage**

Unknown vendor, client mismatch, duplicate invoice, quantity or price discrepancy, or amount outside delegated authority becomes an exception requiring review.

The canonical process survives a future PSA change; only the provider implementation of Purchase Order changes.

### 7.3 Recurring Ticket Discovery

**Service Cases + Alerts + Actions + Outcomes → Pattern → Problem hypothesis → Evidence review → Proposal → Approval → Native Workflow/Remediation → Pilot → Verification → Post-change monitoring**

Jason initiates this process proactively. Al does not need to point out the recurring work.

A recurring symptom with inconsistent causes should not be automated as though it were a recurring known cause.

## 8. Canonical Invariants

| Invariant | Requirement |
|---|---|
| **Human governance** | Jason operates under delegated authority and never becomes the source of organizational policy or acceptable risk. |
| **Evidence before assertion** | Every operational fact and consequential recommendation traces to evidence or is explicitly labeled hypothesis/unknown. |
| **Deterministic authority** | The same authority policy and facts produce the same authorization result. |
| **Provider independence** | Provider records implement canonical concepts; they do not define them. |
| **Native platform preference** | Use provider-native capabilities when they satisfy the requirement and governance constraints. |
| **Verification required** | A successful API call is not completion; Jason verifies the intended real-world outcome. |
| **Institutional memory** | Proposals, approvals, rejections, exceptions, failures, rollbacks, and lessons are retained as management history. |
| **Separation of responsibilities** | Observation, reasoning, authorization, execution, verification, and audit remain distinguishable. |
| **Unknown is valid** | Missing or contradictory evidence remains unknown rather than being silently guessed. |
| **Management by exception** | Routine work increasingly stays inside approved envelopes; humans are interrupted for exceptions and consequential decisions. |

## 9. Minimal Implementation Contract

Every canonical object should eventually support enough metadata to answer:

- What is it?
- Which organization or tenant does it belong to?
- Which provider records represent it?
- What relationships are known?
- What evidence supports current state?
- How fresh is that evidence?
- What is known, inferred, disputed, or unknown?
- What policy and authority apply?
- What actions were proposed or taken?
- Who approved them, if approval was required?
- How was the result verified?
- What historical decisions or exceptions should affect future management?

### 9.1 Provider Extensions

Provider-specific fields may be retained when useful for troubleshooting, audit, or round-trip writes.

They should be namespaced and must not leak into provider-neutral policy unless the policy explicitly addresses that provider.

## 10. Near-Term Use

This first-pass model is sufficient to guide near-term Jason work. It does not need exhaustive refinement before implementation.

When new capabilities are added, new canonical concepts should be introduced only when an existing concept cannot represent the requirement without distortion.

The practical design check is:

1. identify the canonical object and relationship first;
2. map the current Kaseya/Autotask/Datto/IT Glue/Microsoft object into it;
3. avoid new provider-specific Jason concepts unless there is a documented reason.

## 11. Accepted Design Position

Jason is an operational management proxy under human governance.

Jason should proactively observe AOT operations, identify opportunities, prefer native AOT platform mechanisms, request approval when required, implement within delegated authority, verify outcomes, and preserve the management history that explains why decisions were made.
