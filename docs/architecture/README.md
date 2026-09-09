# Project Jason Architecture — Authority Map

**Status:** Active architecture documentation index  
**Owner:** Jason Architecture Authority  
**Governing authority:** Jason Constitution, J-404 Documentation Governance and Continuity

## Purpose

This directory consolidates Jason architecture records while preserving the distinction between canonical architecture and earlier supporting design syntheses.

A document being physically located in this directory does not by itself make every statement in that document equal authority. Use the classification below when records overlap.

## Canonical J-series architecture

The J-series records are the canonical owners for their named architectural subjects:

| Record | Canonical subject |
|---|---|
| `J-100-Reference-Architecture.md` | Enduring top-level Jason architectural building blocks and boundaries |
| `J-101-Capability-Registry.md` | Capability Registry architecture and capability-definition boundary |
| `J-102-Governed-Approval-Architecture.md` | Governed approval architecture |
| `J-103-System-Registry.md` | System Registry architecture, operational topology/state authority, verification, and drift-management boundary |

When one of these subjects is discussed elsewhere, the applicable J-series record owns the enduring architecture unless a higher-authority constitutional/governance record or a later approved ADR explicitly supersedes it.

## Supporting foundational architecture records

The following earlier architecture records are retained because they contain valuable design intent, platform requirements, and institutional history:

- `PROJECT_JASON_ARCHITECTURE_BLUEPRINT.md`
- `JASON_CORE_SERVICES_SPECIFICATION.md`
- `JASON_CAPABILITY_CATALOG.md`
- `JASON_DEPLOYMENT_SYSTEM.md`
- `JASON_FOUNDATION_BUILD_MILESTONE.md`

These records are **supporting foundational references**, not independent authority to override later J-series architecture, the Constitution, approved ADRs, governed component specifications, or current System Registry state.

Where a supporting record describes a durable requirement not yet represented in the J-series/component/standard structure, that requirement must be reconciled into the appropriate canonical owner before the supporting record is retired or archived.

## Special classification notes

### Capability Catalog

`JASON_CAPABILITY_CATALOG.md` is retained as an early approved capability-catalog design and inventory. Current capability identity, provider resolution, lifecycle, and executable definitions must be established from the governed Capability Registry architecture/implementation and current registered capability sources. The catalog must not become a parallel current operational inventory.

### Deployment System

`JASON_DEPLOYMENT_SYSTEM.md` describes deployment-system design principles. Current production deployment topology is established by the System Registry and governed deployment/verification evidence, not by copying deployed state into this architecture record.

### Foundation Build Milestone

`JASON_FOUNDATION_BUILD_MILESTONE.md` is historical milestone-oriented architecture context. Current milestone authority is maintained in `docs/milestones/`.

## Reconciliation rule

When a future session finds a conflict:

1. identify the exact fact or requirement in conflict;
2. determine the authoritative owner using the Constitution, J-404, this index, and the Documentation Register;
3. do not silently delete the lower-authority statement;
4. update the canonical owner if a durable requirement was missing;
5. mark the supporting/historical statement superseded or clarify its scope;
6. preserve material history and evidence;
7. record significant reconciliation in a durable session/decision record.

## Operational-state rule

Architecture defines what must exist and how responsibilities are separated. The System Registry defines and verifies how production is currently wired.

Do not infer current container images, hashes, providers, dependency bindings, identity bindings, capability lifecycle, or deployment state from an architecture document.
