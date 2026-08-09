# IT Glue + Datto RMM Resource Convergence Checklist

## Goal

Prove the first read-only cross-provider Jason resource-convergence slice using the already-verified production IT Glue and Datto RMM connector boundaries.

The bounded question is:

> Which Datto RMM device corresponds to this IT Glue configuration, and what evidence supports that relationship?

## Proven prerequisites

As of 2026-08-09:

- `it_glue.readonly` resolves through the canonical JKD-003 provider-specific AppRole lifecycle;
- the dedicated Jason IT Glue key is stored as KV v2 version 2 and passed a bounded live Organization GET;
- `datto_rmm.readonly` resolves through the canonical JKD-003 provider-specific AppRole lifecycle;
- Datto OAuth and a bounded live device search have passed;
- neither provider path persists runtime tokens or raw provider payloads;
- both connectors emit `connector.requested` and `connector.completed` audit events.

Credential provisioning is therefore not part of this convergence slice.

## Convergence invariant

The convergence service:

1. authorizes both reads through the provider-neutral resource registry;
2. translates generic resource requests into existing connector capabilities;
3. preserves one organization, principal, client, and correlation context across independent provider reads;
4. denies cross-organization correlation;
5. limits the first Datto candidate search to at most five records;
6. creates INF-012 relationship evidence only when explicitly selected identity attributes agree;
7. performs no provider-to-provider communication;
8. performs no mutation;
9. does not persist raw provider payloads;
10. does not automatically promote provider evidence to canonical truth.

## First controlled live convergence

Use one controlled IT Glue configuration and a deliberately narrow Datto device search hint.

1. select one IT Glue configuration ID belonging to the active organization context;
2. execute the configuration GET through `it_glue.entity.get`;
3. execute one Datto device search through `datto_rmm.device.search`, with at most five returned candidates;
4. normalize only identity attributes actually observed in the provider responses;
5. compare only explicitly approved attributes such as stable serial number, device identifier, or normalized device name;
6. create `ProviderRelationshipEvidence` only when every selected matching attribute is present and equal after normalization;
7. keep the relationship at `corroborated` or lower unless a separate governed verification threshold is satisfied;
8. retain only sanitized evidence metadata and provider-neutral references;
9. do not persist provider response bodies.

## Relationship semantics

A successful first correlation is evidence that an IT Glue configuration `represents` a Datto RMM device. It does not merge the records, transfer ownership, grant authority, or make either provider canonical truth.

Relationship evidence must preserve:

- source provider/resource ID;
- target provider/resource ID;
- organization boundary;
- matched attribute names, not raw protected values in repository evidence;
- confidence;
- verification state;
- observation time;
- source authority/provenance.

## Stop conditions

Stop if:

- provider runtime secret verification fails;
- the selected IT Glue configuration is outside the active organization context;
- the Datto search cannot be narrowed to five or fewer candidates;
- provider response shape requires guessing identity fields;
- selected matching attributes are absent or inconsistent;
- raw secrets or provider payloads would need to be printed or committed;
- a mutation or provider-to-provider call would be required;
- a relationship would cross organization boundaries.

## Next steps after first proof

1. lock deterministic normalization mappings for the identity fields proven by the live responses;
2. add provider-conflict reporting when IT Glue and Datto disagree;
3. add bounded relationship traversal through the Central Orchestrator;
4. persist governed relationships behind the INF-012 provider-neutral repository interface;
5. extend the same relationship model to Autotask, Microsoft, and security-provider resources.
