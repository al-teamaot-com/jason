# INF-012 — Cross-Provider Relationship Foundation

**Status:** Foundation Built  
**Owner:** Jason Architecture Authority  
**Depends on:** J-118 Relationship Model, Central Orchestrator, Connector Framework

## Purpose

Establish a governed implementation boundary for mapping provider-native links into Jason's canonical relationship model without allowing provider associations to become canonical truth automatically.

## Problem

Autotask, IT Glue, Datto RMM, Microsoft, and security platforms all expose different identifiers and links for the same real-world client, user, asset, service, alert, or work item. Jason must correlate those records without assuming that matching names, shared emails, administrative access, or vendor links establish ownership, authority, or identity.

## Foundation

The implementation adds:

- provider-neutral `ResourceRef` identities;
- provider relationship evidence records;
- canonical relationship records aligned to J-118;
- explicit relationship lifecycle and verification states;
- provenance requirements;
- organization boundary enforcement;
- confidence bounds;
- fail-closed admission of unknown relationship types;
- promotion only from corroborated or verified provider evidence.

## Provider examples

The same relationship boundary can represent facts such as:

- a Datto RMM device `belongs_to` an Autotask company;
- an IT Glue configuration `represents` a managed asset;
- a RocketCyber alert `affects` a Datto RMM device;
- a Microsoft Entra identity `represents` a known contact or person;
- an IT Glue document `documents` a service, asset, or procedure;
- an Autotask ticket `affects` a device, user, service, or organization.

These examples do not imply that every observed provider link is verified. Inferred or discovered links remain evidence and cannot be promoted to canonical truth until the required verification threshold is met.

## Tenant boundary

The foundation rejects cross-organization relationships by default. A later explicit cross-tenant admission path must carry purpose, authority, scope, handling restrictions, expiration, and audit requirements as required by J-118.

## Architectural boundary

Providers do not communicate with one another. A connector may return provider relationship evidence to the Central Orchestrator. The orchestrator or another governed relationship capability may evaluate, corroborate, and promote that evidence.

No relationship record itself grants execution authority.

## Next steps

1. Bind the generic resource gateway to this relationship evidence contract.
2. Add deterministic mappings for verified IT Glue, Datto RMM, and Autotask provider relationships.
3. Add a bounded relationship traversal service for client, user, device, ticket, service, and alert context.
4. Add provider-conflict reporting when multiple systems disagree.
5. Persist governed relationships behind a provider-neutral repository interface.
6. Extend the same model to Microsoft and security-provider resources.
