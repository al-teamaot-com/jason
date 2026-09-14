# Jason User-Relevant Output and Capability Awareness

## Status

Accepted operating principle derived from production real-world testing on 2026-09-14.

## Problem

Provider APIs often return implementation identifiers, foreign keys, numeric picklists, GUIDs, or other values that are useful to software but poor answers to an operator. A technically correct provider value is not sufficient when the user asked for business meaning.

Examples of unacceptable default presentation include:

- Autotask `assignedResourceID` instead of the assigned technician's name;
- Autotask company ID instead of client/company name;
- numeric status/queue/priority values instead of their labels;
- Datto device UID instead of hostname when the hostname is the useful identifier;
- Microsoft Entra object GUID instead of display name / UPN when the person is the requested fact.

Provider identifiers remain valuable internally for exact correlation, evidence, follow-on reads, auditing, and future safe writes. They are not discarded; they are simply not substituted for meaning.

## User-Relevant Output Principle

> Jason must translate provider-native evidence into canonical, human-relevant business information before presenting it to the requester. Provider identifiers and implementation details remain internal unless they are necessary to understand, disambiguate, troubleshoot, audit, or fulfill the user's explicit request.

### Consequences

1. A foreign key is an instruction to resolve authoritative context, not normally an answer.
2. If the provider has an authoritative governed read capable of resolving the referenced object, Jason should use it before presenting the result.
3. If a foreign key cannot yet be resolved safely, Jason should state what is known and what resolution capability is missing rather than pretending the raw identifier is equivalent to the business fact.
4. IDs may be displayed when explicitly requested, when required for disambiguation, or when useful to troubleshooting/auditing; the human-readable value should still be preferred alongside them when available.
5. Canonical output schemas should favor stable business concepts over provider-specific field names.

## Canonical foreign-key enrichment

Foreign-key resolution belongs in Jason's canonical/correlation layer and reusable provider capabilities, not in one-off conversational prompts.

Initial Autotask enrichment targets include:

- assigned resource / technician;
- creator / last updater where operationally useful;
- company/client;
- contact;
- queue;
- status;
- priority;
- configuration item.

The immediate capability gap exposed by production testing is Autotask Resources. The preferred canonical additions are `service.resource.search` and `service.resource.read` (or an equivalent provider-neutral service-person resource), backed by the Autotask Resources API. Ticket output can then resolve `assignedResourceID` through the canonical service resource without making Autotask's ontology Jason's ontology.

## Capability-Aware Answer Principle

> Jason must distinguish what it can currently know, what it actually checked, and which capability/resource family is missing. Jason must not imply that an entire provider is unavailable when only a particular capability family is unavailable, and it must not substitute a non-authoritative source merely because that source is available.

### Example: Microsoft tenant question

Current production Microsoft Graph reads cover exact Entra user search and read. Jason therefore may say that it can read Entra users. It may not claim that Microsoft/Entra is unavailable as a whole.

At the same time, the current catalog does not yet include tenant-wide resource families such as:

- organization/tenant facts;
- verified domains;
- subscribed SKUs / licensing inventory and assignment summaries;
- Conditional Access policy inventory/posture;
- Exchange organization/mailbox configuration.

A question such as “what can you tell me about our Microsoft tenant?” should therefore produce a capability-aware answer: summarize the Microsoft facts Jason can actually read, identify missing tenant-level families precisely, and avoid inventing or substituting Jason System Registry data. The System Registry is authoritative for Jason topology and declared operational state, not for Microsoft tenant configuration.

## Authoritative-source selection

For every requested fact Jason should prefer, in order:

1. an active canonical capability mapped to an authoritative provider;
2. a trusted correlation/enrichment read that resolves an already-authorized provider reference;
3. an explicit statement that the fact is unavailable because the needed capability is missing.

It should not silently fall back to a source whose authority does not match the requested fact.

## Broad questions and orchestration

Broad questions are not a reason to create a giant provider-specific “everything” endpoint. Jason should orchestrate multiple narrow reusable capabilities.

A future Microsoft tenant summary, for example, should compose tenant identity, domain, licensing, security-policy and Exchange resources into an MSP-owner-facing summary. The individual capabilities remain independently governed and reusable.

## Privacy and release behavior

Humanization does not weaken information-release controls. Resolution of a provider ID into a person/client/name is itself an information use/release step and remains subject to existing identity, organization/client scope, sensitivity, and release authorization. If resolution is denied, the answer fails closed.

## Acceptance criteria for user-facing provider answers

A provider-backed answer is production-quality when:

- it answers the user's business question rather than merely echoing provider fields;
- provider IDs are suppressed unless relevant or explicitly requested;
- foreign keys are resolved where an authoritative governed capability exists;
- labels replace numeric picklist values where possible;
- ambiguity is preserved and never resolved by “take the first match”;
- unsupported facts are described as missing capability/resource families rather than provider-wide unavailability;
- sources used are authoritative for the fact;
- information-release governance remains fail-closed.
