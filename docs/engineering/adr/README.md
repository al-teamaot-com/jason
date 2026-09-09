# Project Jason Engineering ADR Index

**Status:** Supporting implementation-engineering index  
**Owner:** Jason Architecture Authority  
**Higher authority:** Jason Constitution, project-level ADRs under `docs/decisions/`, canonical J-series architecture, and `docs/engineering/README.md`

## Purpose

This directory preserves implementation-engineering Architecture Decision Records from Jason's historical `ADR-000x` namespace.

These records document engineering decisions beneath Jason's platform-level governance. They are intentionally distinct from the project-level governed ADR namespace under `docs/decisions/`.

## Records

- [ADR-0001 — Jason Integration SDK](ADR-0001-Jason-Integration-SDK.md)
- [ADR-0002 — ConnectorBase Lifecycle](ADR-0002-ConnectorBase-Lifecycle.md)
- [ADR-0003 — Operation Registries](ADR-0003-Operation-Registries.md)
- [ADR-0004 — Generic Entity Gateways](ADR-0004-Generic-Entity-Gateways.md)
- [ADR-0005 — OpenBao Secrets Broker](ADR-0005-OpenBao-Secrets-Broker.md)
- [ADR-0006 — Execution Policy Engine](ADR-0006-Execution-Policy-Engine.md)
- [ADR-0007 — Central Execution Provider Registry](ADR-0007-Central-Execution-Provider-Registry.md)
- [ADR-0008 — Central Capability Registry](ADR-0008-Central-Capability-Registry.md)
- [ADR-0009 — Governed Capability Resolution Engine](ADR-0009-Governed-Capability-Resolution-Engine.md)

## Authority boundary

An engineering ADR cannot supersede the Constitution, a project-level ADR in `docs/decisions/`, or canonical J-series platform architecture. If a conflict exists, the higher-authority record governs and the engineering ADR must be reconciled or explicitly retained as historical context.
