# Jason Capability Register

**Version:** 0.1  
**Status:** Active build register  
**Owner:** Jason Architecture Authority

## Purpose

The Capability Register is the authoritative inventory and maturity roadmap for governed Jason capabilities.

Every capability must have a documented purpose, scope, authority model, evidence requirements, success criteria, review interval, and retirement criteria.

Capabilities are expressed independently of the provider currently implementing them.

## Capability maturity stages

1. **Observe** — collect and organize evidence; do not recommend or act.
2. **Recommend** — produce a recommendation for human review.
3. **Execute with approval** — act only after explicit approval bound to the proposed action.
4. **Bounded autonomous execution** — act automatically within approved policy, scope, and risk limits.
5. **Governed optimization** — recommend or perform controlled improvements while preserving human governance.

No capability is born autonomous. Authority is earned through demonstrated competence and evidence.

## Required capability fields

| Field | Requirement |
|---|---|
| Capability ID | Stable canonical identifier |
| Name | Human-readable name |
| Purpose | Organizational outcome it supports |
| Business justification | Why the capability should exist |
| Competencies | Professional skills exercised |
| Inputs | Required structured inputs |
| Outputs | Structured results produced |
| Required evidence | Minimum evidence needed for reliable operation |
| Applicable policies | Governing policies and standards |
| Authority | Maximum permitted mode and required approver classes |
| Risk level | Low, Medium, High, or Critical |
| Current maturity stage | Observe through Governed Optimization |
| Success metrics | Evidence that the capability is effective |
| Failure behavior | Safe degraded or failure response |
| Steward | Accountable owner for continuing fitness |
| Review interval | Required reassessment cadence |
| Retirement criteria | Conditions under which it should be removed or replaced |
| Provider implementations | Replaceable current providers |
| Status | Proposed, Building, Pilot, Active, Suspended, Retired |

## Capability #001

### CAP-001 — Professional Ticket Investigation

| Field | Definition |
|---|---|
| Capability ID | `CAP-001` |
| Name | Professional Ticket Investigation |
| Purpose | Give an AOT technician a useful, evidence-grounded assessment and next action from an operational ticket. |
| Business justification | Ticket investigation is frequent, representative of AOT operations, and exercises the kernel end to end. |
| Competencies | Observe, normalize, correlate, investigate, rank hypotheses, explain, recommend, communicate, remember, learn. |
| Inputs | Ticket identity, title, description, client, configuration item, attachments, diagnostic output, requester context, permitted related records. |
| Outputs | Situation summary, missing information, observations, ranked hypotheses, recommendation, confidence, risk, approval needs, evidence references, proposed communication, learning candidate. |
| Required evidence | Original ticket content, authoritative client and asset mapping, relevant diagnostics, source and collection timestamps, provenance, integrity metadata where applicable. |
| Applicable policies | Client isolation, evidence before inference, lowest-risk successful action, progressive disclosure, authority before execution. |
| Authority | Version 0.1 maximum mode is `recommend`. No operational execution. |
| Risk level | Medium overall; individual recommendations may be Low through Critical. |
| Current maturity stage | Recommend |
| Success metrics | Time to useful answer, technician acceptance rate, evidence citation completeness, false-confidence rate, cross-client leakage rate, escalation appropriateness, outcome confirmation rate. |
| Failure behavior | State what is missing, reduce confidence, recommend the smallest evidence-gathering step, and never fabricate. |
| Steward | To be assigned before pilot. |
| Review interval | Every sprint during pilot; monthly after stabilization. |
| Retirement criteria | Retire or simplify when a dependable approved platform capability provides equivalent outcomes with lower maintenance and risk. |
| Provider implementations | Initial implementation may use Autotask, Datto RMM, IT Glue, and an approved reasoning model through replaceable connectors. |
| Status | Building |

## Planned vertical slices

The order below is provisional and should be changed when implementation evidence supports a better sequence.

| ID | Capability | Initial stage | Purpose |
|---|---|---:|---|
| CAP-001 | Professional Ticket Investigation | Recommend | First end-to-end kernel slice |
| CAP-002 | Disk Health Investigation | Recommend | Exercise structured diagnostics and bounded technical reasoning |
| CAP-003 | Microsoft 365 Mail Investigation | Recommend | Test a different provider and evidence domain |
| CAP-004 | Backup Failure Investigation | Recommend | Exercise time-sensitive operational evidence and escalation |
| CAP-005 | Client Communication Drafting | Recommend | Apply audience-aware progressive disclosure |
| CAP-006 | Knowledge Candidate Capture | Observe | Preserve reusable lessons from completed work |

## Admission test

A proposed capability should not enter the register unless:

1. It supports a concrete organizational outcome.
2. At least one real workflow needs it.
3. Its inputs and outputs can be defined.
4. Its authority and client scope can be bounded.
5. Required evidence can be identified.
6. Success and failure can be measured.
7. A simpler approved platform capability has been considered first.
8. A steward, review interval, and retirement criteria can be assigned.

## Review rule

The register is a living governance artifact. Changes should be based on operating evidence, platform changes, risk, or lessons learned rather than novelty or architectural speculation.
