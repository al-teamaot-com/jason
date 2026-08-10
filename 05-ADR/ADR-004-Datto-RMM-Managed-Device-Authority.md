# ADR-004 — Datto RMM Managed-Device Authority

**Status:** Proposed for governance review  
**Decision scope:** RMM-managed device identity, existence, and operational state  
**Affected providers:** Datto RMM, IT Glue, Jason canonical object and relationship services

## Context

Jason can observe the same physical endpoint in multiple provider systems. Datto RMM manages the endpoint operationally, while IT Glue primarily documents it. Treating the two provider records as equal authorities creates avoidable ambiguity when names differ, documentation is stale, or one provider omits an identity attribute from a particular API response.

The existing physical AOT workflow already treats Datto RMM as the operational inventory for managed endpoints. Host validation also demonstrated that a bounded Datto search can establish a managed device even when an IT Glue configuration cannot yet be safely corroborated to that device.

J-117 remains controlling: a provider record is not the Jason canonical object itself, and Jason canonical identity must remain provider-independent.

## Decision

For the **RMM-managed device domain**, Datto RMM is the authoritative external provider for:

- existence of an RMM-managed device;
- Datto device UID as the authoritative external mapping identifier;
- current RMM hostname and other runtime identity attributes exposed by governed reads;
- Datto site/client association when governed organization mapping has been validated;
- agent/runtime state, online state, and other RMM-operational facts.

IT Glue is a documentation source for device-related records. An IT Glue configuration may represent a Datto-managed device, but the IT Glue record does not independently establish or override the existence or operational identity of that managed device.

Jason remains authoritative for:

- the provider-independent canonical Asset/Device object identifier;
- organization and tenant binding after governed resolution;
- the cross-provider mapping that states an IT Glue configuration represents a Datto-managed device;
- mapping verification state, confidence, provenance, history, and promotion decisions;
- policy, authorization, approvals, and execution authority.

## Required behavior

1. A valid governed Datto device observation may establish that a managed device exists even when no IT Glue mapping has been proven.
2. Failure to corroborate an IT Glue configuration must leave the documentation relationship `unresolved`; it must not erase or downgrade the Datto managed-device authority observation.
3. IT Glue data must not overwrite Datto-authoritative managed-device operational attributes merely because the IT Glue record is accessible or appears more descriptive.
4. A Datto provider UID remains an external mapping identifier, not the Jason canonical object ID.
5. Cross-provider relationship evidence remains evidence-only until separately promoted under Jason policy.
6. Cross-organization mappings remain denied.
7. Ambiguous Datto search results remain fail-closed; authority requires one governed device observation.
8. Secrets, provider access tokens, and raw provider payloads remain outside canonical object and evidence records unless explicitly governed by a protected evidence mechanism.

## Relationship direction and provider authority

Provider authority and canonical relationship direction are separate concerns.

J-118 already defines the canonical relationship `represents` as the representation pointing to the object it represents. Therefore, when documentation is corroborated, the canonical relationship evidence is:

`IT Glue configuration -> represents -> Datto managed-device observation`

Datto RMM is still the authoritative external provider for managed-device existence and operational identity. The relationship direction does not make IT Glue authoritative for the device and does not make the Datto provider record the Jason canonical object.

Jason must not introduce an inverse canonical relationship such as `represented_by` merely to place the authoritative provider on the source side. If an inverse view is useful to operators, it may be presented as a derived view while preserving the canonical `represents` relationship in stored evidence.

## Operational consequence

The convergence workflow becomes:

1. establish one bounded Datto managed-device observation;
2. recognize the Datto observation as authoritative for the managed-device domain;
3. locate or read a candidate IT Glue configuration;
4. compare governed identity attributes;
5. create `IT Glue configuration -> represents -> Datto managed-device observation` evidence only when sufficient attributes corroborate the mapping;
6. otherwise retain the Datto managed device and mark the documentation relationship unresolved;
7. require separate policy-controlled promotion before a relationship becomes canonical.

## Alternatives considered

### Equal-provider corroboration before recognizing a device

Rejected. This incorrectly makes documentation quality a prerequisite for recognizing an endpoint that is already actively managed by the RMM platform.

### IT Glue as device source of truth

Rejected for RMM-managed endpoints. IT Glue is optimized for documentation and may contain stale, manually maintained, renamed, or unmatched configuration records.

### Datto provider record as Jason canonical identity

Rejected. This violates J-117 provider independence. Datto is authoritative within the managed-device provider domain, while Jason retains the canonical object identity and governed mapping model.

### New inverse canonical relationship `represented_by`

Rejected. J-118 requires the smallest useful canonical relationship vocabulary and already defines `represents`. Provider authority does not justify adding a synonymous inverse relationship to the canonical model.

## Governance impact

This ADR narrows authority by resource domain and attribute rather than declaring one provider globally authoritative. Future authority assignments for users, tickets, agreements, knowledge, security state, Microsoft identities, cloud resources, or other objects require their own policy or architecture decision.

## Validation requirements

Implementation must prove that:

- a governed Datto device projection is marked with managed-device authority;
- a non-Datto observation cannot establish managed-device authority;
- unmatched IT Glue documentation leaves relationship state unresolved while preserving the Datto authority observation;
- corroborated mappings use the existing canonical `represents` relationship from IT Glue documentation to the Datto managed-device observation;
- provider mismatch and tenant mismatch still fail closed;
- no canonical promotion occurs as a side effect of observation.
