# Project Jason Engineering Architecture

**Status:** Active implementation-engineering architecture  
**Owner:** Jason Architecture Authority  
**Higher authority:** Jason Constitution, canonical J-series architecture under `docs/architecture/`, approved project ADRs under `docs/decisions/`

## Purpose

This directory preserves and governs Jason's detailed engineering architecture, including the Jason Integration SDK (JIS), implementation-level ADRs, provider engineering references, capability/execution-policy implementation architecture, and resolution-engine details.

It was consolidated from the historical top-level `architecture/` directory so all governed human-facing documentation is discoverable beneath `docs/`.

## Authority boundary

The canonical J-series architecture in `docs/architecture/` defines enduring platform-level responsibilities and boundaries. The engineering records here define implementation structure beneath those boundaries.

If an engineering record conflicts with the Constitution, an approved project ADR in `docs/decisions/`, or the canonical J-series architecture, the higher-authority record wins and this engineering material must be reconciled.

Provider-specific documentation must not override JIS, capability/provider registries, identity/authority, Central Orchestrator, System Registry, or policy-engine governance.

## Structure

### `adr/`

Implementation-engineering Architecture Decision Records. These use the historical `ADR-000x` engineering namespace and are distinct from project-level governed decisions in `docs/decisions/`.

### `jis/`

Jason Integration SDK engineering principles, provider-development procedures, templates, checklists, and milestone-closeout requirements.

### `providers/`

Provider-specific reference specifications, limitations, and validation status.

### `capabilities/`

Engineering-level capability-registry and capability integration references.

### `execution-policy/`

Engineering documentation for execution-policy/provider-registry implementation boundaries.

### `resolution/`

Engineering documentation for governed resolution implementation.

## Documentation rule

New platform-level architecture belongs in `docs/architecture/` or `docs/decisions/` as appropriate. New detailed implementation engineering architecture may live here when it is intentionally subordinate to those canonical platform records.

Do not introduce a second project-level architecture authority under this directory.
