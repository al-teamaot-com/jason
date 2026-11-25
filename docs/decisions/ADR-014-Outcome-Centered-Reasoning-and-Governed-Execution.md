# ADR-014: Outcome-Centered Reasoning and Governed Execution

**Status:** Owner-approved architectural requirement (2026-11-25); implementation and production activation remain subject to the normal governed engineering and release process.  
**Canonical owner:** [J-100 — Jason Reference Architecture](../architecture/J-100-Reference-Architecture.md)

## Context

People describe the result they need in their own words. They should not need to know Jason's internal capability identifiers, provider API operations, resource taxonomy, or which playbook happens to contain a particular step.

Building a separate user-facing capability and one-off execution path for each provider record type or playbook makes Jason fragmented and brittle. It also shifts the burden of knowing Jason's internal design onto technicians and owners. Jason's architecture must instead center on understanding the request and fulfilling its intended outcome through reusable governed reasoning and execution.

## Decision

Jason shall use one provider-independent, outcome-centered reasoning and orchestration model across conversations, providers, resource types, and playbooks.

1. **Interpret the intended outcome.** Jason resolves what the requester wants accomplished, the relevant targets and relationships, authorized scope, constraints, and conditions for success. If ambiguity could materially change the target, disclosure, or action, Jason asks a focused clarification question.
2. **Reason across authorized evidence.** Jason selects relevant evidence sources from the request and context, retrieves only what is needed, and explains the result or identifies the work required to achieve it. The requester does not need to name a provider capability, API call, resource type, or playbook.
3. **Compose reusable governed work.** The Central Orchestrator uses common provider-independent operation and planning logic with replaceable connectors. Internal capability contracts, resource schemas, and provider operations are implementation mechanisms; they are not separate user-facing products. Do not create one-off workflows for each resource/action or playbook when the shared operation model can perform that work safely.
4. **Keep playbooks declarative and composable.** A playbook supplies purpose, context, evidence requirements, constraints, sequencing, and success conditions. It reuses Jason's shared reasoning, policy, planning, execution, and verification path rather than embedding a separate provider-specific mutation implementation.
5. **Preserve governed exact execution.** Outcome-level flexibility does not authorize arbitrary provider requests. Jason must resolve the exact target and provider operation, evaluate the authenticated actor, tenant/client scope, sensitivity and risk, bind approval where required to the semantic intent and concrete execution plan, verify the plan immediately before execution, record evidence, and verify the result. Ambiguous targets, unsupported operations, changed plans, or failed authorization fail closed with an accurate explanation.
6. **Apply policy to intent and risk.** An authenticated technician's direct request authorizes the exact routine work requested when policy permits it. Approved playbooks may perform routine low-risk updates automatically when backed by sufficiently reliable evidence. Security-sensitive and owner-level actions use the existing governed approval route, including the established Teams approval process when required. A requester's instruction never overrides policy or provider restrictions.
7. **Return a useful result.** Jason reports whether the outcome was achieved, identifies affected records, and summarizes changes. Denials and provider limitations must explain the specific reason and next requirement; a generic failure message is not sufficient.

## IT Glue application

The IT Glue integration shall follow this architecture rather than becoming a collection of one-off write processes.

- The target is governed create, read, update, and delete across IT Glue resource types and operations the provider API supports, within verified AOT client scope and the authenticated requester's authority. Provider limits and authorization still apply.
- Routine technician-requested documentation work, including adding process material or photographs, may proceed from the authenticated technician's exact request. Playbooks may also apply routine low-risk updates using verified evidence, such as a device-name correction from a trusted Kaseya source.
- A restricted record remains restricted. On a blocked attempt, Jason tells the technician specifically that the record is restricted and why the requested operation is denied, without disclosing protected content. A repeated attempt at the same restricted action after that warning triggers Owner escalation through the existing Teams process; a single attempt is not an alert.
- Credential creation, updates, and disclosure require secure handling and requester attribution. Before enabling these actions, verify that IT Glue's audit and applicable Kaseya alerting can identify both Jason and the authenticated requesting technician. If provider auditing can identify only Jason's integration account, Jason blocks the credential action and explains that the provider audit cannot attribute it to the requester. Do not substitute an unaudited Jason-side log for required provider attribution. Bulk credential retrieval must use an existing Kaseya/IT Glue alert path where available, and that behavior must be verified before activation.
- After a successful non-credential change, Jason confirms the result, identifies the record, and summarizes what changed. Credential values must not appear in ordinary audit records or change summaries.

These IT Glue rules define required behavior for the integration. They do not authorize a production write, credential disclosure, or activation.

## Consequences

- The Conversation Experience, Central Orchestrator, Policy, Connector Framework, and playbook architecture must implement one consistent outcome-oriented path.
- Capability/resource schemas remain available internally as validated execution contracts. Their count must not dictate the number of human-facing workflows.
- Provider adapters translate between reusable Jason operations and provider-specific behavior. Provider-specific logic remains isolated behind those adapters.
- New workflows should normally be configuration or declarative composition over existing reasoning and execution primitives. New code is justified when it adds a reusable primitive or enforces a provider-specific safety requirement, not merely because a new record type or playbook exists.
- A generic executor must remain schema-validated, authorization-bound, client-isolated, auditable, and subject to exact-plan verification. It is not a raw API proxy.

## Acceptance criteria for implementation

An implementation conforming to this ADR must demonstrate:

1. A technician can request a meaningful outcome in natural language without supplying internal operation names.
2. The same request interpretation and execution framework can work across multiple IT Glue resource types and CRUD operations supported by the API, without a separate workflow implementation for each type.
3. A playbook can compose the same shared IT Glue operations and policy controls used by direct technician requests.
4. Ambiguous target resolution requests clarification and never chooses the first matching record.
5. Routine, restricted, security-sensitive, owner-level, credential, and bulk-credential cases follow the policy above and produce specific explanations or required approvals.
6. Credential actions fail closed unless provider audit attribution records the requester as well as Jason; any required Kaseya alert is verified.
7. Every successful change has provider readback, requester/Jason audit correlation, and a concise record-level change summary.
8. Unavailable provider operations, authorization gaps, or unverified alert/audit behaviors are reported explicitly and are never represented as completed work.

## Authority and release boundary

This ADR records the owner's architecture-wide requirement. It does not itself authorize code deployment, production IT Glue mutations, credential access, provider credential provisioning, or changes to production policy. Those remain subject to the applicable exact-scope engineering, identity, security, and release controls.
