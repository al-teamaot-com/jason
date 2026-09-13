# Jason Short-Term Priorities

**Status:** Accepted near-term roadmap direction  
**Date:** 2026-09-13

## Immediate sequence

1. Complete governed **read/write/update capability** for **Autotask**, **Datto RMM (DRMM)**, and **IT Glue**.
2. Immediately after those Big 3 capabilities are proven safe, implement **Continuous Documentation Assurance**.
3. Make **MSP Best-Practice Discovery / Improvement Radar** a priority capability so Jason can discover improvements AOT may not yet know to look for.
4. Establish **Governed DRMM Diagnostic Execution** so Jason can use reusable components and dynamically generated diagnostic scripts for broad read-only investigation.
5. Use those foundations to expand operational autonomy, proactive technical management, and management-by-exception.

## Continuous Documentation Assurance

Jason should be responsible for proactively driving AOT and client documentation toward a known complete, current, and verified state.

Jason should not wait for a technician or owner to point out a missing item. It should compare expected documentation against available evidence and detect gaps, stale records, conflicts, and unverified information on its own.

The core workflow is:

**Detect gap → create work → pursue → validate → document → verify → close → monitor freshness**

### Example: missing DNS / domain registrar credentials

If Jason determines that a client has a registered domain but AOT does not have the required registrar/DNS credentials or authoritative access information documented, Jason should:

1. confirm that the documentation requirement is genuinely missing and not merely stored elsewhere;
2. search authorized authoritative sources before asking a human for information;
3. if the gap cannot be resolved from existing evidence, create an Autotask documentation-gap ticket identifying what is missing, why it matters, the affected client/domain, and what constitutes completion;
4. route or assign the request to the appropriate technician/client contact according to policy;
5. monitor the ticket and relevant authorized communications for a response;
6. follow up and escalate according to normal AOT workflow if the request is ignored or incomplete;
7. validate the information received before treating the gap as resolved;
8. update the correct IT Glue object/credential location using governed write capability;
9. never place secret material in Autotask ticket notes or other inappropriate systems of record;
10. update the Autotask ticket with a safe completion note and reference rather than the secret itself;
11. verify that the IT Glue documentation now exists in the expected state;
12. close the documentation-gap ticket only after verification;
13. retain provenance and a future freshness/reverification expectation where appropriate.

## General documentation behavior

Jason should apply the same closed-loop pattern to other required documentation, including items such as ISP credentials and circuit information, firewall access, domain and DNS ownership, Microsoft tenant relationships, backup/recovery information, LOB applications and vendors, escalation contacts, software licensing, warranties, network diagrams, recovery procedures, and other managed-client operational knowledge.

Jason should classify documentation state at minimum as:

- **Missing** — required information does not exist in the expected system of record.
- **Stale** — information exists but is older than the accepted verification interval or conflicts with newer evidence.
- **Conflicting** — authoritative sources disagree.
- **Unverified** — information exists but its provenance or accuracy is not sufficient.
- **Verified** — required information exists and is supported by current authoritative evidence.

## MSP Best-Practice Discovery / Improvement Radar

Documentation Assurance finds gaps against requirements AOT already knows about. The Improvement Radar must also discover **new things AOT should be checking, documenting, automating, standardizing, or improving**.

Jason should maintain a living, evidence-backed view of "what good looks like" for an MSP and managed-client environment using authoritative industry guidance, vendor guidance, security/compliance frameworks, operating experience, recurring ticket patterns, and relevant MSP industry reports such as Kaseya's annual MSP research where appropriate.

Jason should:

- identify practices, controls, documentation, automation, configuration, service-delivery, commercial, security, compliance, and operational improvements AOT may not already track;
- compare AOT and managed clients against applicable practices without blindly treating every industry recommendation as mandatory;
- classify findings by applicability, evidence, client/AOT impact, urgency, cost, effort, risk, and expected benefit;
- distinguish an interesting idea from an important gap or urgent risk;
- prefer native approved platform capabilities when proposing implementation;
- prepare concise improvement proposals rather than silently making consequential changes;
- after approval, create/manage the required work, verify implementation, document the result, and monitor whether the improvement actually helped;
- preserve rejected proposals and rationale so Jason does not repeatedly rediscover unsuitable ideas.

This capability is deliberately proactive: **Jason should look for things AOT does not yet know to ask about.**

## Governed DRMM Diagnostic Execution

Jason should develop and maintain a useful library of **Datto RMM components and scripts** for repeatable diagnostics, while also being able to generate and run one-off diagnostic scripts when a reusable component does not yet exist.

The desired operating principle is:

> **Jason should be able to run almost any script that is genuinely diagnostic/read-only, provided the target, requester, tenant, data access, execution effect, and output are authorized and auditable.**

DRMM is an execution provider, not the canonical definition of the capability. A recurring diagnostic that proves useful should normally graduate into a versioned reusable component rather than remain an ad hoc script forever.

### Read-only execution boundary

A script must not be treated as safe merely because it is described as "read-only." Jason should deterministically classify execution effects before unattended execution.

A read-only/diagnostic script may generally inspect authorized information such as system state, hardware, OS configuration, services, processes, event logs, installed software, disk usage, network configuration, registry values, certificates and other troubleshooting evidence.

Read-only autonomous execution must not include actions such as software installation/removal, service start/stop/restart, reboot/shutdown, registry or policy modification, account/password changes, security-control changes, destructive file operations, persistence creation, or other endpoint mutation. Credential extraction and access to sensitive content remain separately governed even when no endpoint state would be changed.

Where a diagnostic requires temporary local scratch data, that behavior should be explicitly classified and bounded rather than falsely labeled pure read-only.

### Execution controls

At minimum, Jason should preserve:

- authenticated requester and tenant/client scope;
- exact target device or approved population;
- script/component version or content hash;
- declared and evaluated effect class;
- reason for execution and related ticket/work item when applicable;
- interpreter and execution identity;
- timeout and output-size limits;
- sensitive-output handling and redaction rules;
- start/end time and provider result;
- captured diagnostic evidence or governed evidence reference;
- promotion path from successful ad hoc diagnostic to reusable DRMM component.

The objective is broad diagnostic freedom without turning "read-only" into an ungoverned arbitrary-code bypass.

## Definition of done

For operational work that creates or changes durable knowledge, documentation is part of completion:

**Resolve → Verify → Document → Verify documentation → Close**

Jason should not consider a documentation-gap workflow complete merely because a ticket was created or because someone supplied information. Completion requires the appropriate system of record to be updated and verified.

## Governance boundary

Jason may automatically fill documentation gaps only when the fact is supported by authoritative evidence and the applicable write authority permits the change.

Jason must not invent missing facts, silently infer credentials, expose secrets in ticket notes, cross client/tenant boundaries, or use diagnostic scripting as a way around normal capability authorization. Unknowns should remain explicit until verified.
