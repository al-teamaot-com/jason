# INF-011 Kaseya Resource Platform Foundation

## Purpose

INF-011 establishes a provider-neutral resource access model for Kaseya, Datto, and adjacent MSP platforms.

Jason must not accumulate narrow capabilities such as `it_glue.device.lookup` or one-off vendor endpoint wrappers. Capabilities ask for governed resource families; provider adapters translate those requests into the vendor API surface.

## Design rule

**Resource families before endpoint-specific capabilities.**

Examples:

- IT Glue exposes governed entity, document, and relationship resources.
- Datto RMM exposes device, alert, job, and patch-state resources.
- RocketCyber exposes incident and detection resources.
- SaaS Alerts exposes alert and user-activity resources.
- VulScan exposes vulnerability and asset-exposure resources.
- Graphus exposes email-detection resources.
- BullPhish exposes campaign and training-state resources.
- ID Agent exposes credential-exposure resources.

These names describe Jason's canonical resource model. They do not assert that every provider API is already deployed or that every vendor supports the same fields.

## Generic operations

The initial resource gateway supports read-only verbs:

- `describe`
- `get`
- `query`
- `relationships`
- `actions` (enumeration only; not execution authority)

A provider can register the subset it supports for each resource type.

## Governance

Every resource query is:

1. provider-scoped;
2. resource-type-scoped;
3. organization/client-scoped;
4. checked against the canonical resource registry;
5. checked against allowed operations;
6. fail-closed for unknown resources or operations;
7. read-only unless a later governed mutation profile explicitly grants change authority.

The resource registry contains no credentials and performs no network I/O.

## IT Glue convergence

The existing IT Glue connector already has generic `entity.get` and `entity.query` capabilities plus documents and relationships. INF-011 formalizes that pattern as the architectural rule rather than replacing it with per-object capabilities.

Provider-specific convenience capabilities may remain as aliases where they improve operator usability, but the underlying implementation should converge on the generic resource gateway.

## Datto RMM convergence

Existing device, alert, patch, and component-result reads remain valid. Follow-on work should map those operations into the same resource contract so capabilities can request endpoint context without knowing Datto RMM URL structure.

## Planned Kaseya provider family

The resource catalog reserves governed families for:

- Autotask
- Datto RMM
- IT Glue
- RocketCyber
- SaaS Alerts
- VulScan
- Graphus
- BullPhish
- ID Agent

Provider adapters are implemented only when an approved API, authentication contract, and client-boundary model have been verified. Jason must not invent endpoints or scrape unsupported interfaces to satisfy the catalog.

## Capability examples

Capabilities should compose resources instead of mirroring vendor APIs. Examples include:

- Endpoint Health Investigation
- Patch Failure Investigation
- Security Incident Investigation
- User Risk Investigation
- Vulnerability and Exposure Investigation
- Backup Failure Investigation
- Client Documentation Review
- Technician Punch List

A capability may combine several providers through the Central Orchestrator. Providers never call one another directly.

## Mutation boundary

This foundation grants no write authority.

Future IT Glue document/checklist updates, Datto RMM component execution, Autotask changes, or other mutations must use the existing mutation-governance model with explicit approval classes, idempotency, audit evidence, and rollback/compensation where applicable.

## Deployment status

**Repository foundation built; provider convergence and live adapters pending host validation.**

No new credential, provider request, or mutation is introduced by this foundation.
